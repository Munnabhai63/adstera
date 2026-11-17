"""Tests locking FAQ question shape, answer lengths, and schema synchronization across at-floor pages (D20-A).

Rules enforced:
- Every .faq-question text, after stripping leading marker/whitespace, ends with ?.
- Every .faq-answer is 40-80 words.
- Body question count == FAQPage mainEntity count.
- Body question strings == schema mainEntity names (exact, after strip).
"""

import json
import pytest
import bs4
from pathlib import Path

from scripts.seo_onpage_audit import get_all_article_paths, audit_article

PROJECT_ROOT = Path(__file__).parent.parent


def get_at_floor_paths():
    paths = get_all_article_paths()
    return [p for p in paths if (audit_article(p).get("prose_words") or 0) >= 3000]


def test_at_floor_faq_questions_end_with_question_mark():
    floor_paths = get_at_floor_paths()
    assert len(floor_paths) == 57, f"Expected 57 at-floor articles, found {len(floor_paths)}"
    
    non_questions = []
    for p in floor_paths:
        s = bs4.BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        for q in s.find_all(class_="faq-question"):
            raw_text = q.get_text().strip()
            clean_text = raw_text.lstrip("❓? \t\n").strip()
            if not clean_text.endswith("?"):
                non_questions.append((str(p.name), raw_text))
                
    assert len(non_questions) == 0, f"Found {len(non_questions)} FAQ questions not ending in '?': {non_questions[:5]}"


def test_at_floor_faq_answers_are_40_to_80_words():
    floor_paths = get_at_floor_paths()
    out_of_bounds = []
    
    for p in floor_paths:
        s = bs4.BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        for a in s.find_all(class_="faq-answer"):
            txt = a.get_text().strip()
            w = len(txt.split())
            if w < 40 or w > 80:
                out_of_bounds.append((str(p.name), w, txt[:50]))
                
    assert len(out_of_bounds) == 0, f"Found {len(out_of_bounds)} FAQ answers outside 40-80 words: {out_of_bounds[:5]}"


def test_at_floor_faq_body_and_schema_match():
    floor_paths = get_at_floor_paths()
    mismatches = []
    
    for p in floor_paths:
        s = bs4.BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        body_questions = []
        for q in s.find_all(class_="faq-question"):
            clean = q.get_text().strip().replace("❓", "").strip()
            body_questions.append(clean)
            
        schema_questions = []
        for sc in s.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(sc.string or "{}")
                graph = data.get("@graph", [data])
                for item in graph:
                    if item.get("@type") == "FAQPage":
                        for ent in item.get("mainEntity", []):
                            name = ent.get("name", "").strip()
                            schema_questions.append(name)
            except Exception:
                pass
                
        if len(body_questions) != len(schema_questions):
            mismatches.append((str(p.name), f"Count mismatch: body={len(body_questions)} schema={len(schema_questions)}"))
        elif body_questions != schema_questions:
            mismatches.append((str(p.name), f"String mismatch: body={body_questions} schema={schema_questions}"))
            
    assert len(mismatches) == 0, f"Found {len(mismatches)} body/schema FAQ mismatches: {mismatches[:3]}"
