"""
adsterra_links.py — Centralized, authoritative Adsterra Direct Links mapping
for all 10 network publisher domains.

Each domain is mapped to its dedicated high-eCPM Adsterra direct link with
niche-tailored, high-converting copy for native in-article cards, header
recommendations, sidebar widgets, and calculator CTAs.
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ADSTERRA_DIRECT_LINKS: dict[str, dict[str, str]] = {
    "loanraaj": {
        "url": "https://araplhn.org/4/17dc693c036f3b211f48887d232add4b",
        "badge": "Commercial Finance Partner",
        "title": "Commercial Vehicle & MSME Loan Pre-Approval",
        "desc": "Check competitive APRs, collateral-free credit limits, and fast-track business loan approvals with leading financial institutions.",
        "cta": "Check Pre-Approved Rates →",
        "calc_cta": "Apply for this Loan Amount →",
        "icon": "🚛",
    },
    "rechargetak": {
        "url": "https://araplhn.org/4/36def2a0119696fb23e3fe034ccfcbc6",
        "badge": "Sponsored Telecom Rewards",
        "title": "Unlimited 5G Data & OTT Combo Cashback",
        "desc": "Unlock up to ₹150 instant cashback voucher on annual recharge packs, 5G data boosters, and FASTag highway top-ups.",
        "cta": "Claim Recharge Rewards →",
        "calc_cta": "Activate Discount Plan →",
        "icon": "📱",
    },
    "rechargepur": {
        "url": "https://araplhn.org/4/efed43a0653e93bd1dc62b74d42e4c6a",
        "badge": "Official Utility Partner",
        "title": "Smart Meter Electricity & Cooking Gas Rebate",
        "desc": "Claim government subsidy rebates and instant UPI discount vouchers on your municipal bill payments and gas refills.",
        "cta": "Check Utility Subsidies →",
        "calc_cta": "Reduce Household Bill Expenses →",
        "icon": "⚡",
    },
    "tazaloan": {
        "url": "https://araplhn.org/4/b85c5d24beb88d58bfb4e161e1f74dd9",
        "badge": "Digital Credit Offer",
        "title": "Paperless Instant Cash Personal Loan",
        "desc": "Disbursal in 60 minutes, zero physical paperwork, low CIBIL considerations, and pre-approved digital credit lines up to ₹5,00,000.",
        "cta": "Check Instant Eligibility →",
        "calc_cta": "Apply for this Monthly EMI →",
        "icon": "💸",
    },
    "loankiseva": {
        "url": "https://araplhn.org/4/2caa4b8918499ce7fd21fc1b92ec94aa",
        "badge": "MSME Scheme Desk",
        "title": "CGTMSE Collateral-Free Business Credit",
        "desc": "PMEGP subsidy applications, industrial machinery lease financing, and fast-tracked SIDBI commercial working capital.",
        "cta": "Apply for MSME Subsidy →",
        "calc_cta": "Submit Scheme Application →",
        "icon": "🏭",
    },
    "karzseva": {
        "url": "https://araplhn.org/4/8b6f18f361f42dc7c2c708b4ce5f6f28",
        "badge": "Legal Settlement Partner",
        "title": "One-Time Bank Settlement (OTS) Relief",
        "desc": "Legally settle unmanageable credit card debts with up to 60% principal waivers and dispute negative credit bureau reporting.",
        "cta": "Get Free Debt Evaluation →",
        "calc_cta": "Calculate Settlement Savings →",
        "icon": "🛡️",
    },
    "loantau": {
        "url": "https://araplhn.org/4/5758e39593ed52767a2328758c2683da",
        "badge": "Kisan Credit Desk",
        "title": "KCC 4% Subsidized Agriculture Credit",
        "desc": "Low-interest crop loans, tractor purchase finance, solar pump subsidies, and NABARD rural dairy enterprise funding.",
        "cta": "Check Kisan Eligibility →",
        "calc_cta": "Check Subsidized Interest →",
        "icon": "🌾",
    },
    "tazabhav": {
        "url": "https://araplhn.org/4/ca5b06c43def4844f857da9379d3229d",
        "badge": "Live Bullion Desk",
        "title": "Digital Gold & Sovereign Commodity Trading",
        "desc": "Access live 24K MCX bullion spot rates, buy digital gold starting at ₹10, and accumulate pure bullion with zero vault fees.",
        "cta": "Explore Live Rates →",
        "calc_cta": "View Current Bullion Spreads →",
        "icon": "🥇",
    },
    "tazarokda": {
        "url": "https://araplhn.org/4/683357397a7ae6ec26a028b4100a876c",
        "badge": "Direct Investment Partner",
        "title": "Zero-Brokerage Demat & High-CAGR SIPs",
        "desc": "Open lifetime free demat account with zero maintenance fee and invest in direct zero-commission mutual funds and index funds.",
        "cta": "Open Free Demat Account →",
        "calc_cta": "Start This SIP Investment →",
        "icon": "📈",
    },
    "rechargekar": {
        "url": "https://araplhn.org/4/7a123d148c127cf4f54df5374d59a985",
        "badge": "Exclusive Entertainment Offer",
        "title": "Multi-Room DTH & Family Telecom Pack",
        "desc": "Save up to 30% annually on Tata Play, Airtel DTH, Dish TV, and pooled postpaid family telecom connections.",
        "cta": "Claim Family DTH Offer →",
        "calc_cta": "Save on Annual DTH →",
        "icon": "📺",
    },
}

# Aliases for domain names with .com and http/https
for short_name, data in list(ADSTERRA_DIRECT_LINKS.items()):
    ADSTERRA_DIRECT_LINKS[f"{short_name}.com"] = data
    ADSTERRA_DIRECT_LINKS[f"https://{short_name}.com"] = data
    ADSTERRA_DIRECT_LINKS[f"http://{short_name}.com"] = data


def get_adsterra_config(domain_or_key: str) -> dict[str, str]:
    """
    Look up the exact Adsterra configuration for any domain or key.
    Defaults to loanraaj configuration if unmatched.
    """
    clean = domain_or_key.lower().replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    if clean in ADSTERRA_DIRECT_LINKS:
        return ADSTERRA_DIRECT_LINKS[clean]
    
    # Try stripping .com
    prefix = clean.replace(".com", "")
    if prefix in ADSTERRA_DIRECT_LINKS:
        return ADSTERRA_DIRECT_LINKS[prefix]
        
    return ADSTERRA_DIRECT_LINKS["loanraaj"]


def render_native_ad_card(domain_or_key: str) -> str:
    """Generate high-CTR, responsive native in-article sponsored card HTML."""
    cfg = get_adsterra_config(domain_or_key)
    return f"""
    <div class="native-ad-card">
        <div class="native-ad-badge">{cfg['badge']}</div>
        <div class="native-ad-body">
            <div class="native-ad-icon">{cfg['icon']}</div>
            <div class="native-ad-text">
                <h4 class="native-ad-title">{cfg['title']}</h4>
                <p class="native-ad-desc">{cfg['desc']}</p>
            </div>
            <a href="{cfg['url']}" target="_blank" rel="noopener sponsored" class="native-ad-btn">{cfg['cta']}</a>
        </div>
    </div>
    """


def render_sidebar_ad_widget(domain_or_key: str) -> str:
    """Generate responsive sidebar sponsored widget HTML."""
    cfg = get_adsterra_config(domain_or_key)
    return f"""
    <div class="widget-card sidebar-ad-card">
        <div class="sidebar-ad-tag">{cfg['badge']}</div>
        <div class="sidebar-ad-icon">{cfg['icon']}</div>
        <h4 class="sidebar-ad-title">{cfg['title']}</h4>
        <p class="sidebar-ad-desc">{cfg['desc']}</p>
        <a href="{cfg['url']}" target="_blank" rel="noopener sponsored" class="sidebar-ad-btn">{cfg['cta']}</a>
    </div>
    """


ADSTERRA_SCRIPTS: dict[str, dict[str, str]] = {
    "rechargetak": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/dc41505f499f4766916a1efc1fcc260c"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/bf2db224e6b41f48796445afdf3e666b"></script>',
    },
    "tazaloan": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/7c72b09e2f9b8efbeffc6adf72b46383"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/05f860490762d69285aa3dccbf6b7cee"></script>',
    },
    "tazabhav": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/4af55666d78005635674d84ca5705dc3"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/768c05ff622a4e818f439d86f0a45823"></script>',
    },
    "rechargepur": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/8921db9b7c660d20aee2be0f5e708fcc"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/79732d673f8eb0607b192edc9dc6a3b5"></script>',
    },
    "loankiseva": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/8c01d8d0e2d9e28a5b16ea2030075464"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/aaa958f01b1a81eaf466d3c9a001a862"></script>',
    },
    "loanraaj": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/469818ae009e95c4d51277eb83956347"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/33f1a7d198b5423ebc2a315b8eb76d52"></script>',
    },
    "karzseva": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/60fe0e370671a9c4feb05cbaf4af39aa"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/0278c131d8a4ef8d08fef6c937ccd0d2"></script>',
    },
    "loantau": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/4bed4e6942d4d450068417705aab2055"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/6bb0516e01dc9bdfe29ec03aee2a4e0d"></script>',
    },
    "tazarokda": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/2cb8a2b93f18d3107c54c7cd67102652"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/0f4d1c559ba16b9c12fc6d564c679bf5"></script>',
    },
    "rechargekar": {
        "popunder": '<script data-cfasync="false" src="https://abscloud.org/1/02d7469ada7886443b3c4deff2a923cb"></script>',
        "socialbar": '<script data-cfasync="false" src="https://bauval.org/14/e742775cc78d4b7bb87893991c674116"></script>',
    },
}

def render_adsterra_scripts(domain_or_key: str) -> str:
    """Generate official Adsterra Popunder + SocialBar script block."""
    clean = _normalize_domain_key(domain_or_key)
    info = ADSTERRA_SCRIPTS.get(clean) or ADSTERRA_SCRIPTS["loanraaj"]
    return f"""
    <!-- Adsterra Monetization Engine -->
    {info['popunder']}
    {info['socialbar']}
    """


# ── Layer 1: Display Banner & Native Adsterra Slot Engine ────────────────────────

BANNER_STATE_PATH = Path(__file__).resolve().parent / "state" / "adsterra_banners.json"

BANNER_SLOT_SPECS: dict[str, dict[str, Any]] = {
    "banner_728x90": {
        "marker": "728x90",
        "css_class": "adsterra-leaderboard-wrap",
        "slot_attr": "adsterra-728x90",
        "label": "Sponsored Advertisement",
        "api_title": "728x90_1",
        "width": 728,
        "height": 90,
    },
    "banner_300x250": {
        "marker": "300x250",
        "css_class": "adsterra-mrec-wrap",
        "slot_attr": "adsterra-300x250",
        "label": "Sponsored",
        "api_title": "300x250_1",
        "width": 300,
        "height": 250,
    },
    "native_banner": {
        "marker": "native",
        "css_class": "adsterra-native-wrap",
        "slot_attr": "adsterra-native",
        "label": "Recommended Partners",
        "api_title": "NativeBanner_1",
        "width": None,
        "height": None,
    },
}

SLOT_ALIASES: dict[str, str] = {
    "728x90": "banner_728x90",
    "banner_728x90": "banner_728x90",
    "728x90_1": "banner_728x90",
    "leaderboard": "banner_728x90",
    "300x250": "banner_300x250",
    "banner_300x250": "banner_300x250",
    "300x250_1": "banner_300x250",
    "mrec": "banner_300x250",
    "native": "native_banner",
    "native_banner": "native_banner",
    "nativebanner": "native_banner",
    "nativebanner_1": "native_banner",
}

_DUMMY_MARKERS = (
    "placeholder",
    "dummy",
    "your-zone-code",
    "your-ad-zone-key",
    "example.com",
    "00000000000000000000000000000000",
    "11111111111111111111111111111111",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
)

_banner_cache: dict[str, Any] = {"mtime": -1.0, "data": {"domains": {}}}
ADSTERRA_DISPLAY_BANNERS: dict[str, dict[str, Any]] = {}


def _normalize_domain_key(domain_or_key: str) -> str:
    clean = (domain_or_key or "").strip().lower()
    clean = clean.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    if clean.startswith("www."):
        clean = clean[4:]
    return clean.replace(".com", "")


def normalize_slot_name(slot: str) -> str:
    key = (slot or "").strip().lower()
    if key not in SLOT_ALIASES:
        raise ValueError(f"Unsupported banner slot: {slot!r}")
    return SLOT_ALIASES[key]


def load_banner_state(force: bool = False) -> dict[str, Any]:
    """Load persistent display banner registry, auto-refreshing when file mtime changes."""
    global ADSTERRA_DISPLAY_BANNERS
    if not BANNER_STATE_PATH.exists():
        _banner_cache["mtime"] = -1.0
        _banner_cache["data"] = {"domains": {k: {} for k in ADSTERRA_SCRIPTS}}
        ADSTERRA_DISPLAY_BANNERS = _banner_cache["data"]["domains"]
        return _banner_cache["data"]

    mtime = BANNER_STATE_PATH.stat().st_mtime
    if not force and mtime == _banner_cache["mtime"]:
        return _banner_cache["data"]

    try:
        raw = json.loads(BANNER_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {"domains": {}}
        if "domains" not in raw or not isinstance(raw["domains"], dict):
            raw["domains"] = {}
        _banner_cache["mtime"] = mtime
        _banner_cache["data"] = raw
        ADSTERRA_DISPLAY_BANNERS = raw["domains"]
    except Exception:
        _banner_cache["data"] = {"domains": {}}
        ADSTERRA_DISPLAY_BANNERS = {}
    return _banner_cache["data"]


def save_banner_state(state: dict[str, Any]) -> None:
    """Persist display banner registry atomically and update module cache."""
    global ADSTERRA_DISPLAY_BANNERS
    BANNER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp_path = BANNER_STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, BANNER_STATE_PATH)
    _banner_cache["mtime"] = BANNER_STATE_PATH.stat().st_mtime
    _banner_cache["data"] = state
    ADSTERRA_DISPLAY_BANNERS = state.get("domains", {})


def parse_banner_snippet(raw_snippet: str, forced_slot: str | None = None) -> dict[str, Any]:
    """
    Validate and normalize an authentic Adsterra Display Banner or NativeBanner snippet.
    Rejects empty, unauthenticated, malformed, or placeholder scripts.
    """
    snippet = (raw_snippet or "").strip()
    if not snippet or "<script" not in snippet.lower():
        raise ValueError("Snippet must contain a valid Adsterra <script> tag.")

    low = snippet.lower()
    if any(marker in low for marker in _DUMMY_MARKERS):
        raise ValueError("Rejected placeholder or dummy snippet marker.")

    # Detect Standard atOptions banner (<script>atOptions = { 'key': '<32-hex>', ... }</script> + invoke/anti-adblock script)
    key_match = re.search(r"""['"]key['"]\s*:\s*['"]([a-f0-9]{32})['"]""", snippet, re.IGNORECASE)
    width_match = re.search(r"""['"]width['"]\s*:\s*(\d+)""", snippet, re.IGNORECASE)
    height_match = re.search(r"""['"]height['"]\s*:\s*(\d+)""", snippet, re.IGNORECASE)
    invoke_match = re.search(
        r"""<script[^>]+src=['"]((?:https?:)?//[^'"]+/([a-f0-9]{32})(?:/invoke\.js)?(?:\?[^'"]*)?)['"][^>]*>\s*</script>""",
        snippet,
        re.IGNORECASE,
    )
    container_match = re.search(r"""id=['"]container-([a-f0-9]{32})['"]""", snippet, re.IGNORECASE)

    detected_slot: str | None = None
    zone_key: str | None = None

    if key_match and invoke_match:
        zone_key = key_match.group(1).lower()
        if invoke_match.group(2).lower() != zone_key:
            raise ValueError("Mismatched zone key between atOptions and invoke.js URL.")
        w = int(width_match.group(1)) if width_match else None
        h = int(height_match.group(1)) if height_match else None
        if w == 728 and h == 90:
            detected_slot = "banner_728x90"
        elif w == 300 and h == 250:
            detected_slot = "banner_300x250"
        elif w and h:
            detected_slot = f"banner_{w}x{h}"
    elif invoke_match and container_match:
        zone_key = invoke_match.group(2).lower()
        if container_match.group(1).lower() != zone_key:
            raise ValueError("Mismatched zone key between NativeBanner script and container div.")
        detected_slot = "native_banner"
    else:
        raise ValueError(
            "Unrecognized Adsterra tag format. Expected atOptions+invoke.js or NativeBanner invoke.js+container div with 32-hex key."
        )

    if any(m in zone_key for m in _DUMMY_MARKERS):
        raise ValueError("Rejected dummy 32-hex key.")

    final_slot = normalize_slot_name(forced_slot) if forced_slot else detected_slot
    if not final_slot or final_slot not in BANNER_SLOT_SPECS:
        raise ValueError(f"Detected format {detected_slot!r} is not an active slot (use 300x250, 728x90, or native).")

    if forced_slot and detected_slot and normalize_slot_name(forced_slot) != detected_slot:
        raise ValueError(f"Snippet is {detected_slot}, which does not match target slot {final_slot}.")

    return {
        "slot": final_slot,
        "zone_key": zone_key,
        "snippet": snippet,
        "verified": True,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }


def register_banner_snippet(domain_or_key: str, raw_snippet: str, slot: str | None = None) -> dict[str, Any]:
    """Validate and save one Adsterra display/native banner snippet into state/adsterra_banners.json."""
    dom = _normalize_domain_key(domain_or_key)
    if dom not in ADSTERRA_SCRIPTS:
        raise ValueError(f"Unknown network domain: {domain_or_key!r}")

    parsed = parse_banner_snippet(raw_snippet, forced_slot=slot)
    target_slot = parsed["slot"]

    state = load_banner_state(force=True)
    dom_entry = state.setdefault("domains", {}).setdefault(dom, {})
    slot_entry = dom_entry.setdefault("slots", {}).setdefault(target_slot, {})
    slot_entry.update(
        {
            "zone_key": parsed["zone_key"],
            "snippet": parsed["snippet"],
            "verified": True,
            "added_at": parsed["added_at"],
        }
    )
    save_banner_state(state)
    return {
        "domain": f"{dom}.com",
        "slot": target_slot,
        "zone_key": parsed["zone_key"],
        "placement_id": slot_entry.get("placement_id"),
    }


def register_bulk_snippets(domain_or_key: str, bulk_text: str) -> list[dict[str, Any]]:
    """
    Parse multiple Adsterra banner snippets pasted together for a single domain
    (e.g. 728x90 + 300x250 + NativeBanner concatenated in one textarea) and save all valid ones.
    """
    _script_src_pat = (
        r"<script[^>]+src=['\"](?:https?:)?//[^'\"]+/[a-f0-9]{32}(?:/invoke\.js)?(?:\?[^'\"]*)?['\"][^>]*>\s*</script>"
    )
    _container_pat = r"<div[^>]+id=['\"]container-[a-f0-9]{32}['\"][^>]*>\s*</div>"
    _at_opts_pat = r"<script[^>]*>(?:(?!</script>)[\s\S])*?atOptions(?:(?!</script>)[\s\S])*?</script>"
    chunks = re.findall(
        rf"(?:{_at_opts_pat}\s*{_script_src_pat}|{_script_src_pat}\s*{_container_pat}|{_container_pat}\s*{_script_src_pat})",
        bulk_text or "",
        re.IGNORECASE,
    )
    if not chunks:
        return [register_banner_snippet(domain_or_key, bulk_text)]

    results = []
    for chunk in chunks:
        results.append(register_banner_snippet(domain_or_key, chunk))
    return results


async def sync_placements_from_api_async() -> dict[str, Any]:
    """Fetch official Adsterra domain_ids and all 60 placement_ids via AdsterraApiClient."""
    from adsterra_api import AdsterraApiClient

    client = AdsterraApiClient()
    if client.is_mock_mode():
        raise RuntimeError("ADSTERRA_API_KEY not configured; refusing to sync mock placement IDs.")

    domains_list = await client.fetch_publisher_domains()
    placements_list = await client.fetch_placements()

    dom_id_to_short: dict[int, str] = {}
    state = load_banner_state(force=True)
    domains_state = state.setdefault("domains", {})

    for d in domains_list:
        title = (d.get("title") or "").strip().lower()
        short = _normalize_domain_key(title)
        if short in ADSTERRA_SCRIPTS:
            dom_id_to_short[int(d["id"])] = short
            entry = domains_state.setdefault(short, {})
            entry["domain"] = f"{short}.com"
            entry["adsterra_domain_id"] = int(d["id"])
            entry.setdefault("slots", {})
            entry.setdefault("other_placements", {})

    api_title_to_slot = {spec["api_title"].lower(): slot_name for slot_name, spec in BANNER_SLOT_SPECS.items()}
    synced_count = 0

    for p in placements_list:
        did = p.get("domain_id")
        if did not in dom_id_to_short:
            continue
        short = dom_id_to_short[did]
        title = (p.get("title") or "").strip()
        pid = int(p["id"])
        slot_key = api_title_to_slot.get(title.lower())
        entry = domains_state[short]
        if slot_key:
            slot_obj = entry["slots"].setdefault(slot_key, {})
            slot_obj["placement_id"] = pid
            slot_obj["title"] = title
            synced_count += 1
        else:
            other = entry["other_placements"].setdefault(title, {})
            other["placement_id"] = pid
            if p.get("direct_url"):
                other["direct_url"] = p["direct_url"]
            synced_count += 1

    state["last_api_sync"] = datetime.now(timezone.utc).isoformat()
    save_banner_state(state)
    return {"domains": len(dom_id_to_short), "placements_synced": synced_count}


def sync_placements_from_api() -> dict[str, Any]:
    """Synchronous wrapper to refresh official Adsterra placement IDs into state/adsterra_banners.json."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(sync_placements_from_api_async())
    raise RuntimeError("Call sync_placements_from_api_async() inside an active event loop.")


def get_banner_inventory() -> list[dict[str, Any]]:
    """Return live configuration status of all 10 domains x 3 display slots without fake defaults."""
    state = load_banner_state()
    domains_state = state.get("domains", {})
    inventory: list[dict[str, Any]] = []
    for short in ADSTERRA_SCRIPTS:
        entry = domains_state.get(short, {})
        slots_data = entry.get("slots", {})
        slots_summary: dict[str, Any] = {}
        configured_slots = 0
        for slot_key, spec in BANNER_SLOT_SPECS.items():
            s = slots_data.get(slot_key, {})
            snippet = (s.get("snippet") or "").strip()
            zone_key = s.get("zone_key")
            is_ready = bool(snippet and zone_key)
            if is_ready:
                configured_slots += 1
            slots_summary[slot_key] = {
                "marker": spec["marker"],
                "api_title": spec["api_title"],
                "placement_id": s.get("placement_id"),
                "configured": is_ready,
                "zone_key_preview": f"{zone_key[:6]}...{zone_key[-4:]}" if zone_key else None,
            }
        inventory.append(
            {
                "short_name": short,
                "domain": f"{short}.com",
                "adsterra_domain_id": entry.get("adsterra_domain_id"),
                "configured_count": configured_slots,
                "total_slots": len(BANNER_SLOT_SPECS),
                "slots": slots_summary,
            }
        )
    return inventory


def render_display_banner(domain_or_key: str, slot: str = "300x250", wrap_markers: bool = True) -> str:
    """
    Render an authentic Adsterra Display Banner (728x90, 300x250) or NativeBanner widget.
    If no verified snippet is saved yet for this domain/slot, renders ONLY invisible slot mount
    markers (zero dummy divs, zero placeholder clutter).
    """
    slot_key = normalize_slot_name(slot)
    spec = BANNER_SLOT_SPECS[slot_key]
    marker = spec["marker"]
    start_tag = f"<!-- ADSTERRA_SLOT:{marker} -->"
    end_tag = f"<!-- /ADSTERRA_SLOT:{marker} -->"

    short = _normalize_domain_key(domain_or_key)
    state = load_banner_state()
    slot_info = state.get("domains", {}).get(short, {}).get("slots", {}).get(slot_key, {})
    snippet = (slot_info.get("snippet") or "").strip()

    if not snippet or not slot_info.get("zone_key"):
        return f"{start_tag}{end_tag}" if wrap_markers else ""

    inner = (
        f'<div class="adsterra-slot-wrap {spec["css_class"]} ad-unit" '
        f'data-ad-slot="{spec["slot_attr"]}">'
        f'<div class="adsterra-slot-tag">{spec["label"]}</div>'
        f'<div class="adsterra-slot-frame">{snippet}</div>'
        f"</div>"
    )
    if wrap_markers:
        return f"{start_tag}\n{inner}\n{end_tag}"
    return inner


ADSTERRA_BANNER_CSS = """
/* Adsterra Responsive Display Banner & Native Slots (Layer 1) */
.adsterra-slot-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    max-width: 100%;
    overflow-x: auto;
    box-sizing: border-box;
}
.adsterra-slot-tag {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.9px;
    color: #94A3B8;
    margin-bottom: 6px;
}
.adsterra-slot-frame {
    max-width: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
}
.adsterra-leaderboard-wrap {
    margin: 16px auto 0 auto;
    padding: 8px 12px;
    background: #FFFFFF;
    border: 1px solid var(--border, #E2E8F0);
    border-radius: 8px;
    max-width: 760px;
}
.adsterra-mrec-wrap {
    margin: 0 auto 24px auto;
    padding: 12px;
    background: #FFFFFF;
    border: 1px solid var(--border, #E2E8F0);
    border-radius: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.03);
}
.adsterra-native-wrap {
    margin: 28px 0;
    padding: 16px 18px;
    background: #F8FAFC;
    border: 1px solid var(--border, #E2E8F0);
    border-radius: 10px;
}
"""


# Initialize module-level ADSTERRA_DISPLAY_BANNERS on import
load_banner_state()
