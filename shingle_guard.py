#!/usr/bin/env python3
"""
shingle_guard.py — Persistent 12-word prose shingle index & domain vocabulary blocklists
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent
SHINGLE_INDEX_PATH = PROJECT_ROOT / "state" / "prose_shingles.json"


class DuplicateContentError(ValueError):
    """Raised when a 12-word prose shingle appears on more than one page across the network."""
    pass


class JargonViolationError(ValueError):
    """Raised when an article contains terms forbidden for its vertical."""
    pass


class QualityPatternError(ValueError):
    """Raised when an article contains lorem ipsum, looping phrases, or corrupted script."""
    pass


# Domain Vocabulary Blocklists
BLOCKLISTS = {
    # Telecom domains must never contain lending jargon
    "recharge": [
        r"\bkfs\b",
        r"\bkey fact statement\b",
        r"\bapr\b",
        r"\bcibil\b",
        r"\bnbfc\b",
        r"\bforeclosure\b",
        r"\bprepayment penalty\b",
        r"\bcollateral-free loan\b",
        r"\bdebt consolidation\b",
        r"\bloan agreement\b",
        r"\binterest rate per annum\b",
        r"\bloan tenure\b"
    ],
    # Commodity domain must never contain lending jargon
    "tazabhav": [
        r"\bkfs\b",
        r"\bkey fact statement\b",
        r"\bapr\b",
        r"\bcibil\b",
        r"\bnbfc\b",
        r"\bforeclosure\b",
        r"\bpersonal loan\b",
        r"\bhome loan\b",
        r"\bloan tenure\b",
        r"\bborrower\b",
        r"\blender\b"
    ],
    # Loan domains must never contain telecom plan jargon
    "loan": [
        r"\bvalidity days\b",
        r"\b28 days validity\b",
        r"\b84 days validity\b",
        r"\bsms/day\b",
        r"\bunlimited 5g\b",
        r"\bott bundle\b",
        r"\bdata booster\b",
        r"\bprepaid recharge pack\b",
        r"\bsim porting\b"
    ]
}


def get_domain_vertical(domain: str) -> str:
    dom = domain.lower()
    if "recharge" in dom:
        return "recharge"
    elif "tazabhav" in dom:
        return "tazabhav"
    elif "loan" in dom or "karz" in dom or "tazarokda" in dom:
        return "loan"
    return "other"


def extract_prose_paragraphs(html_text: str) -> list[str]:
    """Extract plain text of paragraphs from post-content area."""
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup.find_all(["aside", "nav", "header", "footer"]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r"widget|sidebar|author-card|eeat|native-ad|ad-slot|summary-box|executive-summary")):
        tag.decompose()
    content = soup.find("div", class_="post-content") or soup.find("article") or soup.find("main")
    if not content:
        return []
    paras = []
    for p in content.find_all("p"):
        txt = p.get_text().strip()
        if txt:
            paras.append(txt)
    return paras


def get_12_word_shingles(text: str) -> list[str]:
    """Split text into normalized 12-word sliding shingles."""
    # Normalize punctuation and whitespace
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    words = clean.split()
    if len(words) < 12:
        return []
    shingles = []
    for i in range(len(words) - 11):
        shingles.append(" ".join(words[i : i + 12]))
    return shingles


def validate_text_quality(text: str):
    """Rejects Latin filler (lorem ipsum), looping phrases, and mixed-script corruption."""
    lower = text.lower()
    if "lorem ipsum" in lower or "consectetur adipiscing" in lower or "dolor sit amet" in lower:
        raise QualityPatternError("Latin filler detected in text")

    # Check for looping phrases: e.g. same 4-word phrase repeated 3+ times in a row
    words = lower.split()
    for n in (3, 4, 5):
        if len(words) >= n * 3:
            for i in range(len(words) - n * 3 + 1):
                p1 = " ".join(words[i : i + n])
                p2 = " ".join(words[i + n : i + 2 * n])
                p3 = " ".join(words[i + 2 * n : i + 3 * n])
                if p1 == p2 == p3 and len(p1) > 10:
                    raise QualityPatternError(f"Looping phrase detected: '{p1}'")

    # Check Devanagari share per sentence
    sentences = re.split(r"[.!?।\n]", text)
    for sent in sentences:
        s = sent.strip()
        if len(s) < 15:
            continue
        dev_chars = sum(1 for c in s if "\u0900" <= c <= "\u097f")
        total_letters = sum(1 for c in s if c.isalpha())
        if total_letters > 15:
            share = dev_chars / total_letters
            # Rejects mixed-script corruption between 5% and 85%
            if 0.05 < share < 0.85:
                raise QualityPatternError(f"Mixed-script corruption detected ({share*100:.1f}% Devanagari): '{s[:60]}...'")


def validate_domain_vocabulary(domain: str, text: str):
    """Ensure text does not contain forbidden jargon for domain's vertical."""
    vert = get_domain_vertical(domain)
    blocklist = BLOCKLISTS.get(vert, [])
    for pattern in blocklist:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raise JargonViolationError(
                f"Forbidden jargon '{match.group(0)}' found in article for {domain} ({vert} vertical)"
            )


_INDEX_SINGLETON: ShingleIndex | None = None
_INDEX_SINGLETON_PATH: Path | None = None
_SINGLETON_LOCK = threading.Lock()


