"""
admin_ui/deploy_content_service.py — Service layer for Deploy Control and Content Workspace.
Handles Cloudflare edge deployment subprocess, single-flight guard, article corpus caching,
and path-safe article detail inspection.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parent.parent

KNOWN_DOMAINS = frozenset({
    "loanraaj.com",
    "rechargetak.com",
    "rechargepur.com",
    "tazaloan.com",
    "loankiseva.com",
    "karzseva.com",
    "loantau.com",
    "tazabhav.com",
    "tazarokda.com",
    "rechargekar.com",
})

# ---------------------------------------------------------------------------
# DEPLOYMENT CONTROL (Single-Flight Guard, Status & Subprocess Runner)
# ---------------------------------------------------------------------------

_DEPLOY_LOCK = threading.Lock()
_DEPLOY_STATUS: dict[str, Any] = {
    "running": False,
    "last_run": None,
    "last_result": None,
}


def get_deploy_status() -> dict[str, Any]:
    """Return the current deployment status."""
    return {
        "running": _DEPLOY_STATUS["running"],
        "last_run": _DEPLOY_STATUS["last_run"],
        "last_result": _DEPLOY_STATUS["last_result"],
    }


def run_deployment(domains_arg: Any = "all") -> tuple[int, dict[str, Any]]:
    """
    Execute deploy_all_pages.py with single-flight concurrency guard and hard timeout.
    Returns (status_code, json_payload).
    """
    # 1. Single-flight guard: Refuse concurrent invocations with 409
    if not _DEPLOY_LOCK.acquire(blocking=False):
        return 409, {
            "ok": False,
            "error": "A deployment is already running. Concurrent invocations are refused with 409.",
        }

    ran_domains: list[str] = []
    if domains_arg == "all" or not domains_arg:
        ran_domains = sorted(list(KNOWN_DOMAINS))
    elif isinstance(domains_arg, list):
        ran_domains = [str(d) for d in domains_arg if str(d) in KNOWN_DOMAINS]
        if not ran_domains:
            ran_domains = sorted(list(KNOWN_DOMAINS))
    else:
        ran_domains = sorted(list(KNOWN_DOMAINS))

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _DEPLOY_STATUS["running"] = True
    _DEPLOY_STATUS["last_run"] = now_iso

    try:
        # Timeout: 600s per domain, capped at reasonable total
        timeout_seconds = max(600, len(ran_domains) * 600)

        # Run deploy_all_pages.py as a subprocess
        cmd = [sys.executable, "deploy_all_pages.py"]
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        full_output = (stdout_text + "\n" + stderr_text).strip()
        tail = full_output[-400:] if len(full_output) > 400 else full_output

        success = (proc.returncode == 0)
        domain_status = "ok" if success else "fail"

        results = [
            {
                "domain": d,
                "status": domain_status,
                "tail": tail,
            }
            for d in ran_domains
        ]

        result_payload = {
            "ok": success,
            "ran": ran_domains,
            "results": results,
        }

        _DEPLOY_STATUS["last_result"] = result_payload
        return 200, result_payload

    except subprocess.TimeoutExpired:
        result_payload = {
            "ok": False,
            "ran": ran_domains,
            "results": [
                {
                    "domain": d,
                    "status": "fail",
                    "tail": "Deployment timed out after 600s per domain limit.",
                }
                for d in ran_domains
            ],
            "error": "Deployment timed out.",
        }
        _DEPLOY_STATUS["last_result"] = result_payload
        return 200, result_payload

    except Exception as exc:
        result_payload = {
            "ok": False,
            "ran": ran_domains,
            "results": [
                {
                    "domain": d,
                    "status": "fail",
                    "tail": f"[ERROR] Execution failed: {str(exc)}",
                }
                for d in ran_domains
            ],
            "error": str(exc),
        }
        _DEPLOY_STATUS["last_result"] = result_payload
        return 200, result_payload

    finally:
        _DEPLOY_STATUS["running"] = False
        _DEPLOY_LOCK.release()


# ---------------------------------------------------------------------------
# CONTENT WORKSPACE (Corpus Walking, 60s In-Memory Cache, Article Detail)
# ---------------------------------------------------------------------------

_CONTENT_CACHE: dict[str, Any] = {
    "timestamp": 0.0,
    "payload": None,
    "walk_count": 0,
}


def _walk_corpus() -> dict[str, Any]:
    """Walk sites/**/index.html to build articles and redirect stubs payload."""
    from scripts.seo_onpage_audit import get_all_article_paths, audit_article
    import content_quality_gate

    articles_list: list[dict[str, Any]] = []
    stubs_list: list[dict[str, Any]] = []

    # 1. Non-stub articles (57 published articles >= 3000 words)
    article_paths = get_all_article_paths(PROJECT_ROOT / "sites")
    for p in article_paths:
        try:
            rel = p.relative_to(PROJECT_ROOT / "sites")
            domain = rel.parts[0]
            slug = rel.parts[1]
            stat = p.stat()
            mtime_iso = datetime.datetime.fromtimestamp(stat.st_mtime, datetime.timezone.utc).isoformat()

            audit = audit_article(p)
            prose_words = audit.get("prose_words", 0)
            title = audit.get("title", slug)

            articles_list.append({
                "domain": domain,
                "slug": slug,
                "prose_words": prose_words,
                "title": title,
                "last_modified": mtime_iso,
                "is_stub": False,
                "destination": None,
            })
        except Exception:
            continue

    # 2. Redirect stubs (221 stubs from data/redirects_round20.json)
    r20_path = PROJECT_ROOT / "data" / "redirects_round20.json"
    if r20_path.exists():
        try:
            with open(r20_path, "r", encoding="utf-8") as f:
                r20_entries = json.load(f)
            for entry in r20_entries:
                domain = entry["domain"]
                from_slug = entry["from_slug"]
                to_slug = entry["to_slug"]

                stub_file = PROJECT_ROOT / "sites" / domain / from_slug / "index.html"
                mtime_iso = ""
                if stub_file.exists():
                    stat = stub_file.stat()
                    mtime_iso = datetime.datetime.fromtimestamp(stat.st_mtime, datetime.timezone.utc).isoformat()

                stubs_list.append({
                    "domain": domain,
                    "slug": from_slug,
                    "prose_words": 0,
                    "title": f"Redirect -> {to_slug}",
                    "last_modified": mtime_iso,
                    "is_stub": True,
                    "destination": to_slug,
                })
        except Exception:
            pass

    return {
        "ok": True,
        "articles": articles_list,
        "stubs": stubs_list,
        "all": articles_list + stubs_list,
        "count": len(articles_list),
        "stubs_count": len(stubs_list),
        "total": len(articles_list) + len(stubs_list),
        "domains": sorted(list(KNOWN_DOMAINS)),
    }


def get_articles_list() -> dict[str, Any]:
    """Return cached articles payload, invalidating after 60 seconds."""
    now = time.time()
    if _CONTENT_CACHE["payload"] is not None and (now - _CONTENT_CACHE["timestamp"]) < 60.0:
        return _CONTENT_CACHE["payload"]

    try:
        data = _walk_corpus()
        _CONTENT_CACHE["payload"] = data
        _CONTENT_CACHE["timestamp"] = now
        _CONTENT_CACHE["walk_count"] += 1
        return data
    except Exception as exc:
        # Return empty list gracefully, never a 500
        return {
            "ok": True,
            "articles": [],
            "stubs": [],
            "all": [],
            "count": 0,
            "stubs_count": 0,
            "total": 0,
            "domains": sorted(list(KNOWN_DOMAINS)),
            "error": str(exc),
        }


def get_article_detail(domain: str, slug: str) -> tuple[int, dict[str, Any]]:
    """
    Inspect article index.html returning title, meta description, H1, word count, H2 list, image count.
    Rejects unknown domains and path traversal with 400.
    """
    domain = (domain or "").strip()
    slug = (slug or "").strip().strip("/")

    # 1. Validate domain is one of the ten known domains
    if domain not in KNOWN_DOMAINS:
        return 400, {"ok": False, "error": f"Invalid domain '{domain}'. Must be one of the 10 known domains."}

    # 2. Strict path traversal guard: reject '..' or paths that resolve outside sites/<domain>
    if ".." in slug or ".." in domain or "\\" in slug:
        return 400, {"ok": False, "error": "Path traversal detected and rejected."}

    sites_root = (PROJECT_ROOT / "sites").resolve()
    domain_root = (sites_root / domain).resolve()
    target_dir = (domain_root / slug).resolve()

    try:
        if not target_dir.is_relative_to(domain_root):
            return 400, {"ok": False, "error": "Path traversal detected and rejected."}
    except ValueError:
        return 400, {"ok": False, "error": "Path traversal detected and rejected."}

    index_file = target_dir / "index.html"
    if not index_file.exists():
        return 404, {"ok": False, "error": f"Article not found at {domain}/{slug}"}

    try:
        from bs4 import BeautifulSoup
        from content_quality_gate import count_prose_words, is_redirect_stub

        html = index_file.read_text(encoding="utf-8", errors="ignore")
        if is_redirect_stub(html):
            m = re.search(r'url=([^">]+)', html, re.IGNORECASE)
            dest = m.group(1).strip() if m else ""
            return 200, {
                "ok": True,
                "domain": domain,
                "slug": slug,
                "title": f"Redirect -> {dest}",
                "meta_description": f"301 Redirect stub to {dest}",
                "h1": f"301 Redirect to {dest}",
                "word_count": 0,
                "h2_list": [],
                "image_count": 0,
                "is_stub": True,
                "destination": dest,
            }

        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.find("title")
        title = title_el.get_text(strip=True) if title_el else ""

        meta_el = soup.find("meta", attrs={"name": "description"})
        meta_desc = meta_el.get("content", "").strip() if meta_el else ""

        h1_el = soup.find("h1")
        h1 = h1_el.get_text(strip=True) if h1_el else ""

        pc = soup.find("div", class_="post-content") or soup.find("article") or soup
        h2_list = [re.sub(r"\s+", " ", h.get_text()).strip() for h in pc.find_all("h2")]

        imgs = pc.find_all("img")
        image_count = len(imgs)

        word_count = count_prose_words(html)

        return 200, {
            "ok": True,
            "domain": domain,
            "slug": slug,
            "title": title,
            "meta_description": meta_desc,
            "h1": h1,
            "word_count": word_count,
            "h2_list": h2_list,
            "image_count": image_count,
            "is_stub": False,
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def render_crm_shell_with_content(shell_html: str) -> str:
    """Inject content view and script into shell HTML without mutating shell.py."""
    from admin_ui.views.content import render_content_view
    content_html = render_content_view()
    if 'id="view-content"' not in shell_html:
        if "<footer" in shell_html:
            shell_html = shell_html.replace("<footer", content_html + "\n            <footer", 1)
        else:
            shell_html += content_html
    if "/crm-assets/js/crm-content.js" not in shell_html:
        shell_html = shell_html.replace("</body>", '    <script src="/crm-assets/js/crm-content.js"></script>\n  </body>')
    return shell_html

