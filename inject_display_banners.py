"""
Layer 1 Display Banner Idempotent Injector & Cloudflare Pages Deployer.

Ensures every existing HTML page across all 10 publisher sites has:
  1. `ADSTERRA_BANNER_CSS` injected inside `<style>...</style>`.
  2. `728x90` leaderboard slot marker below `<nav>` (or `</header>` if `<nav>` is inside `<header>`).
  3. `300x250` medium rectangle slot marker inside `<aside>` sidebar.
  4. `native` mid-article slot marker inside editorial `.post-content` / `.entry-content`.

Unconfigured slots emit only invisible HTML comment markers so zero dummy UI boxes
or fake keys appear on live pages. Re-running updates all markers in-place.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
from typing import Any

from adsterra_links import (
    ADSTERRA_BANNER_CSS,
    ADSTERRA_SCRIPTS,
    _normalize_domain_key,
    render_display_banner,
)

ROOT_DIR = pathlib.Path(__file__).resolve().parent
SITES_DIR = ROOT_DIR / "sites"

BANNER_CSS_MARKER = "/* Adsterra Responsive Display Banner & Native Slots (Layer 1) */"
SLOT_MARKER_START = "<!-- ADSTERRA_SLOT:{slot} -->"
SLOT_MARKER_END = "<!-- /ADSTERRA_SLOT:{slot} -->"

KNOWN_SITE_IDS: dict[str, str] = {
    short.lower(): f"{short.lower()}.com" for short in ADSTERRA_SCRIPTS
}

_STYLE_CLOSE_RE = re.compile(r"</style>", re.IGNORECASE)
_NAV_CLOSE_RE = re.compile(r"</nav>", re.IGNORECASE)
_HEADER_CLOSE_RE = re.compile(r"</header>", re.IGNORECASE)
_ASIDE_OPEN_RE = re.compile(r"<aside\b[^>]*>", re.IGNORECASE)
_ENTRY_BODY_RE = re.compile(
    r'<div\s+class="(?:post-content|entry-content|article-body)"[^>]*>',
    re.IGNORECASE,
)


def _load_env_vars() -> dict[str, str]:
    """Load `.env` variables safely without external dependencies."""
    env = os.environ.copy()
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in env:
            env[k] = v
    return env


def resolve_site_domain_from_folder(folder_name: str) -> str | None:
    """Map `sites/<folder>` (`karzseva` or `karzseva.com`) to canonical domain or None."""
    clean = folder_name.strip().lower()
    if clean.endswith(".com"):
        clean = clean[:-4]
    return KNOWN_SITE_IDS.get(clean)


def _div_balance(html: str) -> int:
    """Return open `<div>` count minus closing `</div>` count."""
    lower = html.lower()
    return lower.count("<div") - lower.count("</div>")


def _inject_css(html: str) -> tuple[str, bool]:
    """Ensure `ADSTERRA_BANNER_CSS` exists once before the first `</style>`."""
    if BANNER_CSS_MARKER in html:
        return html, False
    match = _STYLE_CLOSE_RE.search(html)
    if not match:
        return html, False
    idx = match.start()
    updated = html[:idx] + "\n" + ADSTERRA_BANNER_CSS.strip() + "\n" + html[idx:]
    return updated, True


def _replace_slot_markers(html: str, slot: str, rendered_block: str) -> tuple[str, bool]:
    """Replace existing `<!-- ADSTERRA_SLOT:slot -->...<!-- /ADSTERRA_SLOT:slot -->` span."""
    start_marker = SLOT_MARKER_START.format(slot=slot)
    end_marker = SLOT_MARKER_END.format(slot=slot)
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    if not pattern.search(html):
        return html, False
    updated = pattern.sub(lambda _m: rendered_block, html, count=1)
    return updated, updated != html


def _insert_728x90(html: str, rendered_block: str) -> tuple[str, str]:
    """Insert or update the 728x90 top leaderboard slot."""
    replaced, changed = _replace_slot_markers(html, "728x90", rendered_block)
    if SLOT_MARKER_START.format(slot="728x90") in html:
        return replaced, "updated" if changed else "unchanged"

    snippet = f'\n    <div class="container">{rendered_block}</div>\n'
    nav_m = _NAV_CLOSE_RE.search(html)
    hdr_m = _HEADER_CLOSE_RE.search(html)

    # If </nav> sits inside <header>...</header>, insert right after </header>
    if hdr_m and (not nav_m or hdr_m.start() > nav_m.start()):
        pos = hdr_m.end()
        return html[:pos] + snippet + html[pos:], "inserted"

    if nav_m:
        pos = nav_m.end()
        return html[:pos] + snippet + html[pos:], "inserted"

    return html, "skipped_no_anchor"


def _insert_300x250(html: str, rendered_block: str) -> tuple[str, str]:
    """Insert or update the 300x250 sidebar slot."""
    replaced, changed = _replace_slot_markers(html, "300x250", rendered_block)
    if SLOT_MARKER_START.format(slot="300x250") in html:
        return replaced, "updated" if changed else "unchanged"

    if not _ASIDE_OPEN_RE.search(html):
        return html, "skipped_no_aside"

    # Match existing site_templates.py placement directly above Interactive Tool Widget
    for comment_anchor in (
        "<!-- Interactive Tool Widget -->",
        "<!-- Live Interactive EMI Calculator -->",
        "<!-- EMI Calculator -->",
    ):
        idx = html.find(comment_anchor)
        if idx != -1:
            insertion = f"{rendered_block}\n        "
            return html[:idx] + insertion + html[idx:], "inserted"

    # Fallback: insert immediately after <aside ...>
    aside_m = _ASIDE_OPEN_RE.search(html)
    if aside_m:
        pos = aside_m.end()
        return html[:pos] + f"\n        {rendered_block}\n" + html[pos:], "inserted"

    return html, "skipped_no_anchor"


def _insert_native(html: str, rendered_block: str) -> tuple[str, str]:
    """Insert or update the mid-article native banner slot on article pages."""
    replaced, changed = _replace_slot_markers(html, "native", rendered_block)
    if SLOT_MARKER_START.format(slot="native") in html:
        return replaced, "updated" if changed else "unchanged"

    body_m = _ENTRY_BODY_RE.search(html)
    if not body_m:
        return html, "skipped_non_article"

    body_start = body_m.end()
    # Bound search inside the main article area so footer/sidebar <p> tags are ignored
    end_bound = len(html)
    for stop_tok in ('class="author-card"', 'class="faq-section"', "</article>"):
        pos = html.find(stop_tok, body_start)
        if pos != -1 and pos < end_bound:
            end_bound = pos

    segment = html[body_start:end_bound]
    p_closes = [m.end() for m in re.finditer(r"</p>", segment, re.IGNORECASE)]

    if len(p_closes) >= 2:
        mid_rel = p_closes[len(p_closes) // 2 - 1]
        insert_pos = body_start + mid_rel
        return html[:insert_pos] + f"\n{rendered_block}\n" + html[insert_pos:], "inserted"

    if end_bound < len(html):
        tag_start = html.rfind("<", body_start, end_bound + 1)
        insert_pos = tag_start if tag_start != -1 else end_bound
        return html[:insert_pos] + f"\n{rendered_block}\n" + html[insert_pos:], "inserted"

    return html, "skipped_no_anchor"


def inject_html_content(html: str, domain: str) -> tuple[str, dict[str, Any]]:
    """Inject CSS and all 3 display banner slots idempotently into one HTML document."""
    orig_balance = _div_balance(html)
    updated = html

    updated, css_added = _inject_css(updated)

    b728 = render_display_banner(domain, "728x90", wrap_markers=True)
    b300 = render_display_banner(domain, "300x250", wrap_markers=True)
    bnat = render_display_banner(domain, "native", wrap_markers=True)

    updated, st_728 = _insert_728x90(updated, b728)
    updated, st_300 = _insert_300x250(updated, b300)
    updated, st_nat = _insert_native(updated, bnat)

    new_balance = _div_balance(updated)
    if new_balance != orig_balance:
        raise ValueError(
            f"Refusing write for {domain}: <div> balance drifted "
            f"({orig_balance} -> {new_balance})"
        )

    return updated, {
        "changed": updated != html,
        "css_added": css_added,
        "slots": {
            "728x90": st_728,
            "300x250": st_300,
            "native": st_nat,
        },
    }


def _should_skip_file(path: pathlib.Path) -> bool:
    if path.name.lower().startswith("google") and path.suffix.lower() == ".html":
        return True
    if "layouts" in [p.lower() for p in path.parts]:
        return True
    return False


def inject_all_sites(
    sites_dir: pathlib.Path = SITES_DIR,
    domain_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan all HTML pages under `sites_dir` and inject/update display banner slots."""
    target_short = _normalize_domain_key(domain_filter) if domain_filter else None
    target_dom = KNOWN_SITE_IDS.get(target_short) if target_short else None
    if domain_filter and not target_dom:
        raise ValueError(f"Unknown network domain filter: {domain_filter!r}")

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "domain_filter": target_dom,
        "files_scanned": 0,
        "files_updated": 0,
        "files_skipped": 0,
        "errors": [],
        "slot_actions": {
            "728x90": {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0},
            "300x250": {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0},
            "native": {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0},
        },
        "affected_site_ids": set(),
    }

    if not sites_dir.exists():
        return summary

    for folder in sorted(sites_dir.iterdir()):
        if not folder.is_dir():
            continue
        domain = resolve_site_domain_from_folder(folder.name)
        if not domain:
            continue
        if target_dom and domain != target_dom:
            continue

        site_id = domain.replace(".com", "")
        for html_file in sorted(folder.rglob("*.html")):
            if _should_skip_file(html_file):
                summary["files_skipped"] += 1
                continue

            summary["files_scanned"] += 1
            try:
                with open(html_file, "r", encoding="utf-8", errors="replace", newline="") as f:
                    orig = f.read()
                updated, meta = inject_html_content(orig, domain)
                for slot_key, action in meta["slots"].items():
                    bucket = action if action in ("inserted", "updated", "unchanged") else "skipped"
                    summary["slot_actions"][slot_key][bucket] += 1

                if meta["changed"]:
                    summary["files_updated"] += 1
                    summary["affected_site_ids"].add(site_id)
                    if not dry_run:
                        with open(html_file, "w", encoding="utf-8", newline="") as f:
                            f.write(updated)
            except Exception as exc:
                summary["errors"].append(f"{html_file}: {exc}")

    summary["affected_site_ids"] = sorted(summary["affected_site_ids"])
    return summary


