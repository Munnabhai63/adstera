"""
lead_engine.py — High-Payout CPL/CPA Post-Click Lead Conversion Engine.

Pillar 2 of 5 Advanced Enterprise Pillars:
- Dwells on advertiser landing pages after Adsterra Smartlink/Banner clicks
- Heuristically identifies lead capture forms (email, name, zip, phone)
- Ingests high-intent persona details from accounts_manager.py
- Uses human typing cadence (60ms–220ms delay, cognitive hesitation, typos)
- Submits lead forms to trigger $1.50–$4.50 CPL conversion bounties
- Logs conversions to sessions.db (table lead_conversions)
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import random
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

import db
import human
from accounts_manager import AccountsManager, Account
from email_client import SonjjEmailClient

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger(__name__)


def _get_val(obj: Any, key: str, default: str = "") -> str:
    """Safely get value from either dict or object."""
    if isinstance(obj, dict):
        return str(obj.get(key, default))
    return str(getattr(obj, key, default))


class LeadConversionEngine:
    """Post-click advertiser form detection and autonomous human lead submitter."""

    # Priority heuristic selector lists
    EMAIL_SELECTORS = [
        'input[type="email"]',
        'input[name*="email" i]',
        'input[id*="email" i]',
        'input[placeholder*="email" i]',
    ]

    NAME_SELECTORS = [
        'input[name*="full_name" i]',
        'input[name*="fullname" i]',
        'input[id*="fullName" i]',
        'input[name*="first_name" i]',
        'input[name*="firstname" i]',
        'input[id*="firstName" i]',
        'input[name*="name" i]',
        'input[id*="name" i]',
        'input[placeholder*="name" i]',
    ]

    ZIP_SELECTORS = [
        'input[name*="zip" i]',
        'input[id*="zip" i]',
        'input[name*="postal" i]',
        'input[id*="postal" i]',
        'input[placeholder*="zip" i]',
    ]

    PHONE_SELECTORS = [
        'input[type="tel"]',
        'input[name*="phone" i]',
        'input[id*="phone" i]',
        'input[placeholder*="phone" i]',
    ]

    SUBMIT_SELECTORS = [
        'button[type="submit"]',
        'input[type="submit"]',
        'form button',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'button:has-text("Check")',
        'button:has-text("Get Quote")',
        'button:has-text("Continue")',
        'button:has-text("Next")',
        'button:has-text("Verify")',
    ]

    OTP_SELECTORS = [
        'input[autocomplete="one-time-code"]',
        'input[name*="otp" i]',
        'input[id*="otp" i]',
        'input[name*="code" i]',
        'input[id*="code" i]',
        'input[placeholder*="otp" i]',
        'input[placeholder*="code" i]',
    ]

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.accounts_mgr = AccountsManager()
        self.email_client = SonjjEmailClient(config_path=config_path)

        cfg = self.config.get("lead_engine", {})
        self.enabled = cfg.get("enabled", True)
        self.conversion_prob = float(cfg.get("conversion_prob", 0.10))
        self.max_leads_per_day = int(cfg.get("max_leads_per_day", 50))
        self.min_post_click_dwell = float(cfg.get("min_post_click_dwell", 25.0))
        self.max_post_click_dwell = float(cfg.get("max_post_click_dwell", 45.0))
        self.typing_delay_min_ms = int(cfg.get("typing_delay_min_ms", 60))
        self.typing_delay_max_ms = int(cfg.get("typing_delay_max_ms", 220))

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", self.config_path, e)
        return {}

    def should_attempt_conversion(self, rng: Optional[random.Random] = None) -> bool:
        """
        Evaluate whether the current clicked ad session should attempt lead conversion.
        Guards against exceeding daily cap and throttles to natural conversion curve.
        """
        if not self.enabled:
            return False

        r = rng or random.Random()
        # Check daily cap in database
        today_summary = db.today_leads_summary()
        if today_summary["today_leads"] >= self.max_leads_per_day:
            logger.info("Lead Engine: Daily cap of %d leads reached. Throttling.", self.max_leads_per_day)
            return False

        # Natural random threshold (default 10% of clicked ad sessions)
        return r.random() < self.conversion_prob

    async def detect_lead_form(self, page: Any) -> dict[str, Any]:
        """
        Scan page DOM for viable lead capture input fields and submit triggers.
        Returns a mapping of detected field selectors.
        """
        detected: dict[str, Any] = {
            "form_found": False,
            "email_selector": None,
            "name_selector": None,
            "zip_selector": None,
            "phone_selector": None,
            "submit_selector": None,
            "fields_count": 0,
        }

        # Find Email Input (Mandatory for CPL payout)
        for sel in self.EMAIL_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    detected["email_selector"] = sel
                    detected["fields_count"] += 1
                    break
            except Exception:
                continue

        if not detected["email_selector"]:
            return detected

        # Find Name Input
        for sel in self.NAME_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    detected["name_selector"] = sel
                    detected["fields_count"] += 1
                    break
            except Exception:
                continue

        # Find Zip Code Input
        for sel in self.ZIP_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    detected["zip_selector"] = sel
                    detected["fields_count"] += 1
                    break
            except Exception:
                continue

        # Find Phone Input
        for sel in self.PHONE_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    detected["phone_selector"] = sel
                    detected["fields_count"] += 1
                    break
            except Exception:
                continue

        # Find Submit Button
        for sel in self.SUBMIT_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    detected["submit_selector"] = sel
                    break
            except Exception:
                continue

        # Mark viable if email and submit button exist
        if detected["email_selector"] and detected["submit_selector"]:
            detected["form_found"] = True

        return detected

    async def detect_otp_field(self, page: Any) -> Optional[str]:
        """Scan page DOM for a visible OTP / email verification code input field."""
        for sel in self.OTP_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return sel
            except Exception:
                continue
        return None

    async def fill_and_submit_lead(
        self,
        page: Any,
        domain: str = "loanraaj.com",
        persona: Optional[Any] = None,
        rng: Optional[random.Random] = None,
        country: str = "",
    ) -> dict[str, Any]:
        """
        Execute full natural post-click dwell, Sonjj Email provisioning, and form auto-fill:
        1. Natural initial content scroll & reading pause.
        2. Detects inputs.
        3. Generates Geo-Matched Persona + provisions/reuses real Sonjj Email (with SQLite cache & Credit-Guard).
        4. Moves mouse via Bézier curve and types with human cadence.
        5. Clicks submit button.
        6. Checks for post-submit OTP input or verification link via Sonjj inbox polling.
        7. Logs conversion to sessions.db.
        """
        r = rng or random.Random()
        start_time = asyncio.get_event_loop().time()

        # Step 1: Pre-form browsing dwell (3 - 6 seconds)
        try:
            await human.scroll_page(page, rng=r)
            await human.idle_drift(page, duration=r.uniform(2.0, 4.5), rng=r)
        except Exception as e:
            logger.debug("Lead Engine: Pre-form dwell error: %s", e)

        # Step 2: Form Detection
        form_info = await self.detect_lead_form(page)
        if not form_info["form_found"]:
            logger.info("Lead Engine: No actionable lead form detected on %s", page.url)
            dwell_so_far = asyncio.get_event_loop().time() - start_time
            return {
                "success": False,
                "reason": "no_form_found",
                "dwell_sec": round(dwell_so_far, 2),
                "fields_filled": 0,
            }

        # Step 3: Select Geo-Matched Persona + Sonjj Email Provisioning (Cache Reuse -> Sonjj API -> Credit Guard)
        active_persona = persona
        effective_country = (country or "US").upper()
        default_zip = "400001" if effective_country == "IN" else "10001"
        default_phone = "9820456789" if effective_country == "IN" else "(555) 234-5678"
        full_name_str = "Rahul Sharma" if effective_country == "IN" else "Steven Brown"
        zip_str = default_zip
        phone_str = default_phone

        if active_persona is None:
            synth_acc = self.accounts_mgr.generate_synthetic_account(country=effective_country)
            active_persona = synth_acc.persona
            fallback_email = synth_acc.email
        else:
            fallback_email = _get_val(active_persona, "email", "visitor@gmail.com")

        if active_persona:
            full_name_str = _get_val(active_persona, "full_name", full_name_str)
            zip_str = _get_val(active_persona, "zip", default_zip)
            phone_str = _get_val(active_persona, "phone", default_phone)

        prefix_hint = full_name_str.lower().replace(" ", ".")
        try:
            email_info = self.email_client.create_or_reuse_email(prefix_hint=prefix_hint, rng=r)
            email_str = email_info.get("email") or fallback_email
            email_source = email_info.get("source", "synthetic")
            is_real_email = bool(email_info.get("is_real", False))
        except Exception as em_err:
            logger.debug("Lead Engine: Sonjj email fallback notice: %s", em_err)
            email_str = fallback_email
            email_source = "synthetic"
            is_real_email = False

        filled_count = 0

        # Step 4: Human typing into Name field
        if form_info.get("name_selector"):
            try:
                await human.type_text_human(page, form_info["name_selector"], full_name_str, rng=r)
                filled_count += 1
                await asyncio.sleep(r.uniform(0.4, 0.9))
            except Exception as e:
                logger.warning("Lead Engine: Failed typing name: %s", e)

        # Step 5: Human typing into Email field (Mandatory)
        if form_info.get("email_selector"):
            try:
                await human.type_text_human(page, form_info["email_selector"], email_str, rng=r)
                filled_count += 1
                await asyncio.sleep(r.uniform(0.5, 1.1))
            except Exception as e:
                logger.warning("Lead Engine: Failed typing email: %s", e)

        # Step 6: Human typing into Zip Code field
        if form_info.get("zip_selector"):
            try:
                await human.type_text_human(page, form_info["zip_selector"], zip_str, rng=r)
                filled_count += 1
                await asyncio.sleep(r.uniform(0.3, 0.7))
            except Exception as e:
                logger.warning("Lead Engine: Failed typing zip: %s", e)

        # Step 7: Human typing into Phone field (if present)
        if form_info.get("phone_selector"):
            try:
                await human.type_text_human(page, form_info["phone_selector"], phone_str, rng=r)
                filled_count += 1
                await asyncio.sleep(r.uniform(0.4, 0.8))
            except Exception as e:
                logger.warning("Lead Engine: Failed typing phone: %s", e)

        # Step 8: Pre-submit cognitive hesitation pause (1.5 - 3.0s)
        await asyncio.sleep(r.uniform(1.5, 3.0))

        # Step 9: Click Submit Button
        submitted = False
        if form_info.get("submit_selector"):
            sel = form_info["submit_selector"]
            try:
                clicked = await human.click_element(page, sel, rng=r)
                if not clicked:
                    await page.click(sel)
                submitted = True
                logger.info("Lead Engine: Successfully clicked submit button (%s) with email=%s (%s)", sel, email_str, email_source)
            except Exception as e:
                logger.warning("Lead Engine: Error clicking submit: %s", e)

        # Step 10: Post-submit natural dwell & Optional OTP / Verification Link Auto-Completion
        post_dwell = r.uniform(2.5, 6.0)
        try:
            await human.idle_drift(page, duration=post_dwell, rng=r)
        except Exception:
            await asyncio.sleep(post_dwell)

        otp_verified = False
        try:
            otp_sel = await self.detect_otp_field(page)
            if otp_sel or is_real_email:
                inbox_res = self.email_client.extract_otp_or_link(email_str)
                otp_code = inbox_res.get("otp")
                verify_link = inbox_res.get("link")
                if otp_sel and otp_code:
                    await human.type_text_human(page, otp_sel, otp_code, rng=r)
                    filled_count += 1
                    for sub_sel in self.SUBMIT_SELECTORS:
                        el = await page.query_selector(sub_sel)
                        if el and await el.is_visible():
                            await el.click()
                            break
                    otp_verified = True
                    logger.info("Lead Engine: Verified OTP %s for %s", otp_code, email_str)
                elif verify_link:
                    await page.goto(verify_link, wait_until="domcontentloaded", timeout=10000)
                    otp_verified = True
                    logger.info("Lead Engine: Followed email verification link for %s", email_str)
        except Exception as otp_err:
            logger.debug("Lead Engine: Post-submit OTP check notice: %s", otp_err)

        total_dwell = round(asyncio.get_event_loop().time() - start_time, 2)

        # Step 11: Calculate Estimated Bounty ($1.50 - $4.50 based on niche)
        bounty = 2.50
        if "loan" in domain or "karz" in domain:
            bounty = 3.50
        elif "rokda" in domain or "bhav" in domain:
            bounty = 3.00

        # Step 12: Record to SQLite Database
        conversion_id = db.record_lead_conversion(
            domain=domain,
            advertiser_url=page.url[:255],
            email=email_str,
            persona_name=full_name_str,
            fields_filled=filled_count,
            dwell_sec=total_dwell,
            status="verified" if otp_verified else ("submitted" if submitted else "partial"),
            bounty_est=bounty,
        )

        return {
            "success": submitted,
            "conversion_id": conversion_id,
            "domain": domain,
            "advertiser_url": page.url,
            "email": email_str,
            "email_source": email_source,
            "otp_verified": otp_verified,
            "persona_name": full_name_str,
            "fields_filled": filled_count,
            "dwell_sec": total_dwell,
            "bounty_est": bounty,
        }

    def simulate_offline_conversion(
        self,
        domain: str = "loanraaj.com",
        advertiser_url: str = "https://verified-lender.org/apply-cash-loans",
    ) -> dict[str, Any]:
        """Generate and record a simulated lead conversion for offline verification."""
        synth_acc = self.accounts_mgr.generate_synthetic_account()
        persona = synth_acc.persona

        full_name = _get_val(persona, "full_name", "Steven Brown")
        bounty = 3.50 if "loan" in domain else 2.50
        dwell = round(random.uniform(28.0, 42.0), 2)

        cid = db.record_lead_conversion(
            domain=domain,
            advertiser_url=advertiser_url,
            email=synth_acc.email,
            persona_name=full_name,
            fields_filled=4,
            dwell_sec=dwell,
            status="submitted",
            bounty_est=bounty,
        )

        return {
            "conversion_id": cid,
            "domain": domain,
            "advertiser_url": advertiser_url,
            "email": synth_acc.email,
            "persona_name": full_name,
            "fields_filled": 4,
            "dwell_sec": dwell,
            "bounty_est": bounty,
            "status": "submitted",
        }


def print_lead_engine_report(conversions: list[dict[str, Any]]) -> None:
    """Print an eye-readable summary of CPL conversions for manual CMD audit."""
    print("\n" + "=" * 102)
    print(" [+] CPL / CPA LEAD CONVERSION ENGINE REPORT (PILLAR 2)")
    print("=" * 102)
    print(
        f"{'ID':<5} | {'Domain':<16} | {'Persona Name':<18} | {'Email':<26} | "
        f"{'Fields':>6} | {'Dwell':>6} | {'Bounty':>8}"
    )
    print("-" * 102)

    total_bounty = 0.0
    for c in conversions:
        total_bounty += float(c["bounty_est"])
        print(
            f"#{c.get('conversion_id', c.get('id', 1)):<4} | "
            f"{c['domain']:<16} | "
            f"{c['persona_name'][:18]:<18} | "
            f"{c['email'][:26]:<26} | "
            f"{c['fields_filled']:>6} | "
            f"{c['dwell_sec']:>5.1f}s | "
            f"+${c['bounty_est']:>6.2f}"
        )

    print("=" * 102)
    print(
        f"{'TOTAL CONVERSIONS':<44} | "
        f"{len(conversions)} Leads Recorded{'':<20} | "
        f"+${total_bounty:>6.2f}"
    )
    print("=" * 102 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="High-Payout CPL Lead Engine")
    parser.add_argument("--simulate", action="store_true", help="Generate simulated lead conversion in sessions.db")
    parser.add_argument("--count", type=int, default=3, help="Number of simulated conversions")
    parser.add_argument("--history", action="store_true", help="Show recent lead conversions from sessions.db")

    args = parser.parse_args()
    engine = LeadConversionEngine()

    if args.history:
        leads = db.get_lead_conversions(limit=15)
        print_lead_engine_report(leads)
    else:
        results = []
        domains = ["loanraaj.com", "tazaloan.com", "karzseva.com", "rechargetak.com"]
        for i in range(args.count):
            dom = domains[i % len(domains)]
            res = engine.simulate_offline_conversion(domain=dom)
            results.append(res)
        print_lead_engine_report(results)
