"""
push_foundation.py — Layer 6: Service Workers & Idempotent Push Collector Injector

Deploys clean, zero-conflict Web Push foundation files across all 10 publisher sites:
1. `/OneSignalSDKWorker.js` — Official OneSignal Web SDK v16 Service Worker
2. `/push-sw.js` — Native W3C Push API Service Worker (`push`, `notificationclick`, `install`, `activate`)
   * Writes clean standalone `/sw.js` without any external third-party dependencies
3. Idempotent `<!-- PUSH_FOUNDATION_START --> ... <!-- PUSH_FOUNDATION_END -->` collector `<script>`
   injected cleanly before `</body>` with ZERO `<div>` drift and ZERO private key leakage.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
from typing import Any, Optional

import yaml

from adsterra_links import ADSTERRA_SCRIPTS, _normalize_domain_key
from inject_display_banners import _div_balance, _should_skip_file, deploy_cloudflare_sites
import push_manager
import vapid_keys

ROOT_DIR = pathlib.Path(__file__).resolve().parent
SITES_DIR = ROOT_DIR / "sites"
CONFIG_PATH = ROOT_DIR / "config.yaml"

PUSH_MARKER_START = "<!-- PUSH_FOUNDATION_START -->"
PUSH_MARKER_END = "<!-- PUSH_FOUNDATION_END -->"

KNOWN_SITE_DOMAINS: dict[str, str] = {
    short.lower(): f"{short.lower()}.com" for short in ADSTERRA_SCRIPTS
}

_BLOCK_RE = re.compile(
    re.escape(PUSH_MARKER_START) + r".*?" + re.escape(PUSH_MARKER_END),
    re.DOTALL,
)
_BODY_CLOSE_RE = re.compile(r"</body>", re.IGNORECASE)

ONESIGNAL_SW_JS = 'importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js");\n'

NATIVE_PUSH_SW_JS = """/* Layer 6: W3C Web Push Service Worker (Collect-Only Safe Foundation) */
self.addEventListener("install", function(event) {
  self.skipWaiting();
});

