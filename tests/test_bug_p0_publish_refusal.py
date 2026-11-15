"""
tests/test_bug_p0_publish_refusal.py — Invariant tests for BUG-P0 Publish Refusal Gate:
1. test_below_floor_article_is_not_published:
   - fixture returns ~95-word article
   - publish_next_post returns False
   - no new sites/*/index.html created
   - published_posts has no row for domain
   - sync_github never called
2. test_leaked_article_is_not_published:
   - fixture contains real BANNED_LEAK_PHRASES string
   - returns False, nothing written, sync_github not called
3. test_topic_returns_to_pending_after_refusal:
   - after refusal, SELECT status FROM topic_queue WHERE id=? is 'pending'
4. test_good_article_still_publishes:
   - fixture genuinely clears the floor (>=3000 words, >=4 H2, table, >=2 FAQs, etc.)
   - returns True and the file exists
5. test_pipeline_stage_records_refusal:
   - pipeline_state.stage_name is 'Quality Gate Refused' after refusal
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
import pytest

import autopublish_daemon
from content_quality_gate import BANNED_LEAK_PHRASES, ARTICLE_WORD_COUNT_FLOOR


def _setup_test_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    domain: str = "tazaloan",
    topic: str = "Instant Personal Loan Interest Rate Guide 2026",
) -> tuple[Path, list[str]]:
    repo_cfg = Path("config.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    ap_db = tmp_path / "state" / "autopublish.db"
    monkeypatch.setattr(autopublish_daemon, "DB_PATH", str(ap_db))
    monkeypatch.setattr(autopublish_daemon, "CONFIG_PATH", repo_cfg)
    autopublish_daemon.init_db()

    # Seed isolated ShingleGuard index in tmp_path to prevent side-effects on repo state
    shingle_file = tmp_path / "state" / "prose_shingles.json"
    shingle_file.parent.mkdir(parents=True, exist_ok=True)
    shingle_file.write_text('{"seed_hash": {"domain": "seed", "slug": "seed", "text": "seed prose shingle"}}', encoding="utf-8")
    import shingle_guard
    monkeypatch.setattr(shingle_guard, "SHINGLE_INDEX_PATH", shingle_file)

    # Seed site dir and sitemap.xml
    d = tmp_path / "sites" / f"{domain}.com"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset></urlset>', encoding="utf-8")

    # Seed pending topic in topic_queue
    with sqlite3.connect(ap_db) as con:
        con.execute(
            "INSERT INTO topic_queue (domain, category, topic, status, priority_score, created_at) VALUES (?, 'Finance', ?, 'pending', 95.0, '2026-11-15T00:00:00')",
            (domain, topic),
        )
        con.commit()

    # Stub SEO brief and dynamic image generators
    monkeypatch.setattr(
        autopublish_daemon.seo_pipeline,
        "generate_seo_brief",
        lambda site, top: {
            "seo_title": f"{site.title()} Comprehensive Interest Rate Guide 2026",
            "meta_description": f"Verified interest rate comparison, eligibility criteria, and fee structures for {site.title()}.",
            "primary_keyword": f"{site} interest rate guide",
            "lsi_keywords": ["rbi compliance", "apr benchmark", "credit score guidelines"],
            "category": "Finance",
        },
    )
    monkeypatch.setattr(
        autopublish_daemon.seo_pipeline,
        "get_dynamic_seo_image",
        lambda kw, site: {"url": "https://example.com/hero.jpg", "alt": "Verified financial benchmark illustration"},
    )
    monkeypatch.setattr(autopublish_daemon, "_notify_pipeline_error", lambda *a, **k: None)
    monkeypatch.setattr(
        autopublish_daemon.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="ok", stderr=""),
    )

    import instant_indexer
    monkeypatch.setattr(instant_indexer, "broadcast_new_post", lambda site_id, url: True)

    git_calls: list[str] = []
    monkeypatch.setattr(autopublish_daemon, "sync_github", lambda site_id, slug, top: git_calls.append(site_id))

    return ap_db, git_calls


def _generate_varied_long_article() -> str:
    sections = [
        ("Institutional Guidelines", "Evaluating statutory regulatory guidelines established by banking authorities."),
        ("Interest Rate Framework", "Analyzing effective annual percentage rates across diverse credit categories."),
        ("Eligibility Criteria", "Outlining comprehensive borrower qualification benchmarks and documentation rules."),
        ("Risk Assessment Matrix", "Examining systemic financial exposure, liquidity considerations, and credit rating impacts."),
        ("Disbursement Dynamics", "Reviewing operational turnaround schedules and digital loan processing workflows."),
    ]
    parts = ["<p class='lead'>Authoritative market intelligence and comprehensive analytical assessment regarding Indian financial sector developments in 2026.</p>"]

    subjects = [
        "Commercial banking institutions", "Statutory financial agencies", "Non-banking financial corporations",
        "Senior credit underwriters", "Regulatory policy committees", "Empirical economic researchers",
        "Institutional credit desks", "Corporate treasury analysts", "Retail lending specialists",
        "Chartered risk assessment officers"
    ]
    verbs = [
        "must systematically evaluate", "frequently scrutinize", "maintain robust compliance mechanisms for",
        "require exhaustive documentation regarding", "apply rigorous stress testing metrics to",
        "mandate continuous supervisory monitoring of", "consistently benchmark borrowing thresholds against",
        "incorporate standardized repayment algorithms into", "establish conservative loan-to-value limits for",
        "calculate debt-to-income proportions across"
    ]
    contexts = [
        "unsecured consumer financing products across regional commercial centers.",
        "micro-enterprise working capital facilities under structured credit schemes.",
        "revolving credit line authorizations for emerging service sector enterprises.",
        "statutory priority sector lending allocations mandated by central directives.",
        "syndicated infrastructure debt obligations subject to floating interest benchmarks.",
        "term deposit backed asset acquisition programs in metropolitan hubs.",
        "digital consumer credit origination channels utilizing algorithmic scoring models.",
        "secured equipment hypothecation agreements for small manufacturing units.",
        "housing finance portfolio acquisitions governed by statutory securitization rules.",
        "commercial vehicle financing agreements requiring verified cash flow validation."
    ]
    adverbs = [
        "Consequently, market participants must maintain disciplined liquidity reserves to mitigate potential volatility.",
        "Furthermore, detailed forensic audits ensure that borrowing entities maintain appropriate debt service coverage ratios.",
        "Moreover, updated statutory circulars emphasize strict compliance with transparent annual percentage rate disclosures.",
        "In addition, empirical delinquency statistics demonstrate the critical importance of early warning risk indicators.",
        "Importantly, institutional lenders are required to furnish clear amortisation schedules prior to loan execution.",
        "As a result, borrowers should compare effective interest outlays rather than relying solely on promotional nominal rates.",
        "Similarly, digital credit assessment platforms now cross-verify tax filings directly with centralized repositories.",
        "Therefore, prudent capital budgeting necessitates establishing contingency provisions for floating rate adjustments.",
        "Concurrently, financial ombudsman frameworks provide robust dispute resolution mechanisms for aggrieved consumers.",
        "Ultimately, sustainable credit expansion relies on balancing risk-adjusted asset returns with consumer affordability."
    ]

    for sec_idx, (title, intro) in enumerate(sections, 1):
        parts.append(f"<h2>{sec_idx}. {title}</h2>")
        parts.append(f"<p>{intro} The Indian credit ecosystem in 2026 demands unprecedented operational transparency and analytical rigor across all borrower categories.</p>")
        for p_idx in range(16):
            s = subjects[(sec_idx * 7 + p_idx * 3) % len(subjects)]
            v = verbs[(sec_idx * 5 + p_idx * 2) % len(verbs)]
            c = contexts[(sec_idx * 3 + p_idx * 7) % len(contexts)]
            a = adverbs[(sec_idx * 2 + p_idx * 5) % len(adverbs)]
            detail = f"During fiscal year 2026, observation index {sec_idx}-{p_idx} demonstrates that quarterly portfolio performance correlates with baseline economic indicators. Verified credit records confirm that timely debt servicing preserves creditworthiness across statutory evaluation periods."
            parts.append(f"<p>{s} {v} {c} {detail} {a}</p>")

    table = """
    <div class='table-responsive'>
        <table class='article-table'>
            <thead>
                <tr><th>Borrower Category</th><th>Baseline APR</th><th>Benchmark Spread</th><th>Processing Slab</th></tr>
            </thead>
            <tbody>
                <tr><td>Prime Salaried</td><td>8.65%</td><td>RBLR + 2.15%</td><td>0.50%</td></tr>
                <tr><td>Self-Employed Professional</td><td>9.20%</td><td>RBLR + 2.70%</td><td>0.75%</td></tr>
                <tr><td>MSME Enterprise</td><td>9.85%</td><td>RBLR + 3.35%</td><td>1.00%</td></tr>
            </tbody>
        </table>
    </div>
    """
    parts.append(table)
    return "\n".join(parts)


def test_below_floor_article_is_not_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ap_db, git_calls = _setup_test_env(tmp_path, monkeypatch, domain="tazaloan")

    short_html = (
        "<p class='lead'>Tazaloan provides an empirical benchmark analyzing personal loan interest slabs and statutory guidelines across Indian lending markets.</p>"
        "<h2>1. Interest Rate Framework</h2>"
        "<p>Borrowers should carefully review effective annual percentage rates and processing fee schedules before finalizing loan applications.</p>"
        "<div class='table-responsive'><table class='article-table'><thead><tr><th>Lender</th><th>Rate</th></tr></thead>"
        "<tbody><tr><td>Public Bank</td><td>9.5%</td></tr><tr><td>NBFC</td><td>11.2%</td></tr></tbody></table></div>"
        "<h3>How do borrowers verify interest rate transparency?</h3>"
        "<p>Borrowers should inspect loan sanction letters and amortization tables to verify total repayment outflow.</p>"
    )
    faqs = [{"question": "How do borrowers verify interest rate transparency?", "answer": "Borrowers should inspect loan sanction letters."}]
    monkeypatch.setattr(autopublish_daemon, "generate_claude_seo_article", lambda *a, **k: (short_html, faqs))

    res = autopublish_daemon.publish_next_post(specific_site="tazaloan")

    assert res is False, "publish_next_post must return False for below-floor article"

    # Verify zero article files created under sites/tazaloan.com
    site_dir = tmp_path / "sites" / "tazaloan.com"
    created_html = [p for p in site_dir.rglob("*.html")]
    assert len(created_html) == 0, f"No new HTML files should be created, found: {created_html}"

    # Verify no row in published_posts
    with sqlite3.connect(ap_db) as con:
        rows = con.execute("SELECT * FROM published_posts WHERE domain = 'tazaloan'").fetchall()
    assert len(rows) == 0, "published_posts table must have no row for refused domain"

    # Verify sync_github was never called
    assert len(git_calls) == 0, "sync_github must never be called on refusal"


def test_leaked_article_is_not_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ap_db, git_calls = _setup_test_env(tmp_path, monkeypatch, domain="tazaloan")

    leak_phrase = BANNED_LEAK_PHRASES[0]
    leak_html = (
        f"<p class='lead'>Tazaloan analysis report. {leak_phrase} for this draft article.</p>"
        "<h2>1. Market Dynamics</h2>"
        "<p>Financial metrics require strict adherence to regulatory standards across all regional sectors.</p>"
    )
    faqs = [{"question": "Q1?", "answer": "A1."}]
    monkeypatch.setattr(autopublish_daemon, "generate_claude_seo_article", lambda *a, **k: (leak_html, faqs))

    res = autopublish_daemon.publish_next_post(specific_site="tazaloan")

    assert res is False, "publish_next_post must return False for prompt-leaked article"

    # Verify zero article files created under sites/tazaloan.com
    site_dir = tmp_path / "sites" / "tazaloan.com"
    created_html = [p for p in site_dir.rglob("*.html")]
    assert len(created_html) == 0, f"No HTML files should be written on prompt leak, found: {created_html}"

    # Verify sync_github was never called
    assert len(git_calls) == 0, "sync_github must never be called when prompt leak is detected"


def test_topic_returns_to_pending_after_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ap_db, _ = _setup_test_env(tmp_path, monkeypatch, domain="tazaloan")

    with sqlite3.connect(ap_db) as con:
        q_id = con.execute("SELECT id FROM topic_queue WHERE domain='tazaloan'").fetchone()[0]

    short_html = "<p class='lead'>Thin content below floor.</p><h2>Section</h2><p>Brief text.</p>"
    monkeypatch.setattr(autopublish_daemon, "generate_claude_seo_article", lambda *a, **k: (short_html, []))

    res = autopublish_daemon.publish_next_post(specific_site="tazaloan")
    assert res is False, "publish_next_post must return False for below-floor article"

    with sqlite3.connect(ap_db) as con:
        status = con.execute("SELECT status FROM topic_queue WHERE id=?", (q_id,)).fetchone()[0]
    assert status == "pending", f"Expected topic status 'pending' after refusal, got '{status}'"


def test_good_article_still_publishes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ap_db, git_calls = _setup_test_env(tmp_path, monkeypatch, domain="tazaloan")

    long_html = _generate_varied_long_article()
    faqs = [
        {"question": "What is the statutory minimum documentation required in 2026?", "answer": "Borrowers must provide verified identity proofs, recent income statements, and tax returns."},
        {"question": "How do floating interest rates impact monthly loan repayments?", "answer": "Floating rates adjust in response to central bank repo rate modifications, altering the interest component of loan amortisation."}
    ]
    monkeypatch.setattr(autopublish_daemon, "generate_claude_seo_article", lambda *a, **k: (long_html, faqs))

    res = autopublish_daemon.publish_next_post(specific_site="tazaloan")

    assert res is True, "publish_next_post must return True for an article that clears the quality floor"

    site_dir = tmp_path / "sites" / "tazaloan.com"
    created_html = [p for p in site_dir.rglob("index.html")]
    assert len(created_html) == 1, f"Expected exactly 1 published article file, found {len(created_html)}: {created_html}"
    assert created_html[0].exists(), "Published article index.html file must exist"

    with sqlite3.connect(ap_db) as con:
        pub_rows = con.execute("SELECT domain, words FROM published_posts WHERE domain = 'tazaloan'").fetchall()
    assert len(pub_rows) == 1, "published_posts table must have exactly 1 record for the published domain"
    assert pub_rows[0][1] >= ARTICLE_WORD_COUNT_FLOOR, f"Recorded words {pub_rows[0][1]} must be >= floor {ARTICLE_WORD_COUNT_FLOOR}"
    assert len(git_calls) == 1, "sync_github must be called on successful publish"


def test_pipeline_stage_records_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ap_db, _ = _setup_test_env(tmp_path, monkeypatch, domain="tazaloan")

    short_html = "<p class='lead'>Sub-floor content snippet.</p><h2>Overview</h2><p>Brief text.</p>"
    monkeypatch.setattr(autopublish_daemon, "generate_claude_seo_article", lambda *a, **k: (short_html, []))

    res = autopublish_daemon.publish_next_post(specific_site="tazaloan")
    assert res is False, "publish_next_post must return False on refusal"

    with sqlite3.connect(ap_db) as con:
        stage_name = con.execute("SELECT stage_name FROM pipeline_state WHERE domain = 'tazaloan'").fetchone()[0]
    assert stage_name == "Quality Gate Refused", f"Expected stage_name 'Quality Gate Refused', got '{stage_name}'"
