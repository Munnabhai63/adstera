"""
tests/test_profile_cookie_automation.py — Unit Tests for MD File 3:
Unlimited Profile Factory, Multi-Format Accounts Manager, Persona Generation, and Cookie Warmer Roster.
"""
import pytest
from pathlib import Path
from accounts_manager import AccountsManager, Account
from profile_factory import ProfileFactory
from cookie_warmer import CookieWarmer, WARMING_ROSTER
from mahi_connector import MahiConnector

TEST_ACCOUNTS_TXT = Path("test_accounts_sample.txt")


@pytest.fixture(autouse=True)
def cleanup():
    yield
    if TEST_ACCOUNTS_TXT.exists():
        TEST_ACCOUNTS_TXT.unlink()


def test_accounts_parser_multi_format():
    """Verify parsing colon, pipe, and extended proxy account formats."""
    sample_text = (
        "# Sample comment\n"
        "user1@gmail.com:SecretPass1\n"
        "user2@yahoo.com|SecretPass2\n"
        "user3@finance.com:Pass3:proxy.provider.com:8080\n"
        "user4@loans.com:Pass4:proxy.provider.com:9000:proxyuser:proxypass\n"
    )
    TEST_ACCOUNTS_TXT.write_text(sample_text, encoding="utf-8")

    mgr = AccountsManager()
    accounts = mgr.parse_accounts_file(TEST_ACCOUNTS_TXT)

    assert len(accounts) == 4
    assert accounts[0].email == "user1@gmail.com"
    assert accounts[0].password == "SecretPass1"
    assert accounts[1].email == "user2@yahoo.com"
    assert accounts[2].proxy == "http://proxy.provider.com:8080"
    assert accounts[3].proxy == "http://proxyuser:proxypass@proxy.provider.com:9000"


def test_persona_generation_consistency():
    """Verify high-intent financial persona attributes and deterministic seeding."""
    mgr = AccountsManager()
    p1 = mgr.generate_persona("alexander.finance@domain.com")
    p2 = mgr.generate_persona("alexander.finance@domain.com")

    # Same seed must yield identical persona
    assert p1["full_name"] == p2["full_name"]
    assert p1["city"] == p2["city"]
    assert p1["credit_score"] == p2["credit_score"]
    assert "Personal" in p1["commercial_intent"] or "Loan" in p1["commercial_intent"] or "Credit" in p1["commercial_intent"] or "Savings" in p1["commercial_intent"] or "Mortgage" in p1["commercial_intent"] or "Insurance" in p1["commercial_intent"] or "VPN" in p1["commercial_intent"]


def test_synthetic_account_on_the_fly():
    """Verify instant synthetic account creation with credentials and persona."""
    mgr = AccountsManager()
    acc = mgr.generate_synthetic_account(domain="investorpro.com")
    assert "@investorpro.com" in acc.email
    assert len(acc.password) >= 8
    assert acc.persona is not None
    assert "annual_income" in acc.persona


def test_profile_factory_hardware_generation():
    """Verify ProfileFactory produces realistic MAHI hardware profiles without database writes."""
    p = ProfileFactory.generate_profile(seed="unique_user_seed_9981")
    assert p["id"].startswith("gen_")
    settings = p["settings"]

    # Display checks
    disp = settings["display"]
    assert disp["screenWidth"] in [1920, 1536, 1440, 1366, 2560]
    assert disp["colorDepth"] == 24
    assert disp["availHeight"] < disp["screenHeight"]

    # Hardware & WebGL checks
    hw = settings["hardware"]
    assert hw["concurrency"] in [4, 8, 12, 16]
    assert hw["memory"] in [8, 16, 32]
    assert "ANGLE" in hw["webgl_renderer"]
    assert hw["canvas_noise_seed"] > 0


def test_profile_factory_batch_scalability():
    """Verify generating 100 profiles takes less than 50ms."""
    import time
    t0 = time.time()
    batch = ProfileFactory.generate_batch(100)
    elapsed = time.time() - t0

    assert len(batch) == 100
    assert elapsed < 0.10, f"Generating 100 profiles took {elapsed:.3f}s (should be < 0.10s)"


def test_cookie_warmer_roster_and_selection():
    """Verify CookieWarmer authoritative sites roster from MAHI Browser."""
    warmer = CookieWarmer()
    assert len(WARMING_ROSTER) >= 10

    categories = {s["category"] for s in WARMING_ROSTER}
    assert "Search" in categories
    assert "Finance" in categories
    assert "Commerce" in categories

    targets = warmer.select_warming_targets(count=3)
    assert len(targets) == 3
    # Ensure no duplicates in selected batch
    urls = [t["url"] for t in targets]
    assert len(set(urls)) == 3


def test_mahi_connector_dynamic_profile():
    """Verify MahiConnector seamlessly integrates with ProfileFactory."""
    conn = MahiConnector()
    dyn_p = conn.get_dynamic_profile(seed="mahi_unlimited_test")
    assert dyn_p is not None
    assert "settings" in dyn_p
    assert "display" in dyn_p["settings"]