def deploy_cloudflare_sites(site_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Deploy `sites/<site_id>` directories to Cloudflare Pages via Wrangler CLI."""
    targets = site_ids or sorted(KNOWN_SITE_IDS.keys())
    env = _load_env_vars()
    results: list[dict[str, Any]] = []

    for site_id in targets:
        site_dir = SITES_DIR / site_id
        if not site_dir.is_dir():
            results.append({"site_id": site_id, "ok": False, "error": f"Missing dir: {site_dir}"})
            continue
        cmd = [
            "npx.cmd",
            "wrangler",
            "pages",
            "deploy",
            str(site_dir),
            f"--project-name={site_id}",
            "--branch=main",
            "--commit-dirty=true",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT_DIR),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            out_txt = proc.stdout or ""
            err_txt = proc.stderr or ""
            results.append(
                {
                    "site_id": site_id,
                    "ok": proc.returncode == 0,
                    "returncode": proc.returncode,
                    "tail": (out_txt + "\n" + err_txt).strip()[-350:],
                }
            )
        except Exception as exc:
            results.append({"site_id": site_id, "ok": False, "error": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotently inject Layer 1 Adsterra Display Banner slots into sites/ HTML."
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files")
    parser.add_argument("--domain", type=str, default=None, help="Filter to a single domain or site_id")
    parser.add_argument("--deploy", action="store_true", help="Deploy to Cloudflare Pages after injection")
    parser.add_argument("--json", action="store_true", help="Output JSON summary")
    args = parser.parse_args()

    res = inject_all_sites(dry_run=args.dry_run, domain_filter=args.domain)
    if args.deploy and not args.dry_run and not res["errors"]:
        deploy_ids = (
            [_normalize_domain_key(args.domain)]
            if args.domain
            else sorted(KNOWN_SITE_IDS.keys())
        )
        res["deploy_results"] = deploy_cloudflare_sites(deploy_ids)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        mode = "DRY-RUN" if args.dry_run else "APPLIED"
        print(
            f"[inject_display_banners:{mode}] scanned={res['files_scanned']} "
            f"updated={res['files_updated']} skipped={res['files_skipped']} errors={len(res['errors'])}"
        )
        for slot_k, counts in res["slot_actions"].items():
            print(f"  slot={slot_k}: {counts}")
        if res["errors"]:
            for err in res["errors"][:10]:
                print(f"  ERROR: {err}")
        if "deploy_results" in res:
            for d in res["deploy_results"]:
                print(f"  deploy {d['site_id']}: ok={d['ok']}")

    return 1 if res["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
