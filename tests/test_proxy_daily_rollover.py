"""
tests/test_proxy_daily_rollover.py — Verify date-aware daily usage rollover on Proxy.
"""
import datetime
from pool import Proxy


def test_proxy_daily_rollover_on_is_available():
    p = Proxy(host="1.2.3.4", port=8080)
    p.uses_today = 12
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    p.uses_date = yesterday

    # is_available should detect that uses_date is from yesterday, reset uses_today to 0, and return True
    assert p.is_available(max_uses=12, cooldown_secs=0.0) is True
    assert p.uses_today == 0
    assert p.uses_date == datetime.date.today().isoformat()


def test_proxy_daily_rollover_on_record_use():
    p = Proxy(host="1.2.3.4", port=8080)
    p.uses_today = 12
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    p.uses_date = yesterday

    p.record_use()
    assert p.uses_today == 1
    assert p.uses_date == datetime.date.today().isoformat()

