from __future__ import annotations

import re
from pathlib import Path
from seo_pipeline import valid_description


def test_meta_descriptions_no_ellipsis_or_placeholders():
    base = Path("sites")
    desc_pattern = re.compile(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        re.IGNORECASE,
    )
    invalid_files = []
    for p in base.glob("**/*.html"):
        # Skip small utility pages without meta descriptions if any
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = desc_pattern.search(text)
        if m:
            desc = m.group(1)
            if not valid_description(desc):
                invalid_files.append((str(p), desc))

    assert len(invalid_files) == 0, f"Found {len(invalid_files)} files with invalid meta descriptions: {invalid_files[:5]}"


def test_valid_description_helper():
    assert valid_description("This is a valid meta description that is definitely between sixty and one hundred sixty characters long.")
    assert not valid_description("Too short")
    assert not valid_description("This description contains an ellipsis... which is invalid according to SEO standards.")
    assert not valid_description("This description contains {placeholder} which is invalid.")
    assert not valid_description("This description contains page-link which is invalid.")
    assert not valid_description(None)

