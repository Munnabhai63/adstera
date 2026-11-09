"""
cluster_manager.py — Step 5.4: Multi-Machine Cluster Orchestrator

Coordinates distributed traffic generation across a multi-node VPS cluster:
- Central coordinator manages worker nodes
- Work distribution: splits domains and daily session caps across active nodes
- Node heartbeat tracking (auto-detects dead or lagging worker nodes)
- Rebalancing: redistributes workload if a worker node goes offline
- Anti-detection advantage: Traffic originates from completely different physical server IPs
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

CLUSTER_STATE_PATH = Path(__file__).parent / "state" / "cluster_state.json"

DEFAULT_DOMAINS = [
    "loanraaj.com", "rechargetak.com", "rechargepur.com", "tazaloan.com",
    "loankiseva.com", "karzseva.com", "loantau.com", "tazabhav.com",
    "tazarokda.com", "rechargekar.com",
]


@dataclass
class ClusterNode:
    node_id: str
    host: str
    port: int = 5050
    role: str = "worker"  # 'coordinator' | 'worker'
    status: str = "online"  # 'online' | 'busy' | 'offline'
    assigned_domains: list[str] = field(default_factory=list)
    assigned_daily_cap: int = 500
    sessions_today: int = 0
    healthy_proxies: int = 0
    last_heartbeat: float = field(default_factory=time.time)

    @property
    def is_alive(self) -> bool:
        """Node is considered alive if heartbeat is within last 120 seconds."""
        return (time.time() - self.last_heartbeat) < 120.0


class ClusterManager:
    """Manages node registry, workload sharding, and cluster health."""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}
        cluster_cfg = self.cfg.get("cluster", {})
        self.enabled: bool = bool(cluster_cfg.get("enabled", False))
        self.node_id: str = cluster_cfg.get("node_id", "node_coordinator")
        self.total_daily_cap: int = int(self.cfg.get("scheduler", {}).get("daily_cap", 2000))
        self.heartbeat_timeout_s: float = float(cluster_cfg.get("heartbeat_timeout_s", 120.0))
        self.nodes: dict[str, ClusterNode] = {}
        self._load_state()

    def register_node(
        self,
        node_id: str,
        host: str,
        port: int = 5050,
        role: str = "worker",
    ) -> ClusterNode:
        """Register a new or returning node in the cluster."""
        node = ClusterNode(
            node_id=node_id,
            host=host,
            port=port,
            role=role,
            status="online",
            last_heartbeat=time.time(),
        )
        self.nodes[node_id] = node
        self.rebalance_workload()
        self._save_state()
        logger.info("Cluster node registered: %s (%s:%d, role=%s)", node_id, host, port, role)
        return node

    def record_heartbeat(
        self,
        node_id: str,
        sessions_today: int = 0,
        healthy_proxies: int = 0,
        status: str = "online",
    ) -> bool:
        """Record a node's heartbeat. Returns True if node recognized, False otherwise."""
        if node_id not in self.nodes:
            logger.warning("Heartbeat from unknown node: %s", node_id)
            return False
        node = self.nodes[node_id]
        node.last_heartbeat = time.time()
        node.sessions_today = sessions_today
        node.healthy_proxies = healthy_proxies
        node.status = status
        self._save_state()
        return True

    def get_active_workers(self) -> list[ClusterNode]:
        """Returns list of online worker nodes whose heartbeats are fresh."""
        now = time.time()
        active = []
        for n in self.nodes.values():
            if n.role == "worker" and (now - n.last_heartbeat) <= self.heartbeat_timeout_s:
                active.append(n)
        return active

    def rebalance_workload(self, domains: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """
        Evenly partitions target domains and total daily session cap across all alive worker nodes.
        Returns workload assignments mapping node_id -> {domains, daily_cap}.
        """
        target_domains = domains or self.cfg.get("target", {}).get("domains") or DEFAULT_DOMAINS
        active_workers = self.get_active_workers()

        if not active_workers:
            # Standalone fallback: all work assigned to local coordinator
            return {
                self.node_id: {
                    "domains": target_domains,
                    "daily_cap": self.total_daily_cap,
                }
            }

        n_workers = len(active_workers)
        cap_per_worker = max(10, self.total_daily_cap // n_workers)

        assignments: dict[str, dict[str, Any]] = {}
        for idx, worker in enumerate(active_workers):
            # Distribute domains round-robin
            assigned = [d for i, d in enumerate(target_domains) if (i % n_workers) == idx]
            if not assigned:
                assigned = [target_domains[0]]
            worker.assigned_domains = assigned
            worker.assigned_daily_cap = cap_per_worker
            assignments[worker.node_id] = {
                "domains": assigned,
                "daily_cap": cap_per_worker,
            }

        self._save_state()
        logger.info("Cluster workload rebalanced across %d workers: %s", n_workers, list(assignments.keys()))
        return assignments

    def get_node_assignment(self, node_id: str) -> dict[str, Any]:
        """Retrieve the domains and daily cap allocated for a specific node."""
        if node_id in self.nodes:
            n = self.nodes[node_id]
            return {
                "node_id": n.node_id,
                "domains": n.assigned_domains,
                "daily_cap": n.assigned_daily_cap,
                "status": n.status,
            }
        return {
            "node_id": node_id,
            "domains": DEFAULT_DOMAINS,
            "daily_cap": self.total_daily_cap,
            "status": "unregistered",
        }

    def get_cluster_overview(self) -> dict[str, Any]:
        """Returns consolidated cluster metrics for UI dashboards."""
        now = time.time()
        total_sessions = sum(n.sessions_today for n in self.nodes.values())
        total_proxies = sum(n.healthy_proxies for n in self.nodes.values())
        online_count = sum(1 for n in self.nodes.values() if (now - n.last_heartbeat) <= self.heartbeat_timeout_s)

        return {
            "cluster_enabled": self.enabled,
            "coordinator_id": self.node_id,
            "total_nodes": len(self.nodes),
            "online_nodes": online_count,
            "total_sessions_today": total_sessions,
            "total_healthy_proxies": total_proxies,
            "aggregate_daily_capacity": sum(n.assigned_daily_cap for n in self.nodes.values()),
            "nodes": [asdict(n) for n in self.nodes.values()],
        }

    def _save_state(self) -> None:
        try:
            CLUSTER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": time.time(),
                "coordinator_id": self.node_id,
                "nodes": {nid: asdict(n) for nid, n in self.nodes.items()},
            }
            CLUSTER_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed saving cluster state: %s", exc)

    def _load_state(self) -> None:
        try:
            if CLUSTER_STATE_PATH.exists():
                data = json.loads(CLUSTER_STATE_PATH.read_text(encoding="utf-8"))
                for nid, ndict in data.get("nodes", {}).items():
                    self.nodes[nid] = ClusterNode(**ndict)
        except Exception:
            pass


def build_from_config(cfg: dict) -> ClusterManager:
    return ClusterManager(cfg=cfg)
