"""Verification tests for Vuexy CRM Component U3 (AutoPublish & 20-Topic CMS)."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from admin_ui.shell import render_crm_shell
from admin_ui.views.autopublish import DOMAINS_META, render_autopublish_view


def test_autopublish_view_structure_and_a11y_contracts() -> None:
    html = render_autopublish_view()
    assert 'id="view-autopublish"' in html
    assert 'id="u3DomainSelect"' in html
    assert 'id="u3DomainPills"' in html
    assert 'id="u3StepperTrack"' in html
    assert 'id="u3FleetGrid"' in html
    assert 'id="u3CandidatesTable"' in html
    assert 'id="u3PublishedTable"' in html

    for slug, _, _ in DOMAINS_META:
        assert f'value="{slug}"' in html

    for btn_id in ("u3BtnScout20", "u3BtnKick", "u3BtnBatch", "u3BtnTrigger"):
        assert f'id="{btn_id}"' in html

    # Sortable & responsive table contract per modern-web-guidance
    assert 'role="region"' in html
    assert 'aria-labelledby="u3CandidatesCaption"' in html
    assert '<th scope="col" aria-sort="descending">' in html
    assert 'class="u3-sort-btn" data-sort-key="composite"' in html

    # Native <dialog> contract: no role="dialog" or aria-modal on <dialog>
    dialog_open_tag = re.search(r"<dialog\b[^>]*>", html)
    assert dialog_open_tag is not None
    tag_str = dialog_open_tag.group(0)
    assert 'id="u3PreviewDialog"' in tag_str
    assert "role=" not in tag_str
    assert "aria-modal=" not in tag_str
    assert 'id="u3PreviewCloseBtn"' in html and "autofocus" in html
    assert 'id="u3PreviewModeDesktop"' in html
    assert 'id="u3PreviewModeMobile"' in html
    assert 'sandbox="allow-popups allow-popups-to-escape-sandbox"' in html


def test_crm_shell_embeds_u3_and_removes_autopublish_placeholder() -> None:
    shell_html = render_crm_shell()
    assert 'id="view-autopublish"' in shell_html
    assert 'id="u3PreviewDialog"' in shell_html
    assert '<script src="/crm-assets/js/crm-autopublish.js"></script>' in shell_html
    assert "AutoPublish &amp; 20-Topic CMS (Layer U3)" not in shell_html
    assert "Open Working AutoPublish (/autopublish)" not in shell_html


def test_live_u3_routes_and_autopublish_apis() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/crm", timeout=5) as resp:
        assert resp.status == 200
        crm_html = resp.read().decode("utf-8", errors="ignore")
    assert 'id="u3PreviewDialog"' in crm_html
    assert "/crm-assets/js/crm-autopublish.js" in crm_html

    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/js/crm-autopublish.js", timeout=5) as js_resp:
        assert js_resp.status == 200
        js_text = js_resp.read().decode("utf-8", errors="ignore")
    assert "applyCandidateSort" in js_text
    assert "openArticlePreview" in js_text

    # Stats endpoint across active domain + fleet
    with urllib.request.urlopen("http://127.0.0.1:5050/api/autopublish/stats?domain=tazaloan", timeout=10) as s_resp:
        assert s_resp.status == 200
        stats = json.loads(s_resp.read().decode("utf-8"))
    assert stats["active_domain"] == "tazaloan"
    assert isinstance(stats.get("candidates"), list) and len(stats["candidates"]) >= 1
    assert isinstance(stats.get("all_pipelines"), dict)
    assert isinstance(stats.get("pending_by_domain"), dict)
    assert "speed_config" in stats

    # Non-destructive preview fetch for first available post
    posts = stats.get("posts") or []
    if posts:
        first = posts[0]
        q = urllib.parse.urlencode({"domain": first["domain"], "slug": first["slug"]})
        with urllib.request.urlopen(f"http://127.0.0.1:5050/api/autopublish/preview?{q}", timeout=10) as p_resp:
            assert p_resp.status == 200
            prev_html = p_resp.read().decode("utf-8", errors="ignore")
        assert "<html" in prev_html.lower() or "<h1" in prev_html.lower()

    # Non-destructive kick call (explicit empty list touches no running stages)
    req = urllib.request.Request(
        "http://127.0.0.1:5050/api/autopublish/kick",
        data=json.dumps({"domains": []}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as k_resp:
        assert k_resp.status == 200
        kick_res = json.loads(k_resp.read().decode("utf-8"))
    assert kick_res.get("success") is True

    # Legacy /autopublish must remain 100% accessible
    with urllib.request.urlopen("http://127.0.0.1:5050/autopublish", timeout=5) as leg_resp:
        assert leg_resp.status == 200
        leg_html = leg_resp.read().decode("utf-8", errors="ignore")
    assert "20-Topic" in leg_html or "AutoPublish" in leg_html


def test_sanitize_preview_html_strips_scripts_and_inline_handlers() -> None:
    import autopublish_service

    dirty = (
        '<html><head><style>body{color:red}</style><script>alert(1)</script></head>'
        '<body><h1 onclick="evil()">Title</h1><input oninput="calc()">'
        '<a href="javascript:alert(2)">Link</a></body></html>'
    )
    clean = autopublish_service.sanitize_preview_html(dirty)
    assert "<script" not in clean.lower()
    assert "alert(1)" not in clean
    assert "onclick=" not in clean.lower()
    assert "oninput=" not in clean.lower()
    assert "javascript:" not in clean.lower()
    assert "<style>body{color:red}</style>" in clean
    assert "<h1>Title</h1>" in clean
