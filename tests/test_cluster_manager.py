"""
tests/test_cluster_manager.py — Step 5.4: Multi-Machine Cluster Orchestrator Tests

Covers:
1. Node registration and retrieval
2. Heartbeat tracking and timestamp updates
3. Workload rebalancing partitions domains and daily cap
4. Dead node auto-detection and graceful redistribution
5. Cluster overview metrics aggregation
6. State persistence across restarts
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

import cluster_manager
from cluster_manager import ClusterManager, ClusterNode


def test_cluster_node_registration():
    """Registering nodes creates tracked entries in the manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_state = cluster_manager.CLUSTER_STATE_PATH
        cluster_manager.CLUSTER_STATE_PATH = Path(tmpdir) / "state.json"
        try:
            mgr = ClusterManager(cfg={"scheduler": {"daily_cap": 2000}})
            n1 = mgr.register_node("vps_us_1", host="104.21.5.1", port=5050, role="worker")
            assert n1.node_id == "vps_us_1"
            assert n1.status == "online"
            assert "vps_us_1" in mgr.nodes
            print("  [OK] Node registration verified")
        finally:
            cluster_manager.CLUSTER_STATE_PATH = orig_state


def test_cluster_heartbeat_updates():
    """Heartbeat updates session counts, healthy proxies, and last_heartbeat timestamp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_state = cluster_manager.CLUSTER_STATE_PATH
        cluster_manager.CLUSTER_STATE_PATH = Path(tmpdir) / "state.json"
        try:
            mgr = ClusterManager()
            mgr.register_node("vps_sg_1", host="128.199.1.1", port=5050, role="worker")

            success = mgr.record_heartbeat("vps_sg_1", sessions_today=150, healthy_proxies=24)
            assert success
            node = mgr.nodes["vps_sg_1"]
            assert node.sessions_today == 150
            assert node.healthy_proxies == 24
            assert node.is_alive

            # Unknown node heartbeat returns False
            assert not mgr.record_heartbeat("nonexistent_node")
            print("  [OK] Heartbeat updates verified")
        finally:
            cluster_manager.CLUSTER_STATE_PATH = orig_state


def test_cluster_workload_rebalance():
    """Workload partitions domains and daily_cap evenly across active worker nodes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_state = cluster_manager.CLUSTER_STATE_PATH
        cluster_manager.CLUSTER_STATE_PATH = Path(tmpdir) / "state.json"
        try:
            mgr = ClusterManager(cfg={"scheduler": {"daily_cap": 1500}})
            mgr.register_node("worker_1", host="1.1.1.1", port=5050, role="worker")
            mgr.register_node("worker_2", host="2.2.2.2", port=5050, role="worker")
            mgr.register_node("worker_3", host="3.3.3.3", port=5050, role="worker")

            assignments = mgr.rebalance_workload(domains=["d1.com", "d2.com", "d3.com", "d4.com", "d5.com", "d6.com"])
            assert len(assignments) == 3
            # 1500 total / 3 workers = 500 per worker
            for nid, alloc in assignments.items():
                assert alloc["daily_cap"] == 500
                assert len(alloc["domains"]) == 2  # 6 domains / 3 workers = 2 each

            print("  [OK] Workload sharding verified: 3 workers x 500 cap, 2 domains each")
        finally:
            cluster_manager.CLUSTER_STATE_PATH = orig_state


def test_cluster_dead_node_failover():
    """Dead node (>120s timeout) is excluded from active pool and its load redistributed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_state = cluster_manager.CLUSTER_STATE_PATH
        cluster_manager.CLUSTER_STATE_PATH = Path(tmpdir) / "state.json"
        try:
            mgr = ClusterManager(cfg={"scheduler": {"daily_cap": 1000}, "cluster": {"heartbeat_timeout_s": 10.0}})
            mgr.register_node("worker_live", host="1.1.1.1", role="worker")
            mgr.register_node("worker_dying", host="2.2.2.2", role="worker")

            # Simulate worker_dying stopping heartbeats
            mgr.nodes["worker_dying"].last_heartbeat = time.time() - 50.0

            active = mgr.get_active_workers()
            assert len(active) == 1
            assert active[0].node_id == "worker_live"

            # Rebalance should assign 100% capacity to the live worker
            assignments = mgr.rebalance_workload(domains=["a.com", "b.com"])
            assert "worker_live" in assignments
            assert assignments["worker_live"]["daily_cap"] == 1000
            assert len(assignments["worker_live"]["domains"]) == 2
            print("  [OK] Dead node failover rebalanced 100% load to live worker")
        finally:
            cluster_manager.CLUSTER_STATE_PATH = orig_state


def test_cluster_overview_and_state_persistence():
    """Overview aggregates cluster stats and state persists to disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_state = cluster_manager.CLUSTER_STATE_PATH
        cluster_manager.CLUSTER_STATE_PATH = Path(tmpdir) / "cluster_state.json"
        try:
            mgr = ClusterManager(cfg={"scheduler": {"daily_cap": 1000}})
            mgr.register_node("n_alpha", host="1.1.1.1", role="worker")
            mgr.record_heartbeat("n_alpha", sessions_today=85, healthy_proxies=12)

            overview = mgr.get_cluster_overview()
            assert overview["total_nodes"] == 1
            assert overview["total_sessions_today"] == 85
            assert overview["total_healthy_proxies"] == 12

            # Reload manager from disk
            mgr2 = ClusterManager()
            assert "n_alpha" in mgr2.nodes
            assert mgr2.nodes["n_alpha"].sessions_today == 85
            print("  [OK] Cluster overview and state persistence verified")
        finally:
            cluster_manager.CLUSTER_STATE_PATH = orig_state


if __name__ == "__main__":
    test_cluster_node_registration()
    test_cluster_heartbeat_updates()
    test_cluster_workload_rebalance()
    test_cluster_dead_node_failover()
    test_cluster_overview_and_state_persistence()
    print("\nAll cluster manager tests PASSED!")
