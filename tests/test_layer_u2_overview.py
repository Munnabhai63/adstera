"""Verification tests for Vuexy CRM Overview Component U2."""

from __future__ import annotations

import json
import urllib.request

from admin_ui.shell import render_crm_shell
from admin_ui.views import render_overview_view, render_settings_view


def test_overview_and_settings_views_contain_required_u2_hooks() -> None:
    overview_html = render_overview_view()
    for marker in (
        'id="view-overview"',
        'id="u2SparkSessions"',
        'id="u2CtrGauge"',
        'id="u2SparkRevenue"',
        'id="u2AnalyticsTablist"',
        'role="tablist"',
        'role="tabpanel"',
        'hidden="until-found"',
        'id="u2ChartHourly"',
        'id="u2ChartForecast"',
        'id="u2ChartDomains"',
        'id="u2ChartDiurnal"',
        'id="u2BtnStart"',
        'id="u2BtnStop"',
        'id="u2BtnForceStop"',
        'id="u2DomainsTbody"',
        'id="u2BtnResetBreakers"',
        'id="u2ActivityTimeline"',
        'id="u2ConsoleBox"',
        '/api/stats/csv',
    ):
        assert marker in overview_html

    settings_html = render_settings_view()
    for marker in (
        'id="view-settings"',
        'id="btnShellPing"',
        'id="u1ApiPingReadout"',
        'id="shellThemeModeReadout"',
    ):
        assert marker in settings_html

    full_html = render_crm_shell()
    assert '/crm-assets/js/crm-overview.js' in full_html


def test_live_crm_u2_overview_assets_and_api_feeds() -> None:
    with urllib.request.urlopen("http://127.0.0.1:5050/crm", timeout=5) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8", errors="ignore")
    assert 'id="u2ChartHourly"' in html
    assert 'id="u2ActivityTimeline"' in html

    with urllib.request.urlopen("http://127.0.0.1:5050/crm-assets/js/crm-overview.js", timeout=5) as js_resp:
        assert js_resp.status == 200
        assert "javascript" in js_resp.headers.get("Content-Type", "")

    with urllib.request.urlopen("http://127.0.0.1:5050/api/analytics/charts", timeout=5) as ch_resp:
        assert ch_resp.status == 200
        charts = json.loads(ch_resp.read().decode("utf-8"))
    assert "hourly" in charts and "forecast_7d" in charts and "domains" in charts

    with urllib.request.urlopen("http://127.0.0.1:5050/api/stats/csv", timeout=5) as csv_resp:
        assert csv_resp.status == 200
        assert "text/csv" in csv_resp.headers.get("Content-Type", "")
