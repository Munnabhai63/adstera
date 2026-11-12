"""A5 Anti-AI SEO Quality Gate (Burstiness + Zipf Entropy & Slope).

Enforces natural human editorial variance before publishing, stripping HTML
tags and invisible Unicode watermarks cleanly and validating every metric
against `phase3/config.yaml -> a5_seo_gate`.
"""
from __future__ import annotations

import html
import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List

from phase3.a5_seo_gate import resolve_a5_config
from phase3.logging_utils import log_event

logger = logging.getLogger("phase3.a5_seo_gate.quality_gate")

_INVISIBLE_WATERMARKS_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]"
)
_STRIP_BLOCKS_RE = re.compile(
    r"<(script|style|noscript|svg|template)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_BLOCK_BREAK_TAGS_RE = re.compile(
    r"</?(?:p|div|h[1-6]|li|tr|blockquote|article|section|header|footer|br|hr)[^>]*>",
    re.IGNORECASE,
)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_SENTENCE_SPLIT_RE = re.compile(r"(?<!\d)[.!?]+(?:\s+|$)|\n+")
_WORD_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


def _strip_html(raw: str) -> str:
    """Strip scripts/styles/tags, decode entities, and preserve block boundaries."""
    text = _INVISIBLE_WATERMARKS_RE.sub("", raw)
    text = _STRIP_BLOCKS_RE.sub(" ", text)
    text = _BLOCK_BREAK_TAGS_RE.sub("\n", text)
    text = _ANY_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _compute_burstiness(sentence_lengths: List[int]) -> float:
    """Coefficient of variation (std / mean) of sentence token lengths."""
    if not sentence_lengths:
        return 0.0
    mean = sum(sentence_lengths) / len(sentence_lengths)
    if mean <= 0.0:
        return 0.0
    variance = sum((length - mean) ** 2 for length in sentence_lengths) / len(sentence_lengths)
    return math.sqrt(variance) / mean


def _compute_zipf_metrics(tokens: List[str]) -> tuple[float, float]:
    """Return (shannon_entropy_bits, abs_zipf_log_rank_log_freq_slope)."""
    n = len(tokens)
    if n == 0:
        return 0.0, 0.0

    counts = Counter(tokens)
    entropy = -sum((freq / n) * math.log2(freq / n) for freq in counts.values())

    freqs = sorted(counts.values(), reverse=True)
    # Use the entry rank (first rank) of each distinct frequency tier so discrete
    # hapax-legomena tie plateaus (freq == 1) do not flatten the Zipf exponent.
    freq_first_rank: Dict[int, int] = {}
    for rank, freq in enumerate(freqs, start=1):
        freq_first_rank.setdefault(freq, rank)

    xs: List[float] = []
    ys: List[float] = []
    for freq in sorted(freq_first_rank.keys(), reverse=True):
        xs.append(math.log(freq_first_rank[freq]))
        ys.append(math.log(freq))

    if len(xs) < 2:
        return entropy, 0.0

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom <= 0.0:
        return entropy, 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    return entropy, abs(slope)


