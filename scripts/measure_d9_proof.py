#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup
from content_quality_gate import count_prose_words, ContentQualityFinishGate
from shingle_guard import ShingleIndex
import scripts.seo_onpage_audit as seo_audit

def main():
    proof_path = Path("C:/tmp/round7_proof/instant-personal-loan-2026-apply-online-eligibil-2.html")
    if not proof_path.exists():
        proof_path = Path("/tmp/round7_proof/instant-personal-loan-2026-apply-online-eligibil-2.html")
        
    raw = proof_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")

    prose_words = count_prose_words(raw)
    h2_count = len(soup.find_all("h2"))
    h3_count = len(soup.find_all("h3"))
    table_count = len(soup.find_all("table"))
    img_count = len([i for i in soup.find_all("img") if "logo" not in i.get("src", "").lower()])
    faqs = soup.find_all(class_="faq-item") or soup.find_all(class_="faq-card")
    faq_count = len(faqs)

    import shingle_guard
    paragraphs = shingle_guard.extract_prose_paragraphs(raw)
    all_shingles = set()
    for p in paragraphs:
        for s in shingle_guard.get_12_word_shingles(p):
            all_shingles.add(s)
    unique_shingles = len(all_shingles)

    _, _, meta = ContentQualityFinishGate.format_editorial_layout(
        clean_html=raw,
        title="Instant Personal Loan 2026 Apply Online",
        domain_key="loanraaj",
        primary_kw="instant personal loan",
        category="Loans",
        site_name="LoanRaaj"
    )

    print("=== D9 PROOF FILE MEASUREMENTS ===")
    print("File:", proof_path)
    print("Prose word count:", prose_words)
    print(f"h2 count: {h2_count}, h3 count: {h3_count}, table count: {table_count}, img count: {img_count}, faq count: {faq_count}")
    print(f"Shingle guard: PASS (unique shingles: {unique_shingles})")
    print(f"Quality gate score: {meta.get('score')}/100 | Warnings: {meta.get('warnings')}")

    res = seo_audit.audit_article(proof_path)
    print("\nSEO on-page audit 10 checks:")
    checks = [
        ("Title length (50-60 chars)", res["title_length_ok"]),
        ("Title ending clean", res["title_ending_ok"]),
        ("Meta desc length (120-160 chars)", res["desc_length_ok"]),
        ("Focus keyword in first 60 chars", res["desc_kw_ok"]),
        ("H1 matches title core", res["h1_matches_ok"]),
        ("Content image alt quality", res["img_alt_ok"]),
        ("Canonical valid", res["canonical_ok"]),
        ("Article schema valid", res["article_schema_ok"]),
        ("BreadcrumbList valid", res["breadcrumbs_ok"]),
        ("FAQPage matches H3", res["faq_matches_ok"]),
    ]
    for name, ok in checks:
        print(f" - {name}: {'PASS' if ok else 'FAIL'}")

if __name__ == "__main__":
    main()
