"""
tests/test_topic_queue_composite.py — Verification of P3-3:
1. Enqueuing the same topic on two different domains succeeds (composite unique index ux_topic_domain).
2. Cross-domain duplicate guard rejects enqueueing a topic that has already been published on another domain.
"""
import sqlite3
import pytest
from pathlib import Path

import topic_intelligence


def test_topic_queue_composite_and_cross_domain_guard(tmp_path: Path):
    db_file = str(tmp_path / "test_autopublish.db")
    topic_intelligence.init_candidate_tables(db_file)

    topic_title = "Commercial Vehicle Financing 2026: Fast Approvals"

    # 1. Enqueue on rechargekar
    inserted1 = topic_intelligence.sync_winners_to_queue(
        "rechargekar",
        [{"topic": topic_title, "category": "General", "composite_score": 85.0}],
        db_path=db_file,
    )
    assert inserted1 == 1, "First domain enqueue should succeed"

    # 2. Enqueue the SAME topic on rechargepur (must succeed now with composite unique index)
    inserted2 = topic_intelligence.sync_winners_to_queue(
        "rechargepur",
        [{"topic": topic_title, "category": "General", "composite_score": 88.0}],
        db_path=db_file,
    )
    assert inserted2 == 1, "Second domain enqueue with same topic should succeed"

    # Verify both rows exist in DB
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT domain, topic FROM topic_queue WHERE topic = ?", (topic_title,)).fetchall()
    assert len(rows) == 2, f"Expected 2 rows for topic across different domains, got {len(rows)}"

    # 3. Simulate publishing on rechargekar
    conn.execute(
        """
        INSERT INTO published_posts (domain, slug, title, category, words, published_at)
        VALUES ('rechargekar', 'commercial-vehicle-financing-2026', ?, 'General', 1500, '2026-11-13T12:00:00')
        """,
        (topic_title,),
    )
    conn.commit()

    # 4. Now attempt to enqueue on a third domain (tazaloan) — cross-domain guard should reject it
    inserted3 = topic_intelligence.sync_winners_to_queue(
        "tazaloan",
        [{"topic": topic_title, "category": "General", "composite_score": 90.0}],
        db_path=db_file,
    )
    assert inserted3 == 0, "Cross-domain guard must reject topic already published on another domain"
    conn.close()

