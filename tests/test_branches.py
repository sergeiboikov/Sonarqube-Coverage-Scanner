import pytest

from scripts.branches import (
    BranchSelectionError,
    release_version,
    select_release_branch,
)

EXCLUDED = frozenset({"p99.9", "r99.9"})
ANALYZED = "2024-12-01T10:00:00+0000"


def branch(name: str, analyzed: bool = True) -> dict:
    data = {"name": name, "isMain": False, "type": "BRANCH"}
    if analyzed:
        data["analysisDate"] = ANALYZED
    return data


@pytest.mark.parametrize(
    "name, expected",
    [
        ("p12.3", (12, 3)),
        ("r123.4", (123, 4)),
        ("p1.2", None),
        ("p1234.5", None),
        ("p123.45", None),
        ("P123.4", None),
        ("release/r123.4", None),
        ("main", None),
    ],
)
def test_release_version(name, expected):
    assert release_version(name) == expected


def test_selects_numerically_greatest_branch():
    branches = [branch("main"), branch("p99.8"), branch("p100.0"), branch("p100.1"), branch("p12.9")]
    assert select_release_branch(branches, EXCLUDED).name == "p100.1"


def test_skips_excluded_branches():
    branches = [branch("r99.9"), branch("r99.8")]
    assert select_release_branch(branches, EXCLUDED).name == "r99.8"


def test_skips_branches_without_analysis_with_warning():
    branches = [branch("r126.0", analyzed=False), branch("r125.1"), branch("r124.0", analyzed=False)]
    selection = select_release_branch(branches, EXCLUDED)
    assert selection.name == "r125.1"
    assert selection.warning == "newer release branch without analysis skipped: r126.0"


def test_no_release_branch():
    with pytest.raises(BranchSelectionError, match="^no release branch found$"):
        select_release_branch([branch("main"), branch("p99.9")], EXCLUDED)


def test_no_analyzed_release_branch():
    with pytest.raises(BranchSelectionError, match=r"without analysis: r125\.1"):
        select_release_branch([branch("main"), branch("r125.1", analyzed=False)], EXCLUDED)


def test_ambiguous_release_branch():
    with pytest.raises(BranchSelectionError, match=r"ambiguous release branch: p125\.1, r125\.1"):
        select_release_branch([branch("r125.1"), branch("p125.1"), branch("p124.0")], EXCLUDED)