self.addEventListener("activate", function(event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", function(event) {
  if (!event.data) return;
  let data = {};
  try {
    data = event.data.json();
  } catch (e) {
    data = { title: "Latest Update", body: event.data.text() || "" };
  }
  const title = data.title || "Financial & Telecom Update";
  const options = {
    body: data.body || data.message || "New guide published.",
    icon: data.icon || "/favicon.ico",
    data: { url: data.url || "/" }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function(event) {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.openWindow(targetUrl));
});
"""


def _read_cfg(cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if cfg is not None:
        return cfg
    if CONFIG_PATH.is_file():
        try:
            return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {}


def _clean_domain(domain_or_key: str) -> str:
    short = _normalize_domain_key(domain_or_key)
    return KNOWN_SITE_DOMAINS.get(short, f"{short}.com" if short else "loanraaj.com")


def render_push_script_block(
    domain_or_key: str,
    cfg: Optional[dict[str, Any]] = None,
    vapid_public_key: Optional[str] = None,
    onesignal_app_id: Optional[str] = None,
) -> str:
    """
    Build idempotent `<script>` block for Layer 6 Push Notification collection.
    Embeds ONLY public VAPID `applicationServerKey` + optional public OneSignal App ID.
    Never embeds private keys or secret API tokens.
    """
    loaded_cfg = _read_cfg(cfg)
    pn_cfg = loaded_cfg.get("push_notifications", {}) or {}
    if not bool(pn_cfg.get("enabled", True)):
        return f"{PUSH_MARKER_START}\n<!-- Push Notification collection disabled in config.yaml -->\n{PUSH_MARKER_END}"

    clean_dom = _clean_domain(domain_or_key)
    if vapid_public_key is None:
        vapid_state_path = pn_cfg.get("vapid_keys_path") or vapid_keys.DEFAULT_VAPID_STATE_PATH
        vapid_subject = pn_cfg.get("vapid_subject") or vapid_keys.DEFAULT_VAPID_SUBJECT
        pub_key = vapid_keys.load_or_create_vapid_keys(
            state_path=vapid_state_path,
            subject=vapid_subject,
        )["public_key"]
    else:
        pub_key = str(vapid_public_key)

    if onesignal_app_id is None:
        os_client = push_manager.OneSignalPushClient(cfg=loaded_cfg)
        app_id = os_client.get_app_id(clean_dom)
    else:
        app_id = str(onesignal_app_id).strip()

    collect_only = bool(pn_cfg.get("collect_only", True))
    delay_ms = int(float(pn_cfg.get("min_delay_s", 7.0)) * 1000)

    pub_cfg = {
        "domain": clean_dom,
        "vapidPublicKey": pub_key,
        "onesignalAppId": app_id,
        "provider": "onesignal+vapid" if app_id else "vapid_local",
        "collectOnly": collect_only,
        "promptDelayMs": max(3000, delay_ms),
    }
    cfg_json = json.dumps(pub_cfg, separators=(",", ":"))

    return (
        f"{PUSH_MARKER_START}\n"
        f"<script>\n"
        f"window.__ADSTERRA_PUSH__ = {cfg_json};\n"
        f"(function() {{\n"
        f"  try {{\n"
        f"    const cfg = window.__ADSTERRA_PUSH__;\n"
        f"    if (!('Notification' in window) || !('serviceWorker' in navigator)) return;\n"
        f"    function urlB64ToUint8(b64) {{\n"
        f"      const pad = '='.repeat((4 - (b64.length % 4)) % 4);\n"
        f"      const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));\n"
        f"      const out = new Uint8Array(raw.length);\n"
        f"      for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);\n"
        f"      return out;\n"
        f"    }}\n"
        f"    async function collectVapidSubscription() {{\n"
        f"      if (!cfg.vapidPublicKey) return null;\n"
        f"      const reg = await navigator.serviceWorker.register('/push-sw.js', {{ scope: '/' }});\n"
        f"      if (!reg || !reg.pushManager) return null;\n"
        f"      let sub = await reg.pushManager.getSubscription();\n"
        f"      if (!sub && Notification.permission === 'granted') {{\n"
        f"        try {{\n"
        f"          sub = await reg.pushManager.subscribe({{ userVisibleOnly: true, applicationServerKey: urlB64ToUint8(cfg.vapidPublicKey) }});\n"
        f"        }} catch (_e) {{}}\n"
        f"      }}\n"
        f"      if (sub && sub.toJSON) {{\n"
        f"        const j = sub.toJSON();\n"
        f"        const rec = {{ provider: cfg.provider, endpoint: j.endpoint || sub.endpoint || '', p256dh: (j.keys && j.keys.p256dh) || '', auth: (j.keys && j.keys.auth) || '', collectOnly: cfg.collectOnly }};\n"
        f"        window.__PUSH_SUBSCRIPTION__ = rec;\n"
        f"        try {{ localStorage.setItem('adsterra_push_sub', JSON.stringify(rec)); }} catch (_s) {{}}\n"
        f"      }} else {{\n"
        f"        const tryOptIn = function() {{\n"
        f"          try {{\n"
        f"            if (sessionStorage.getItem('adsterra_push_prompted') || Notification.permission !== 'default' || window.scrollY < 200) return;\n"
        f"            sessionStorage.setItem('adsterra_push_prompted', '1');\n"
        f"            window.removeEventListener('scroll', tryOptIn);\n"
        f"            Notification.requestPermission().then(function(p) {{\n"
        f"              if (p === 'granted') collectVapidSubscription().catch(function() {{}});\n"
        f"            }}).catch(function() {{}});\n"
        f"          }} catch (_p) {{}}\n"
        f"        }};\n"
        f"        setTimeout(function() {{ window.addEventListener('scroll', tryOptIn, {{ passive: true }}); }}, cfg.promptDelayMs || 9000);\n"
        f"      }}\n"
        f"      return reg;\n"
        f"    }}\n"
        f"    if (cfg.onesignalAppId) {{\n"
        f"      window.OneSignalDeferred = window.OneSignalDeferred || [];\n"
        f"      window.OneSignalDeferred.push(async function(OneSignal) {{\n"
        f"        await OneSignal.init({{ appId: cfg.onesignalAppId, serviceWorkerPath: '/OneSignalSDKWorker.js', serviceWorkerParam: {{ scope: '/' }}, allowLocalhostAsSecureOrigin: true }});\n"
        f"        if (OneSignal.User && OneSignal.User.PushSubscription) {{\n"
        f"          OneSignal.User.PushSubscription.addEventListener('change', function(ev) {{\n"
        f"            const cur = ev && ev.current ? ev.current : {{}};\n"
        f"            window.__PUSH_SUBSCRIPTION__ = {{ provider: 'onesignal', subscription_id: cur.id || '', endpoint: cur.token || '', collectOnly: cfg.collectOnly }};\n"
        f"          }});\n"
        f"        }}\n"
        f"      }});\n"
        f"      const osScript = document.createElement('script');\n"
        f"      osScript.src = 'https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js';\n"
        f"      osScript.defer = true;\n"
        f"      document.head.appendChild(osScript);\n"
        f"    }} else {{\n"
        f"      collectVapidSubscription().catch(function() {{}});\n"
        f"    }}\n"
        f"  }} catch (_err) {{}}\n"
        f"}})();\n"
        f"</script>\n"
        f"{PUSH_MARKER_END}"
    )


def inject_push_html_content(
    html: str,
    domain: str,
    cfg: Optional[dict[str, Any]] = None,
    vapid_public_key: Optional[str] = None,
    onesignal_app_id: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    """Inject or update Layer 6 Push Foundation markers before `</body>` with zero `<div>` drift."""
    orig_balance = _div_balance(html)
    block = render_push_script_block(
        domain,
        cfg=cfg,
        vapid_public_key=vapid_public_key,
        onesignal_app_id=onesignal_app_id,
    )

    if PUSH_MARKER_START in html and PUSH_MARKER_END in html:
        updated = _BLOCK_RE.sub(lambda _m: block, html, count=1)
        action = "updated" if updated != html else "unchanged"
    else:
        body_m = _BODY_CLOSE_RE.search(html)
        if not body_m:
            return html, {"changed": False, "action": "skipped_no_body"}
        pos = body_m.start()
        updated = html[:pos] + f"\n    {block}\n" + html[pos:]
        action = "inserted"

    new_balance = _div_balance(updated)
    if new_balance != orig_balance:
        raise ValueError(f"Refusing push write for {domain}: <div> balance drifted ({orig_balance} -> {new_balance})")

    return updated, {"changed": updated != html, "action": action}


def write_site_service_workers(site_dir: pathlib.Path, dry_run: bool = False) -> dict[str, str]:
    """
    Write `/push-sw.js` and `/OneSignalSDKWorker.js` into `site_dir`.
    Clean local `/sw.js` maintained without third-party dependencies.
    """
    statuses: dict[str, str] = {}
    targets = {
        "push-sw.js": NATIVE_PUSH_SW_JS,
        "OneSignalSDKWorker.js": ONESIGNAL_SW_JS,
    }
    for fname, content in targets.items():
        fpath = site_dir / fname
        if fpath.is_file():
            existing = fpath.read_text(encoding="utf-8", errors="replace")
            if existing == content:
                statuses[fname] = "unchanged"
                continue
            status = "updated"
        else:
            status = "created"
        if not dry_run:
            fpath.write_text(content, encoding="utf-8", newline="\n")
        statuses[fname] = status
    return statuses


def inject_push_all_sites(
    sites_dir: pathlib.Path = SITES_DIR,
    domain_filter: Optional[str] = None,
    dry_run: bool = False,
    cfg: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Ensure all canonical sites carry `/push-sw.js`, `/OneSignalSDKWorker.js`, and push script block."""
    loaded_cfg = _read_cfg(cfg)
    pn_cfg = loaded_cfg.get("push_notifications", {}) or {}
    vapid_state_path = pn_cfg.get("vapid_keys_path") or vapid_keys.DEFAULT_VAPID_STATE_PATH
    vapid_subject = pn_cfg.get("vapid_subject") or vapid_keys.DEFAULT_VAPID_SUBJECT
    pub_key = vapid_keys.load_or_create_vapid_keys(
        state_path=vapid_state_path,
        subject=vapid_subject,
    )["public_key"]
    os_client = push_manager.OneSignalPushClient(cfg=loaded_cfg)

    target_short = _normalize_domain_key(domain_filter) if domain_filter else None
    target_dom = KNOWN_SITE_DOMAINS.get(target_short) if target_short else None
    if domain_filter and not target_dom:
        raise ValueError(f"Unknown domain filter: {domain_filter!r}")

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "vapid_public_key": pub_key,
        "onesignal_configured": os_client.is_configured(),
        "sites_processed": 0,
        "files_scanned": 0,
        "files_updated": 0,
        "files_inserted": 0,
        "files_unchanged": 0,
        "files_skipped": 0,
        "service_workers": {},
        "affected_site_ids": [],
        "errors": [],
    }

    if not sites_dir.exists():
        return summary

    affected: set[str] = set()
    for folder in sorted(sites_dir.iterdir()):
        if not folder.is_dir():
            continue
        clean = folder.name.strip().lower()
        short = clean[:-4] if clean.endswith(".com") else clean
        domain = KNOWN_SITE_DOMAINS.get(short)
        if not domain:
            continue
        if target_dom and domain != target_dom:
            continue

        summary["sites_processed"] += 1
        sw_res = write_site_service_workers(folder, dry_run=dry_run)
        summary["service_workers"][domain] = sw_res
        if any(v in ("created", "updated") for v in sw_res.values()):
            affected.add(short)

        app_id = os_client.get_app_id(domain)
        for html_file in sorted(folder.rglob("*.html")):
            if _should_skip_file(html_file):
                summary["files_skipped"] += 1
                continue

            summary["files_scanned"] += 1
            try:
                with open(html_file, "r", encoding="utf-8", errors="replace", newline="") as f:
                    orig = f.read()
                updated, meta = inject_push_html_content(
                    orig,
                    domain,
                    cfg=loaded_cfg,
                    vapid_public_key=pub_key,
                    onesignal_app_id=app_id,
                )
                act = meta.get("action")
                if act == "inserted":
                    summary["files_inserted"] += 1
                elif act == "updated":
                    summary["files_updated"] += 1
                elif act == "unchanged":
                    summary["files_unchanged"] += 1
                else:
                    summary["files_skipped"] += 1

                if meta.get("changed"):
                    affected.add(short)
                    if not dry_run:
                        with open(html_file, "w", encoding="utf-8", newline="") as f:
                            f.write(updated)
            except Exception as exc:
                summary["errors"].append(f"{html_file}: {exc}")

    summary["affected_site_ids"] = sorted(affected)
    return summary


