"""
tests/test_social_referrers.py — Step 6.2: Social Media Referrer Diversification Tests

Covers:
1. SerpSynthesizer.build_social_referrer_url formats for all target platforms (Facebook, Twitter/X, Reddit, YouTube, Quora)
2. config.yaml referrers and weights alignment (exact same length, weights sum to 1.0)
3. Probabilistic referrer selection produces diverse multi-channel traffic mix
"""
from __future__ import annotations

from pathlib import Path
import random
import sys
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from serp_synthesizer import SerpSynthesizer


def test_social_referrer_url_formats():
    """build_social_referrer_url generates authentic tracking parameters for each network."""
    synth = SerpSynthesizer()
    rng = random.Random(42)

    fb = synth.build_social_referrer_url("loanraaj.com", platform="facebook", rng=rng)
    assert "l.facebook.com" in fb
    assert "loanraaj.com" in fb

    tw = synth.build_social_referrer_url("loanraaj.com", platform="twitter", rng=rng)
    assert "t.co/" in tw

    rd = synth.build_social_referrer_url("loanraaj.com", platform="reddit", rng=rng)
    assert "reddit.com/r/" in rd

    yt = synth.build_social_referrer_url("loanraaj.com", platform="youtube", rng=rng)
    assert "youtube.com" in yt

    qr = synth.build_social_referrer_url("rechargetak.com", platform="quora", rng=rng)
    assert "quora.com" in qr
    print("  [OK] Social referrer URLs verified across Facebook, Twitter, Reddit, YouTube, Quora")


def test_config_referrer_weights_sum_to_one():
    """config.yaml referrers and referrer_weights match in count and weights sum to ~1.0."""
    cfg_path = Path(__file__).parent.parent / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    referrers = cfg["target"]["referrers"]
    weights = cfg["target"]["referrer_weights"]

    assert len(referrers) == len(weights), f"Length mismatch: {len(referrers)} referrers vs {len(weights)} weights"
    assert abs(sum(weights) - 1.0) < 1e-4, f"Weights sum to {sum(weights)}, expected 1.0"

    # Verify social platforms are present
    assert any("facebook.com" in r for r in referrers)
    assert any("t.co" in r for r in referrers)
    assert any("reddit.com" in r for r in referrers)
    assert any("youtube.com" in r for r in referrers)
    print("  [OK] config.yaml referrer diversity and normalized weights verified")


def test_probabilistic_referrer_distribution():
    """Sampling referrers produces natural multi-channel blend across Google, Direct, and Social."""
    cfg_path = Path(__file__).parent.parent / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    referrers = cfg["target"]["referrers"]
    weights = cfg["target"]["referrer_weights"]
    rng = random.Random(101)

    sampled = rng.choices(referrers, weights=weights, k=1000)
    has_social = any("facebook" in s or "t.co" in s or "reddit" in s or "youtube" in s for s in sampled)
    has_search = any("google" in s or "bing" in s or "duckduckgo" in s for s in sampled)
    has_direct = any(s == "" for s in sampled)

    assert has_social, "Social traffic should be present in 1000 sessions"
    assert has_search, "Search traffic should be present in 1000 sessions"
    assert has_direct, "Direct traffic should be present in 1000 sessions"
    print("  [OK] Multi-channel traffic distribution verified")


if __name__ == "__main__":
    test_social_referrer_url_formats()
    test_config_referrer_weights_sum_to_one()
    test_probabilistic_referrer_distribution()
    print("\nAll social referrer tests PASSED!")
