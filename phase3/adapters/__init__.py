"""Phase 3 adapter wrappers around Phase 1 and Phase 2 modules."""
from phase3.adapters.adsterra_feed import AdsterraFeedAdapter
from phase3.adapters.phase1_device import (
    DeviceDisconnectedError,
    DeviceTouchCaptureBridge,
    Phase1DeviceAdapter,
)
from phase3.adapters.phase2_ai import Phase2AIAdapter
from phase3.adapters.revenue_legacy import RevenueLegacyAdapter
from phase3.adapters.seo_legacy import SEOLegacyAdapter

__all__ = [
    "AdsterraFeedAdapter",
    "DeviceDisconnectedError",
    "DeviceTouchCaptureBridge",
    "Phase1DeviceAdapter",
    "Phase2AIAdapter",
    "RevenueLegacyAdapter",
    "SEOLegacyAdapter",
]