def audit_sites_push_coverage(sites_dir: pathlib.Path = SITES_DIR) -> dict[str, Any]:
    """Audit all 10 sites for push collector presence, SW files, and zero leaked private keys."""
    domains_report: list[dict[str, Any]] = []
    ready_count = 0
    leak_detected = False

    for short in sorted(KNOWN_SITE_DOMAINS):
        domain = KNOWN_SITE_DOMAINS[short]
        site_dir = sites_dir / domain
        idx = site_dir / "index.html"
        has_idx = idx.is_file()
        idx_txt = idx.read_text(encoding="utf-8", errors="replace") if has_idx else ""
        has_collector = PUSH_MARKER_START in idx_txt and "window.__ADSTERRA_PUSH__" in idx_txt
        has_push_sw = (site_dir / "push-sw.js").is_file()
        has_os_sw = (site_dir / "OneSignalSDKWorker.js").is_file()
        has_secret_leak = any(
            tok in idx_txt for tok in ("BEGIN PRIVATE KEY", '"private_key"', '"rest_api_key"')
        )
        if has_secret_leak:
            leak_detected = True

        ready = has_collector and has_push_sw and has_os_sw and not has_secret_leak
        if ready:
            ready_count += 1

        domains_report.append(
            {
                "domain": domain,
                "site_id": short,
                "has_collector": has_collector,
                "has_push_sw": has_push_sw,
                "has_onesignal_sw": has_os_sw,
                "local_sw_clean": (site_dir / "sw.js").is_file(),
                "secret_leak": has_secret_leak,
                "ready": ready,
            }
        )

    return {
        "total_domains": len(KNOWN_SITE_DOMAINS),
        "ready_domains": ready_count,
        "all_ready": ready_count == len(KNOWN_SITE_DOMAINS) and not leak_detected,
        "secret_leak_detected": leak_detected,
        "domains": domains_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Layer 6 Push Notification Foundation Injector & Audit")
    parser.add_argument("--dry-run", action="store_true", help="Scan without writing files")
    parser.add_argument("--domain", type=str, default=None, help="Filter single domain or site_id")
    parser.add_argument("--deploy", action="store_true", help="Deploy updated sites to Cloudflare Pages")
    parser.add_argument("--audit", action="store_true", help="Audit 10-site push readiness")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    if args.audit:
        res = audit_sites_push_coverage()
        print(json.dumps(res, indent=2))
        return 0 if res["all_ready"] else 1

    res = inject_push_all_sites(domain_filter=args.domain, dry_run=args.dry_run)
    if args.deploy and not args.dry_run and not res["errors"]:
        deploy_ids = [_normalize_domain_key(args.domain)] if args.domain else sorted(KNOWN_SITE_DOMAINS)
        res["deploy_results"] = deploy_cloudflare_sites(deploy_ids)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        mode = "DRY-RUN" if args.dry_run else "APPLIED"
        print(
            f"[push_foundation:{mode}] sites={res['sites_processed']} scanned={res['files_scanned']} "
            f"inserted={res['files_inserted']} updated={res['files_updated']} errors={len(res['errors'])}"
        )
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
