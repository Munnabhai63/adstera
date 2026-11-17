"""
tests/test_d10_structural_loss.py — Test structural loss metric and heading preservation (D10)
"""

from content_quality_gate import count_structural_units, verify_structural_integrity


def test_structural_loss_metric_and_heading_preservation():
    """
    Verifies that structural units (<p>, <table>, <figure>, <img>, <ol>/<ul>) are counted,
    heading removal does not trip the guard, and actual paragraph/structure drops fail.
    """
    html_before = """
    <div class="post-content">
        <h2>1. Statutory Architecture & 2026 Directives</h2>
        <p>This is the first comprehensive analysis paragraph explaining statutory requirements and borrower guidelines.</p>
        <h2>Statutory Grievance Redressal</h2>
        <h2>Statutory Grievance Redressal</h2>
        <p>This is the second comprehensive analysis paragraph explaining Ombudsman escalation and dispute resolution.</p>
        <table><tr><td>State Bank of India</td><td>10.5%</td></tr></table>
        <figure><img src="/img/sample.webp" alt="Inspection"/><figcaption>Caption</figcaption></figure>
        <ul><li>Step 1: Application submission</li><li>Step 2: Verification</li></ul>
        <h2>Frequently Asked Questions</h2>
        <h2>Frequently Asked Questions</h2>
        <p>This is the third paragraph answering borrower queries regarding application timelines and fees.</p>
    </div>
    """

    # 1. Simulate duplicate heading removal (heading text removed, paragraphs and elements 100% intact)
    html_after_dedup = """
    <div class="post-content">
        <h2>1. Statutory Architecture & 2026 Directives</h2>
        <p>This is the first comprehensive analysis paragraph explaining statutory requirements and borrower guidelines.</p>
        <h2>2. Statutory Grievance Redressal</h2>
        <p>This is the second comprehensive analysis paragraph explaining Ombudsman escalation and dispute resolution.</p>
        <table><tr><td>State Bank of India</td><td>10.5%</td></tr></table>
        <figure><img src="/img/sample.webp" alt="Inspection"/><figcaption>Caption</figcaption></figure>
        <ul><li>Step 1: Application submission</li><li>Step 2: Verification</li></ul>
        <h2>Frequently Asked Questions</h2>
        <p>This is the third paragraph answering borrower queries regarding application timelines and fees.</p>
    </div>
    """

    ok, msg, data = verify_structural_integrity(html_before, html_after_dedup)
    assert ok is True, f"Heading removal should not trip guard: {msg}"
    assert data["after"]["p"] == data["before"]["p"] == 3
    assert data["after"]["table"] == data["before"]["table"] == 1
    assert data["after"]["figure"] == data["before"]["figure"] == 1
    assert data["after"]["img"] == data["before"]["img"] == 1
    assert data["after"]["list"] == data["before"]["list"] == 1

    # 2. Negative test: Dropped paragraph trips the guard
    html_dropped_p = """
    <div class="post-content">
        <h2>1. Statutory Architecture</h2>
        <p>This is the first comprehensive analysis paragraph explaining statutory requirements and borrower guidelines.</p>
        <table><tr><td>State Bank of India</td><td>10.5%</td></tr></table>
        <figure><img src="/img/sample.webp" alt="Inspection"/></figure>
        <ul><li>Step 1</li></ul>
    </div>
    """
    ok_drop, msg_drop, _ = verify_structural_integrity(html_before, html_dropped_p)
    assert ok_drop is False, "Dropping a paragraph must fail structural verification"
    assert "Structural unit count decreased for <p>" in msg_drop
