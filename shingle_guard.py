#!/usr/bin/env python3
"""
shingle_guard.py — Persistent 12-word prose shingle index & domain vocabulary blocklists
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
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


class ShingleIndex:
    def __init__(self, index_path: Path = SHINGLE_INDEX_PATH, auto_build_if_empty: bool = True):
        self.index_path = index_path
        self.auto_build_if_empty = auto_build_if_empty
        self.index: dict[str, dict[str, str]] = {}
        self.load()

    def rebuild(self):
        """Rebuild index from sites/ corpus."""
        try:
            from scripts.build_shingle_index import build_shingle_index
            build_shingle_index(output_path=self.index_path)
            if self.index_path.exists():
                self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception as e:
            # Fallback if corpus cannot be parsed
            pass

    def load(self):
        if self.index_path.exists():
            try:
                self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
            except Exception:
                self.index = {}
        else:
            self.index = {}

        if not self.index and self.auto_build_if_empty:
            self.rebuild()
            if not self.index:
                self.index_path.parent.mkdir(parents=True, exist_ok=True)
                self.save()

    def save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(self.index, indent=2), encoding="utf-8")

    def register_article(self, domain: str, slug: str, html_text: str, check_duplicates: bool = True) -> int:
        """
        Validate quality, check vocabulary blocklists, and record 12-word shingles.
        Raises DuplicateContentError if a shingle is found on another page.
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

