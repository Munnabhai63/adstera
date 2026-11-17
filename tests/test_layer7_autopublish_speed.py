"""tests/test_layer7_autopublish_speed.py — Layer 7 Autopublish Speed, Parallelism & Recovery Tests."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import autopublish_daemon
import topic_intelligence


def test_layer7_config_defaults_and_interval_20_min() -> None:
    cfg = autopublish_daemon._load_autopublish_config()
    assert int(cfg["interval_minutes"]) == 20
    assert int(cfg["parallel_domains"]) == 2
    assert float(cfg["min_winner_score"]) >= 65.0
    assert int(cfg["min_pending_per_domain"]) >= 3


def test_aggressive_top5_winner_scoring_and_queue_sync(tmp_path: Path) -> None:
    db_file = tmp_path / "autopublish.db"
    topic_intelligence.init_candidate_tables(db_path=str(db_file))

    _, _, _, high_score = topic_intelligence.score_topic(
        "SBI Personal Loan Interest Rate & Zero Processing Fee Eligibility Criteria 2026",
        base_rank=0,
        trend_match=True,
    )
    _, _, _, weak_score = topic_intelligence.score_topic(
        "latest updates news",
        base_rank=15,
        trend_match=False,
    )
    assert high_score >= 80.0
    assert weak_score <= 40.0
    assert (high_score - weak_score) >= 40.0

    pool = topic_intelligence.discover_20_topics_for_domain(
        "tazaloan",
        min_winner_score=65.0,
        sync_to_queue=True,
        fetch_live=False,
        db_path=str(db_file),
    )
    winners = [c for c in pool if c["is_winner"] == 1]
    assert len(winners) == 5
    assert all(w["composite_score"] >= 65.0 for w in winners)

    with sqlite3.connect(db_file) as con:
        q_rows = con.execute(
            "SELECT topic, priority_score, status FROM topic_queue WHERE domain='tazaloan'"
        ).fetchall()
    assert len(q_rows) == 5
    assert all(r[2] == "pending" and float(r[1]) >= 65.0 for r in q_rows)


def test_kick_stuck_domains_unsticks_tazaloan_loankiseva_and_processing(tmp_path: Path) -> None:
    db_file = tmp_path / "autopublish.db"
    topic_intelligence.init_candidate_tables(db_path=str(db_file))
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()

    with sqlite3.connect(db_file) as con:
        con.execute(
            """
            INSERT INTO pipeline_state (domain, current_stage, stage_name, active_topic, words_written, anti_ai_score, status_message, updated_at)
            VALUES ('tazaloan', 2, 'Top-5 CPC Selection', 'Old Stuck Topic', 0, 0.0, 'Stuck', ?)
            """,
            (stale_ts,),
        )
        con.execute(
            """
            INSERT INTO pipeline_state (domain, current_stage, stage_name, active_topic, words_written, anti_ai_score, status_message, updated_at)
            VALUES ('loankiseva', 2, 'Top-5 CPC Selection', 'Mudra Old Stuck', 0, 0.0, 'Stuck', ?)
            """,
            (stale_ts,),
        )
        con.execute(
            """
            INSERT INTO topic_queue (domain, category, topic, status, priority_score, created_at)
            VALUES ('tazaloan', 'Personal Loans', 'Stranded Processing Personal Loan 2026', 'processing', 85.0, ?)
            """,
            (stale_ts,),
        )
        con.commit()

    res = topic_intelligence.kick_stuck_pipelines(
        stale_minutes=30,
        target_domains=["tazaloan", "loankiseva"],
        min_pending_per_domain=3,
        fetch_live=False,
        db_path=str(db_file),
    )

    assert res["rescued_processing"] == 1
    assert "tazaloan" in res["kicked_domains"]
    assert "loankiseva" in res["kicked_domains"]
    assert res["pending_by_domain"]["tazaloan"] >= 3
    assert res["pending_by_domain"]["loankiseva"] >= 3

    with sqlite3.connect(db_file) as con:
        rows = {
            r[0]: (r[1], r[2], r[3])
            for r in con.execute(
                "SELECT domain, stage_name, status_message, updated_at FROM pipeline_state WHERE domain IN ('tazaloan', 'loankiseva')"
            ).fetchall()
        }
        stranded = con.execute("SELECT COUNT(*) FROM topic_queue WHERE status='processing'").fetchone()[0]

    assert stranded == 0
    assert rows["tazaloan"][0] == "Queued for Fast-Track Publish"
    assert rows["loankiseva"][0] == "Queued for Fast-Track Publish"
    assert rows["tazaloan"][2] != stale_ts


def test_parallel_two_domain_batch_concurrency_and_isolation(tmp_path: Path, monkeypatch) -> None:
    repo_cfg = Path("config.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    ap_db = tmp_path / "state" / "autopublish.db"
    monkeypatch.setattr(autopublish_daemon, "DB_PATH", str(ap_db))
    monkeypatch.setattr(autopublish_daemon, "CONFIG_PATH", repo_cfg)
    autopublish_daemon.init_db()

    # Seed empty sites dirs + sitemap for tazaloan & loankiseva
    for dom in ("tazaloan", "loankiseva", "loanraaj", "karzseva"):
        d = tmp_path / "sites" / f"{dom}.com"
        d.mkdir(parents=True, exist_ok=True)
        (d / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset></urlset>', encoding="utf-8")

    # Seed pending topics ONLY for tazaloan & loankiseva
    with sqlite3.connect(ap_db) as con:
        for dom, topic in (
            ("tazaloan", "Instant Personal Loan Interest Rate Guide 2026"),
            ("loankiseva", "PM Mudra Loan Apply Online Eligibility 2026"),
        ):
            con.execute(
                "INSERT INTO topic_queue (domain, category, topic, status, priority_score, created_at) VALUES (?, 'Finance', ?, 'pending', 92.5, '2026-11-11T00:00:00')",
                (dom, topic),
            )
        con.commit()

    monkeypatch.setattr(
        autopublish_daemon.seo_pipeline,
        "generate_seo_brief",
        lambda site, topic: {
            "seo_title": f"{site} Guide 2026",
            "meta_description": "Verified guide description",
            "primary_keyword": f"{site} interest rate guide",
            "lsi_keywords": ["rbi", "apr"],
            "category": "Finance",
        },
    )
    monkeypatch.setattr(
        autopublish_daemon.seo_pipeline,
        "get_dynamic_seo_image",
        lambda kw, site: {"url": "https://example.com/hero.jpg", "alt": "hero"},
    )

    def _slow_article(site_id, site_info, brief):
        time.sleep(0.35)
        html_snip = (
            "<p class='lead'>Direct empirical guide with ₹10,000 savings and 9.5% APR rules from RBI.</p>"
            "<h2>Comparison</h2><div class='table-responsive'><table class='article-table'><thead><tr><th>Option</th><th>Rate</th></tr></thead>"
            "<tbody><tr><td>SBI</td><td>9.5%</td></tr><tr><td>HDFC</td><td>10.2%</td></tr></tbody></table></div>"
            "<h3>Question one?</h3><p>Verified answer with ₹500 fee detail.</p>"
        )
        return html_snip, [{"question": "Question one?", "answer": "Verified answer."}]

    monkeypatch.setattr(autopublish_daemon, "generate_claude_seo_article", _slow_article)
    monkeypatch.setattr(autopublish_daemon, "_notify_pipeline_error", lambda *a, **k: None)

    monkeypatch.setattr(
        autopublish_daemon.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="ok", stderr=""),
    )

    import instant_indexer
    monkeypatch.setattr(instant_indexer, "broadcast_new_post", lambda site_id, url: True)

    git_calls: list[str] = []
    monkeypatch.setattr(autopublish_daemon, "sync_github", lambda site_id, slug, topic: git_calls.append(site_id))

    res = autopublish_daemon.publish_parallel_batch(parallel_domains=2, kick_stuck=False)

    assert res["published_count"] == 2
    assert set(res["attempted_sites"]) == {"tazaloan", "loankiseva"}
    assert set(git_calls) == {"tazaloan", "loankiseva"}
    # Parallel proof: 2 x 0.35s serialized = >= 0.70s; concurrent finishes well under serialized time + overhead check
    assert res["elapsed_seconds"] < 1.2

    with sqlite3.connect(ap_db) as con:
        pub_doms = {r[0] for r in con.execute("SELECT domain FROM published_posts").fetchall()}
        stages = dict(
            con.execute("SELECT domain, stage_name FROM pipeline_state WHERE domain IN ('tazaloan', 'loankiseva')").fetchall()
        )
    assert pub_doms == {"tazaloan", "loankiseva"}
    assert stages["tazaloan"] == "Cloudflare & GSC"
    assert stages["loankiseva"] == "Cloudflare & GSC"
    assert (tmp_path / "sites" / "tazaloan.com" / "tazaloan-interest-rate-guide.html").exists()
    assert (tmp_path / "sites" / "loankiseva.com" / "loankiseva-interest-rate-guide.html").exists()


def test_publish_failure_resets_processing_topic_cleanly(tmp_path: Path, monkeypatch) -> None:
    ap_db = tmp_path / "autopublish.db"
    monkeypatch.setattr(autopublish_daemon, "DB_PATH", str(ap_db))
    autopublish_daemon.init_db()
    with sqlite3.connect(ap_db) as con:
        con.execute(
            "INSERT INTO topic_queue (domain, category, topic, status, priority_score, created_at) VALUES ('loanraaj', 'Business', 'Failure Rollback Topic', 'pending', 80.0, '2026-11-11T00:00:00')"
        )
        con.commit()

    monkeypatch.setattr(autopublish_daemon.seo_pipeline, "generate_seo_brief", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        autopublish_daemon.publish_next_post(specific_site="loanraaj")

    with sqlite3.connect(ap_db) as con:
        st = con.execute("SELECT status FROM topic_queue WHERE domain='loanraaj'").fetchone()[0]
    assert st == "pending"


def test_live_ui_autopublish_speed_endpoints() -> None:
    try:
        r_html = httpx.get("http://127.0.0.1:5050/autopublish", timeout=5)
    except Exception as exc:
        pytest.skip(f"Dashboard UI not listening on 5050: {exc}")

    assert r_html.status_code == 200
    assert "Kick Stuck Domains" in r_html.text
    assert "2 PARALLEL / 20m CADENCE" in r_html.text

    r_stats = httpx.get("http://127.0.0.1:5050/api/autopublish/stats?domain=tazaloan", timeout=10)
    assert r_stats.status_code == 200
    data = r_stats.json()
    assert data["speed_config"]["interval_minutes"] == 20
    assert data["speed_config"]["parallel_domains"] == 2
    assert "all_pipelines" in data

    r_kick = httpx.post("http://127.0.0.1:5050/api/autopublish/kick", json={"domains": ["tazaloan", "loankiseva"]}, timeout=20)
    assert r_kick.status_code == 200
    k = r_kick.json()
    assert k["success"] is True
    assert "tazaloan" in k["kicked_domains"]
    assert "loankiseva" in k["kicked_domains"]
    assert k["pending_by_domain"]["tazaloan"] >= 3
    assert k["pending_by_domain"]["loankiseva"] >= 3


def test_claude_seo_v2_5_full_subsystem_on_article() -> None:
    from content_quality_gate import ContentQualityFinishGate
    from network_registry import NETWORK_REGISTRY
    from site_templates import render_master_page
    import seo_pipeline

    raw_draft = (
        "<p class='lead'>In this guide we delve\u200b into SBI Commercial Truck Loan 9.25% APR rules and ₹45,000 subsidy math under RBI circulars.</p>"
        "<h2>1. What Are the 2026 RBI Interest Slabs?</h2><p>State Bank of India and HDFC Bank offer 9.25% to 11.40% APR for BS-VI fleet operators.</p>"
        "<h2>2. Commercial Vehicle Loan Comparison Table</h2>"
        "<div class='table-responsive'><table><thead><tr><th>Bank</th><th>APR</th><th>Max Tenure</th></tr></thead>"
        "<tbody><tr><td>SBI Fleet</td><td>9.25%</td><td>84 Months</td></tr><tr><td>HDFC Transport</td><td>10.10%</td><td>72 Months</td></tr></tbody></table></div>"
        "<h2>3. Step-by-Step CGTMSE & Fleet Application Checklist</h2><ol><li>Verify GSTIN and Udyam certificate.</li><li>Submit 12-month bank statement.</li></ol>"
        "<h2>4. Penalty & Foreclosure Rules</h2><p>Floating rate MSME loans carry 0% foreclosure charges per Reserve Bank of India guidelines.</p>"
        "<h3>What is the minimum CIBIL score for a truck loan?</h3><p>Most public sector banks require a CIBIL score of 700 or higher for zero-collateral CGTMSE coverage.</p>"
        "<h3>How fast is the disbursement for existing fleet owners?</h3><p>Pre-approved fleet operators receive sanction letters within 48 hours of digital KYC verification.</p>"
    )

    sanitized = ContentQualityFinishGate.sanitize_raw_html(raw_draft)
    assert "\u200b" not in sanitized
    assert "delve" not in sanitized.lower()

    formatted_html, faqs, meta = ContentQualityFinishGate.format_editorial_layout(
        clean_html=sanitized,
        title="SBI Commercial Truck Loan 2026: Complete Guide",
        domain_key="loanraaj",
        primary_kw="sbi commercial truck loan 2026",
        category="Commercial Finance",
        site_name="LoanRaaj",
    )
    assert meta["has_summary"] is True
    assert meta["has_toc"] is True
    assert meta["has_cluster"] is True
    assert meta["has_eeat"] is True
    assert meta["has_table"] is True
    assert len(faqs) >= 2
    assert 'class="article-toc"' in formatted_html
    assert 'class="topic-cluster-box"' in formatted_html
    assert 'class="eeat-verification-box"' in formatted_html
    assert "rbi.org.in" in formatted_html

    canonical = "https://loanraaj.com/sbi-commercial-truck-loan-2026"
    schema_ld = seo_pipeline.build_schema_json_ld(
        site_domain="loanraaj.com",
        site_name="LoanRaaj",
        title="SBI Commercial Truck Loan 2026: Complete Guide",
        desc="Complete guide to SBI commercial truck loan 2026 rates and RBI rules.",
        canonical_url=canonical,
        img_url="https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?auto=format&fit=crop&w=1200&h=675&q=85",
        faqs=faqs,
        category="Commercial Finance",
        cat_slug="commercial-finance",
        word_count=1650,
        keywords=["sbi commercial truck loan", "rbi msme loan"],
    )
    site_info = NETWORK_REGISTRY["loanraaj"]
    full_page = render_master_page(
        site_info,
        title="SBI Commercial Truck Loan 2026: Complete Guide",
        desc="Complete guide to SBI commercial truck loan 2026 rates and RBI rules.",
        canonical=canonical,
        main_body=f"<main><article><h1 class='post-h1'>SBI Commercial Truck Loan 2026: Complete Guide</h1>{formatted_html}</article></main>",
        active_nav="Commercial Finance",
        schema_json_ld=schema_ld,
    )
    audit = seo_pipeline.run_full_claude_seo_audit(full_page, canonical, formatted_html)
    assert audit["claude_seo_score"] == 100.0
    assert all(audit["checks"].values())