class AntiAIQualityGate:
    """Burstiness + Zipf Entropy SEO quality gate driven by ``phase3/config.yaml``."""

    def __init__(self, cfg: Any = None) -> None:
        self.a5_cfg, _ = resolve_a5_config(cfg)

    def evaluate(self, content: Any) -> Dict[str, Any]:
        """Evaluate ``content`` (HTML or plain text) and return pass/fail telemetry."""
        if not isinstance(content, str) or not content.strip():
            return self._fail_result(0.0, 0.0, 0.0, 0, "empty_or_non_string_content")

        cleaned = _strip_html(content)
        if not cleaned:
            return self._fail_result(0.0, 0.0, 0.0, 0, "empty_after_html_strip")

        sentence_lengths: List[int] = []
        tokens: List[str] = []
        for chunk in _SENTENCE_SPLIT_RE.split(cleaned):
            sent_tokens = _WORD_TOKEN_RE.findall(chunk)
            if sent_tokens:
                sentence_lengths.append(len(sent_tokens))
                tokens.extend(t.lower() for t in sent_tokens)

        word_count = len(tokens)
        sentence_count = len(sentence_lengths)
        if word_count == 0 or sentence_count == 0:
            return self._fail_result(0.0, 0.0, 0.0, 0, "no_lexical_tokens")

        burstiness = _compute_burstiness(sentence_lengths)
        zipf_entropy, zipf_slope = _compute_zipf_metrics(tokens)

        reasons: List[str] = []
        if word_count < self.a5_cfg.min_word_count:
            reasons.append(f"word_count_below_min({word_count}<{self.a5_cfg.min_word_count})")
        if sentence_count < self.a5_cfg.min_sentence_count:
            reasons.append(f"sentence_count_below_min({sentence_count}<{self.a5_cfg.min_sentence_count})")
        if burstiness < self.a5_cfg.burstiness_min:
            reasons.append(f"burstiness_below_min({burstiness:.3f}<{self.a5_cfg.burstiness_min:.3f})")
        elif burstiness > self.a5_cfg.burstiness_max:
            reasons.append(f"burstiness_above_max({burstiness:.3f}>{self.a5_cfg.burstiness_max:.3f})")
        if zipf_entropy < self.a5_cfg.zipf_entropy_min:
            reasons.append(f"zipf_entropy_below_min({zipf_entropy:.3f}<{self.a5_cfg.zipf_entropy_min:.3f})")
        elif zipf_entropy > self.a5_cfg.zipf_entropy_max:
            reasons.append(f"zipf_entropy_above_max({zipf_entropy:.3f}>{self.a5_cfg.zipf_entropy_max:.3f})")
        if zipf_slope < self.a5_cfg.zipf_slope_min:
            reasons.append(f"zipf_slope_below_min({zipf_slope:.3f}<{self.a5_cfg.zipf_slope_min:.3f})")
        elif zipf_slope > self.a5_cfg.zipf_slope_max:
            reasons.append(f"zipf_slope_above_max({zipf_slope:.3f}>{self.a5_cfg.zipf_slope_max:.3f})")

        passed = len(reasons) == 0
        reason = "ok" if passed else "; ".join(reasons)
        result = {
            "pass": passed,
            "burstiness": round(burstiness, 6),
            "zipf": round(zipf_entropy, 6),
            "zipf_slope": round(zipf_slope, 6),
            "word_count": word_count,
            "reason": reason,
        }
        log_event(
            logger,
            logging.INFO if passed else logging.WARNING,
            "a5_quality_gate_evaluated",
            **result,
            sentence_count=sentence_count,
        )
        return result

    @staticmethod
    def _fail_result(
        burstiness: float,
        zipf: float,
        zipf_slope: float,
        word_count: int,
        reason: str,
    ) -> Dict[str, Any]:
        res = {
            "pass": False,
            "burstiness": round(burstiness, 6),
            "zipf": round(zipf, 6),
            "zipf_slope": round(zipf_slope, 6),
            "word_count": word_count,
            "reason": reason,
        }
        log_event(logger, logging.WARNING, "a5_quality_gate_rejected", **res)
        return res


def gate(content: str, cfg: Any = None) -> Dict[str, Any]:
    """Module-level convenience wrapper for ``AntiAIQualityGate(cfg).evaluate(content)``."""
    try:
        return AntiAIQualityGate(cfg).evaluate(content)
    except Exception as exc:
        log_event(logger, logging.ERROR, "a5_quality_gate_exception", error=str(exc))
        return {
            "pass": False,
            "burstiness": 0.0,
            "zipf": 0.0,
            "zipf_slope": 0.0,
            "word_count": 0,
            "reason": f"gate_error:{exc}",
        }
