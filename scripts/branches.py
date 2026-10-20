import re
from dataclasses import dataclass

RELEASE_BRANCH_PATTERN = re.compile(r"^[pr](\d{2,3})\.(\d)$")
DEFAULT_EXCLUDED_BRANCHES = ("p99.9", "r99.9")


class BranchSelectionError(RuntimeError):
    pass


@dataclass
class BranchSelection:
    name: str
    warning: str | None = None


def release_version(name: str) -> tuple[int, int] | None:
    match = RELEASE_BRANCH_PATTERN.fullmatch(name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def select_release_branch(branches: list[dict], excluded: frozenset[str]) -> BranchSelection:
    candidates: list[tuple[tuple[int, int], str, bool]] = []
    for branch in branches:
        name = str(branch.get("name") or "")
        if name in excluded:
            continue
        version = release_version(name)
        if version is None:
            continue
        candidates.append((version, name, bool(branch.get("analysisDate"))))

    analyzed = [(version, name) for version, name, has_analysis in candidates if has_analysis]
    if not analyzed:
        not_analyzed = sorted(name for _, name, _ in candidates)
        if not_analyzed:
            raise BranchSelectionError(
                f"no release branch found (without analysis: {', '.join(not_analyzed)})"
            )
        raise BranchSelectionError("no release branch found")

    top_version = max(version for version, _ in analyzed)
    top = sorted(name for version, name in analyzed if version == top_version)
    if len(top) > 1:
        raise BranchSelectionError(f"ambiguous release branch: {', '.join(top)}")

    skipped = sorted(
        name
        for version, name, has_analysis in candidates
        if not has_analysis and version > top_version
    )
    warning = None
    if skipped:
        warning = f"newer release branch without analysis skipped: {', '.join(skipped)}"
    return BranchSelection(name=top[0], warning=warning)
