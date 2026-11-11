"""Modular workspace view renderers for AdsterraFleet Vuexy CRM."""

from admin_ui.views.autopublish import render_autopublish_view
from admin_ui.views.growth import render_growth_view
from admin_ui.views.login import render_login_view
from admin_ui.views.monetization import render_monetization_view
from admin_ui.views.network import render_network_view
from admin_ui.views.overview import render_overview_view
from admin_ui.views.profile import render_profile_view
from admin_ui.views.settings import render_settings_view

__all__ = [
    "render_autopublish_view",
    "render_growth_view",
    "render_login_view",
    "render_monetization_view",
    "render_network_view",
    "render_overview_view",
    "render_profile_view",
    "render_settings_view",
]
