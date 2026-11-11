"""merge_site_folders.py — Safely consolidate `sites/<site_id>` into canonical `sites/<site_id>.com`."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from network_registry import NETWORK_REGISTRY, get_canonical_site_dir

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ET.register_namespace("", SITEMAP_NS)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_sitemap_locs(xml_bytes: bytes) -> list[str]:
    text = xml_bytes.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
        locs: list[str] = []
        for elem in root.iter():
            if elem.tag.split("}")[-1] == "loc" and elem.text:
                locs.append(elem.text.strip())
        if locs:
            return locs
    except ET.ParseError:
        pass
    return [m.strip() for m in re.findall(r"<loc>(.*?)</loc>", text, flags=re.IGNORECASE | re.DOTALL) if m.strip()]


def _merge_sitemaps(src_xml: bytes, dst_xml: bytes) -> tuple[bytes, int]:
    """Union XML `<url>` entries by `<loc>`, keeping `dst_xml` entries and appending new `src_xml` URLs."""
    try:
        dst_root = ET.fromstring(dst_xml.decode("utf-8", errors="replace"))
        src_root = ET.fromstring(src_xml.decode("utf-8", errors="replace"))
    except ET.ParseError:
        dst_locs = set(_extract_sitemap_locs(dst_xml))
        src_text = src_xml.decode("utf-8", errors="replace")
        dst_text = dst_xml.decode("utf-8", errors="replace")
        new_blocks: list[str] = []
        for block in re.findall(r"<url\b[^>]*>.*?</url>", src_text, flags=re.IGNORECASE | re.DOTALL):
            loc_match = re.search(r"<loc>(.*?)</loc>", block, flags=re.IGNORECASE | re.DOTALL)
            if loc_match and loc_match.group(1).strip() not in dst_locs:
                dst_locs.add(loc_match.group(1).strip())
                new_blocks.append(block)
        if not new_blocks:
            return dst_xml, 0
        closing = "</urlset>"
        if closing in dst_text:
            merged_text = dst_text.replace(closing, "\n  " + "\n  ".join(new_blocks) + "\n" + closing)
            return merged_text.encode("utf-8"), len(new_blocks)
        return (dst_text + "\n" + "\n".join(new_blocks)).encode("utf-8"), len(new_blocks)

    seen_locs: set[str] = set()
    for url_el in dst_root:
        if url_el.tag.split("}")[-1] != "url":
            continue
        for child in url_el:
            if child.tag.split("}")[-1] == "loc" and child.text:
                seen_locs.add(child.text.strip())

    added = 0
    for url_el in src_root:
        if url_el.tag.split("}")[-1] != "url":
            continue
        loc_val = ""
        for child in url_el:
            if child.tag.split("}")[-1] == "loc" and child.text:
                loc_val = child.text.strip()
                break
        if loc_val and loc_val not in seen_locs:
            seen_locs.add(loc_val)
            dst_root.append(url_el)
            added += 1

    if added == 0:
        return dst_xml, 0

    ET.indent(dst_root, space="  ")
    serialized = ET.tostring(dst_root, encoding="utf-8", xml_declaration=True)
    if not serialized.endswith(b"\n"):
        serialized += b"\n"
    return serialized, added


def _merge_domain_pair(site_id: str, sites_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    src_dir = sites_dir / site_id
    dst_dir = get_canonical_site_dir(site_id, base_dir=sites_dir)
    report: dict[str, Any] = {
        "site_id": site_id,
        "src_dir": str(src_dir),
        "dst_dir": str(dst_dir),
        "status": "already_consolidated",
        "copied_new": 0,
        "identical": 0,
        "overwritten_newer": 0,
        "kept_dst_newer": 0,
        "sitemap_urls_added": 0,
        "copied_files": [],
        "kept_dst_files": [],
        "deleted_src": False,
    }

    if not src_dir.exists():
        return report

    if dst_dir.exists():
        try:
            if src_dir.is_symlink() or os.path.samefile(src_dir, dst_dir):
                raise RuntimeError(f"Refusing to delete {src_dir}: resolves to same directory as {dst_dir}")
        except OSError:
            pass

    src_files = sorted(p for p in src_dir.rglob("*") if p.is_file())
    expected_rels: list[Path] = []
    expected_sitemap_locs: list[str] = []

    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)

    for src_file in src_files:
        rel = src_file.relative_to(src_dir)
        expected_rels.append(rel)
        dst_file = dst_dir / rel
        src_bytes = src_file.read_bytes()

        if rel.as_posix() == "sitemap.xml":
            expected_sitemap_locs = _extract_sitemap_locs(src_bytes)

        if not dst_file.exists():
            report["copied_new"] += 1
            report["copied_files"].append(rel.as_posix())
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            continue

        dst_bytes = dst_file.read_bytes()
        if _sha256_bytes(src_bytes) == _sha256_bytes(dst_bytes):
            report["identical"] += 1
            continue

        if rel.as_posix() == "sitemap.xml":
            merged_bytes, added = _merge_sitemaps(src_bytes, dst_bytes)
            report["sitemap_urls_added"] += added
            if added > 0 and not dry_run:
                dst_file.write_bytes(merged_bytes)
            if added == 0:
                report["identical"] += 1
            continue

        if src_file.stat().st_mtime > dst_file.stat().st_mtime:
            report["overwritten_newer"] += 1
            report["copied_files"].append(rel.as_posix())
            if not dry_run:
                shutil.copy2(src_file, dst_file)
        else:
            report["kept_dst_newer"] += 1
            report["kept_dst_files"].append(rel.as_posix())

    if dry_run:
        report["status"] = "dry_run_planned"
        return report

    # Hard verification gate before deleting src_dir: every file and sitemap URL must exist in dst_dir.
    for rel in expected_rels:
        dst_file = dst_dir / rel
        if not dst_file.is_file():
            raise RuntimeError(f"Consolidation verification failed: missing {dst_file}")

    if expected_sitemap_locs:
        merged_locs = set(_extract_sitemap_locs((dst_dir / "sitemap.xml").read_bytes()))
        missing_locs = [loc for loc in expected_sitemap_locs if loc not in merged_locs]
        if missing_locs:
            raise RuntimeError(
                f"Sitemap merge verification failed for {site_id}: missing {len(missing_locs)} URLs (e.g. {missing_locs[0]})"
            )

    shutil.rmtree(src_dir)
    report["deleted_src"] = True
    report["status"] = "consolidated"
    return report


def consolidate_all_site_folders(sites_dir: str | Path = "sites", dry_run: bool = False) -> dict[str, Any]:
    """Consolidate all non-`.com` `sites/<site_id>` duplicates into `sites/<site_id>.com`."""
    root = Path(sites_dir)
    results = [_merge_domain_pair(site_id, root, dry_run=dry_run) for site_id in sorted(NETWORK_REGISTRY.keys())]
    totals = {
        "consolidated_domains": sum(1 for r in results if r["status"] == "consolidated"),
        "already_consolidated": sum(1 for r in results if r["status"] == "already_consolidated"),
        "copied_new": sum(r["copied_new"] for r in results),
        "identical": sum(r["identical"] for r in results),
        "overwritten_newer": sum(r["overwritten_newer"] for r in results),
        "kept_dst_newer": sum(r["kept_dst_newer"] for r in results),
        "sitemap_urls_added": sum(r["sitemap_urls_added"] for r in results),
        "deleted_src_dirs": sum(1 for r in results if r["deleted_src"]),
    }
    remaining = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    return {
        "sites_dir": str(root),
        "dry_run": dry_run,
        "totals": totals,
        "remaining_dirs": remaining,
        "results": results,
    }


def _main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Consolidate duplicate sites/<id> into canonical sites/<id>.com")
    parser.add_argument("--sites-dir", default="sites", help="Root sites directory (default: sites)")
    parser.add_argument("--dry-run", action="store_true", help="Plan consolidation without writing or deleting")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = parser.parse_args()

    summary = consolidate_all_site_folders(sites_dir=args.sites_dir, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"Sites dir: {summary['sites_dir']} | dry_run={summary['dry_run']}")
    for row in summary["results"]:
        print(
            f"  {row['site_id']:14s} -> status={row['status']:20s} "
            f"new={row['copied_new']:3d} identical={row['identical']:3d} "
            f"newer={row['overwritten_newer']:2d} kept_dst={row['kept_dst_newer']:2d} "
            f"sitemap+={row['sitemap_urls_added']:2d}"
        )
        if row["copied_files"] and len(row["copied_files"]) <= 10:
            print(f"    copied sample: {row['copied_files']}")
        elif row["copied_files"]:
            print(f"    copied count={len(row['copied_files'])}, sample={row['copied_files'][:5]}")
        if row["kept_dst_files"]:
            print(f"    kept_dst_files: {row['kept_dst_files']}")
    print("Totals:", summary["totals"])
    print("Remaining dirs:", summary["remaining_dirs"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
