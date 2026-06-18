"""Smoke tests — call real LLM APIs against known MRs.

Run manually only (excluded from default pytest run):
    uv run pytest -m smoke -v
"""

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

from shared.schemas import Severity
from adk.run import _run_adk

# Known MRs with stable expected outputs
_LATINCORE_82 = "https://gitlab.shalltry.com/inputmethod/latincore/-/merge_requests/82"
_LATINCORE_82_REPO = "/Users/chazongxun/Documents/workspaces/trans/latincore"

# Minimum findings expected from latincore/82 (verified baseline)
_EXPECTED_FILES = {"latin-core-web/src/main/java/com/transsion/latincore/service/QuotationSyncService.java"}
_EXPECTED_CATEGORIES = {"resource_leak", "null_deref"}


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_latincore_82_produces_critical_findings():
    """Full pipeline on latincore/82 — must find at least 2 critical findings."""
    report, info = await _run_adk(_LATINCORE_82, _LATINCORE_82_REPO)

    assert report.verdict == "block", f"Expected block, got {report.verdict}"

    critical = [f for f in report.findings if f.severity == Severity.CRITICAL]
    assert len(critical) >= 2, f"Expected ≥2 critical findings, got {len(critical)}: {critical}"

    found_files = {f.file for f in report.findings}
    assert _EXPECTED_FILES & found_files, (
        f"Expected findings in {_EXPECTED_FILES}, got files: {found_files}"
    )

    found_categories = {f.category for f in report.findings}
    missing = _EXPECTED_CATEGORIES - found_categories
    assert not missing, f"Missing expected categories: {missing}, got: {found_categories}"


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_latincore_82_planner_activates_backend():
    """Planner must activate 'backend' domain for a pure Java service change."""
    import json
    from adk.run import _filter_test_files, _run_batch
    from shared.git_client import get_pr_diff_batches

    _, batches = get_pr_diff_batches(_LATINCORE_82)
    filtered = _filter_test_files(batches[0])
    findings = await _run_batch(_LATINCORE_82, _LATINCORE_82_REPO, filtered)

    assert len(findings) > 0, "Expected findings from backend reviewer"
    assert all(f.file.endswith(".java") for f in findings), (
        f"All findings should be in .java files, got: {[f.file for f in findings]}"
    )