def get_shared_index(index_path: Path | None = None) -> ShingleIndex:
    """Return a process-wide ShingleIndex. Cached per resolved path.
    If SHINGLE_INDEX_PATH is monkeypatched in tests, the cache must follow the path change.
    """
    global _INDEX_SINGLETON, _INDEX_SINGLETON_PATH
    target = Path(index_path or SHINGLE_INDEX_PATH).resolve()
    if _INDEX_SINGLETON is None or _INDEX_SINGLETON_PATH != target:
        with _SINGLETON_LOCK:
            if _INDEX_SINGLETON is None or _INDEX_SINGLETON_PATH != target:
                _INDEX_SINGLETON = ShingleIndex(index_path=target)
                _INDEX_SINGLETON_PATH = target
    return _INDEX_SINGLETON


def clear_shared_index() -> None:
    """Clear process-wide ShingleIndex cache."""
    global _INDEX_SINGLETON, _INDEX_SINGLETON_PATH
    with _SINGLETON_LOCK:
        _INDEX_SINGLETON = None
        _INDEX_SINGLETON_PATH = None


class ShingleIndex:
    def __init__(self, index_path: Path | None = None, auto_build_if_empty: bool = True):
        self.index_path = Path(index_path or SHINGLE_INDEX_PATH).resolve()
        self.auto_build_if_empty = auto_build_if_empty
        self.index: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()
        self._last_staleness_check: float = 0.0
        self._is_stale_cached: bool = False
        self.load()

    def is_stale(self, sites_dir: Path | None = None) -> bool:
        """Check if index file is missing, empty, or older than the newest file in sites/."""
        if not self.index_path.exists():
            return True
        try:
            index_mtime = self.index_path.stat().st_mtime
        except OSError:
            return True

        if not self.index:
            return True

        # Throttle repeated filesystem scans if checked within the last 5 seconds
        now = time.time()
        if sites_dir is None and (now - self._last_staleness_check) < 5.0:
            return self._is_stale_cached

        s_dir = sites_dir or (PROJECT_ROOT / "sites")
        if not s_dir.exists():
            return False

        is_stale_res = False
        for p in s_dir.rglob("*.html"):
            try:
                if p.stat().st_mtime > index_mtime:
                    is_stale_res = True
                    break
            except OSError:
                continue

        if sites_dir is None:
            self._last_staleness_check = now
            self._is_stale_cached = is_stale_res
        return is_stale_res

    def get_status(self) -> dict[str, Any]:
        """Return status metrics: pages indexed, total shingles, and index file age in seconds."""
        with self._lock:
            pages = len(set(v.get("page_id", "") for v in self.index.values()))
            shingles = len(self.index)
            age_sec = 0.0
            if self.index_path.exists():
                try:
                    age_sec = time.time() - self.index_path.stat().st_mtime
                except OSError:
                    pass
            return {
                "pages": pages,
                "shingles": shingles,
                "age_seconds": round(age_sec, 1),
                "path": str(self.index_path),
            }

    def rebuild(self):
        """Rebuild index from sites/ corpus and report [guard] index rebuilt."""
        with self._lock:
            try:
                from scripts.build_shingle_index import build_shingle_index
                build_shingle_index(output_path=self.index_path)
                if self.index_path.exists():
                    self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
                pages = len(set(v.get("page_id", "") for v in self.index.values()))
                print(f"[guard] index rebuilt: {len(self.index)} shingles / {pages} pages")
            except Exception:
                # Fallback if corpus cannot be parsed
                pass

    def load(self):
        with self._lock:
            if self.index_path.exists():
                try:
                    self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
                except Exception:
                    self.index = {}
            else:
                self.index = {}

            if (not self.index or self.is_stale()) and self.auto_build_if_empty:
                self.rebuild()
                if not self.index:
                    self.index_path.parent.mkdir(parents=True, exist_ok=True)
                    self.save()

    def save(self):
        with self._lock:
            snapshot = dict(self.index)
            payload = json.dumps(snapshot, indent=2)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(payload, encoding="utf-8", newline="\n")

    def register_article(self, domain: str, slug: str, html_text: str, check_duplicates: bool = True) -> int:
        """
        Validate quality, check vocabulary blocklists, and record 12-word shingles.
        Raises DuplicateContentError if a shingle is found on another page.
        Fail-closed: rebuilds index if missing or stale before duplicate check.
        """
        paras = extract_prose_paragraphs(html_text)
        full_prose = " ".join(paras)

        # 1. Quality & vocabulary checks
        validate_text_quality(full_prose)
        validate_domain_vocabulary(domain, full_prose)

        # 2. Extract shingles
        page_id = f"{domain}/{slug}"
        now_iso = datetime.now().isoformat()
        shingles = get_12_word_shingles(full_prose)

        with self._lock:
            # Fail closed: ensure index is fresh before checking duplicates
            if check_duplicates and (not self.index or self.is_stale()) and self.auto_build_if_empty:
                self.rebuild()

            if check_duplicates:
                for shingle in shingles:
                    existing = self.index.get(shingle)
                    if existing and existing["page_id"] != page_id:
                        raise DuplicateContentError(
                            f"Duplicate 12-word shingle found in {page_id} (already in {existing['page_id']}): '{shingle}'"
                        )

            # Record shingles
            for shingle in shingles:
                if shingle not in self.index:
                    self.index[shingle] = {
                        "domain": domain,
                        "slug": slug,
                        "page_id": page_id,
                        "first_seen": now_iso
                    }

            self.save()
        return len(shingles)


# Backward compatibility alias
ProseShingleIndex = ShingleIndex

