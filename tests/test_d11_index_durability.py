"""
tests/test_d11_index_durability.py — Test stale shingle index rebuilds before duplicate checking (D11)
"""

import io
from pathlib import Path
from unittest.mock import patch

from shingle_guard import (
    clear_shared_index,
    get_shared_index,
    ShingleIndex,
)


def test_guard_rebuilds_stale_index(tmp_path: Path):
    """
    Asserts that if the index file is deleted or stale, register_article triggers
    an automatic rebuild before performing duplicate checking.
    """
    tmp_index = tmp_path / "prose_shingles.json"
    clear_shared_index()

    idx = ShingleIndex(index_path=tmp_index, auto_build_if_empty=False)
    # Pre-populate index with a mock shingle
    idx.index["sample unique prose shingle across ten domains verified guide benchmark"] = {
        "domain": "loanraaj.com",
        "slug": "existing-guide",
        "page_id": "loanraaj.com/existing-guide",
    }
    idx.save()
    assert tmp_index.exists()

    # Now delete index file to simulate a stale/missing index
    tmp_index.unlink()
    assert not tmp_index.exists()

    rebuilt_called = False

    def mock_build_shingle_index(output_path=None, dry_run=False):
        nonlocal rebuilt_called
        rebuilt_called = True
        tmp_index.write_text('{"dummy": {"page_id": "test"}}', encoding="utf-8")
        return 1

    sample_html = """
    <div class="post-content">
        <p>Evaluating commercial auto insurance rates requires auditing statutory underwriting benchmarks and fee schedules across licensed carriers in India.</p>
    </div>
    """

    with patch("scripts.build_shingle_index.build_shingle_index", side_effect=mock_build_shingle_index):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            # Setting auto_build_if_empty=True ensures rebuild happens
            idx.auto_build_if_empty = True
            idx.register_article("loanraaj.com", "new-guide", sample_html, check_duplicates=True)
            output = mock_stdout.getvalue()

    assert rebuilt_called is True, "Rebuild was not triggered on missing/stale index before duplicate checking"
    assert "[guard] index rebuilt" in output
    assert tmp_index.exists()
