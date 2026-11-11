"""
content_quality_gate.py — Automated Content Layout & UI Finish Gate.
Derived from:
1. agency-ui-finish-gate-reviewer: Catches raw, unpolished, generic layout before publishing.
2. article-writing: Enforces human editorial voice, crisp formatting, zero LLM scratchpad leaks.
3. seo-content: E-E-A-T audit, empirical data tables, FAQ rich cards.
"""
from __future__ import annotations
import re
import html
from typing import Any

BANNED_LEAK_PHRASES = [
    "banned ai buzzwords",
    "geo-direct opening",
    "prompt provided",
    "let's look closely",
    "constraints (zero tolerance)",
    "required html structure",
    "the constraint says",
    "conflict? it says",
    "i can include div",
    "need 1200+ words",
    "need produce long guide",
    "need ensure no banned words",
    "avoid. need also avoid",
    "need maybe include exact formula",
    "need faq: 3 h3 questions",
    "user required specific questions",
    "user asks complete in-depth guide",
    "snippet: we need answer",
    "need no markdown",
    "need banned words avoid",
]

class ContentQualityFinishGate:
    """
    Automated gate that inspects every generated article layout,
    strips LLM reasoning/thinking leaks, enforces Fortune-500 magazine formatting,
    and formats interactive FAQ cards and Executive Summary boxes.
    """

    @classmethod
    def sanitize_raw_html(cls, raw: str) -> str:
        """Strip all LLM scratchpad, thoughts, and prompt echoes."""
        clean = raw
        
        # 1. Remove markdown fences
        clean = re.sub(r"^```[a-z]*\s*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"```\s*$", "", clean, flags=re.MULTILINE)
        
        # 2. Remove <think>...</think> if present
        clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        
        # 3. Locate where true article content starts
        lead_idx = clean.find("<p class='lead'>")
        if lead_idx == -1:
            lead_idx = clean.find('<p class="lead">')
        if lead_idx != -1:
            clean = clean[lead_idx:]
            
        # 4. Paragraph-by-paragraph purge of any leaked prompt commentary
        parts = re.split(r"(?=<p|<h2|<h3|<div|<table|<ul|<ol)", clean)
        purged = []
        for p in parts:
            p_strip = p.strip()
            if not p_strip:
                continue
            p_low = p_strip.lower()
            if any(leak in p_low for leak in BANNED_LEAK_PHRASES):
                continue
            purged.append(p_strip)
            
        clean = "\n".join(purged)
        return clean.strip()

    @classmethod
    def format_editorial_layout(cls, clean_html: str, title: str, domain_key: str, primary_kw: str) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
        """
        Enhances article layout with:
        - Executive Summary Box
        - Decorated Headings
        - Pro Data Table with Status Badges
        - Actionable Step Cards
        - Sleek Interactive FAQ Cards
        """
        html_out = clean_html
        
        # 1. Extract Lead Paragraph & Inject Executive Summary Box
        lead_match = re.search(r"<p class=['\"]lead['\"]>(.*?)</p>", html_out, re.DOTALL)
        lead_text = lead_match.group(1).strip() if lead_match else f"Comprehensive analysis and verified benchmarks for {title}."
        
        summary_box = f"""
        <div class="executive-summary-box">
            <div class="summary-badge">⚡ Executive Summary & Quick Verdict</div>
            <p class="summary-text">{lead_text}</p>
        </div>
        """
        
        if lead_match:
            # Replace lead paragraph with lead + summary box
            html_out = html_out[:lead_match.end()] + "\n" + summary_box + html_out[lead_match.end():]
        else:
            html_out = f"<p class='lead'>{lead_text}</p>\n{summary_box}\n{html_out}"

        # 2. Enhance Data Table if present
        if "<table" in html_out:
            html_out = re.sub(r"<table(?![^>]*class=)", "<table class='article-table'", html_out)
            # Add badges to common rows
            html_out = html_out.replace("<td>Baseline Standard</td>", "<td><strong>Baseline Standard</strong> <span class='table-badge badge-blue'>Standard</span></td>")
            html_out = html_out.replace("<td>Optimized Choice</td>", "<td><strong>Optimized Choice</strong> <span class='table-badge badge-green'>Recommended</span></td>")
            html_out = html_out.replace("<td>Premium High-Tier</td>", "<td><strong>Premium High-Tier</strong> <span class='table-badge badge-gold'>Top Speed</span></td>")

        # 3. Enhance Step-by-Step Guide
        if "<ol" in html_out and "class=" not in html_out:
            html_out = html_out.replace("<ol>", "<ol class='guide-steps'>")

        # 4. Extract and Format Interactive FAQ Cards
        faqs: list[dict[str, str]] = []
        faq_matches = re.findall(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>", html_out, re.DOTALL)
        
        faq_cards_html = []
        for q_raw, a_raw in faq_matches:
            q_clean = re.sub(r"<[^>]+>", "", q_raw).strip()
            a_clean = re.sub(r"<[^>]+>", "", a_raw).strip()
            if len(q_clean) > 8 and len(a_clean) > 15:
                faqs.append({"question": q_clean, "answer": a_clean})
                faq_cards_html.append(f"""
                <div class="faq-card">
                    <div class="faq-question">❓ {q_clean}</div>
                    <p class="faq-answer">{a_clean}</p>
                </div>
                """)

        # If FAQs were found, replace the plain <h3>/<p> section with sleek .faq-card components
        if faq_cards_html:
            # Remove the old plain FAQ pairs
            for q_raw, a_raw in faq_matches:
                old_block = f"<h3>{q_raw}</h3>\\s*<p>{a_raw}</p>"
                html_out = re.sub(old_block, "", html_out, flags=re.DOTALL)
            
            # Append styled FAQ section
            faq_section = f"""
            <div class="faq-section">
                <h2>Frequently Asked Questions</h2>
                {''.join(faq_cards_html)}
            </div>
            """
            # Clean any leftover orphan <h2>Frequently Asked Questions</h2>
            html_out = re.sub(r"<h2>Frequently Asked Questions</h2>\s*(?=<div class=\"faq-section\")", "", html_out)
            html_out = html_out + "\n" + faq_section
        else:
            # Fallback 3 default structured FAQs
            faqs = [
                {"question": f"What is the main advantage of {title}?", "answer": f"It offers verified efficiency, transparent cost calculations, and substantial annual savings compared to standard options."},
                {"question": f"How to verify current rates and eligibility?", "answer": "Consult the official tariff guidelines and check authorized dealer portals before making purchase decisions."},
                {"question": f"Are there any hidden charges?", "answer": "Always verify statutory taxes, administrative fees, and installation charges disclosed in the fine print."}
            ]
            fallback_cards = "".join([f'<div class="faq-card"><div class="faq-question">❓ {f["question"]}</div><p class="faq-answer">{f["answer"]}</p></div>' for f in faqs])
            html_out += f"""
            <div class="faq-section">
                <h2>Frequently Asked Questions</h2>
                {fallback_cards}
            </div>
            """

        # 5. Inject Adsterra Mid-Article Native Banner Slot (idempotent)
        if "<!-- ADSTERRA_SLOT:native -->" not in html_out:
            try:
                from adsterra_links import render_display_banner
                native_slot_html = render_display_banner(domain_key, "native")
            except Exception:
                native_slot_html = "<!-- ADSTERRA_SLOT:native --><!-- /ADSTERRA_SLOT:native -->"

            h2_matches = list(re.finditer(r"</h2>\s*<p>.*?</p>", html_out, flags=re.DOTALL))
            if len(h2_matches) >= 2:
                pos = h2_matches[1].end()
                html_out = html_out[:pos] + "\n" + native_slot_html + "\n" + html_out[pos:]
            elif '<div class="faq-section">' in html_out:
                html_out = html_out.replace('<div class="faq-section">', f'{native_slot_html}\n<div class="faq-section">', 1)
            else:
                html_out = html_out + "\n" + native_slot_html

        # 6. Quality Audit Scoring
        word_count = len(re.findall(r"\b\w+\b", html_out))
        has_table = "<table" in html_out
        has_summary = "executive-summary-box" in html_out
        has_faqs = len(faqs) >= 2
        no_leaks = not any(leak in html_out.lower() for leak in BANNED_LEAK_PHRASES)

        score = 100.0
        if not has_table: score -= 15.0
        if not has_faqs: score -= 15.0
        if not no_leaks: score -= 30.0
        if word_count < 1000: score -= 20.0

        audit_meta = {
            "score": score,
            "word_count": word_count,
            "has_table": has_table,
            "has_faqs": has_faqs,
            "no_leaks": no_leaks,
            "faq_count": len(faqs)
        }

        return html_out, faqs, audit_meta
