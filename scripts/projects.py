import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_KEY = "projectKey"


class ProjectsError(RuntimeError):
    pass


@dataclass
class Project:
    key: str
    team: str
    branch: str | None


def load_projects(file_path: Path) -> tuple[list[Project], list[str]]:
    if not file_path.is_file():
        raise ProjectsError(f"Projects file not found: {file_path}")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectsError(f"Invalid JSON in {file_path}: {exc}") from exc

    if not isinstance(data, list):
        raise ProjectsError(f"{file_path}: expected a JSON array of objects")

    projects: list[Project] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            warnings.append(f"#{index}: item is not an object, skipped")
            continue

        key = str(item.get(PROJECT_KEY) or "").strip()
        if not key:
            warnings.append(f"#{index}: empty {PROJECT_KEY!r}, skipped")
            continue

        branch = str(item.get("Branch") or "").strip() or None
        identity = (key, branch or "")
        if identity in seen:
            label = f"{key}@{branch}" if branch else key
            warnings.append(f"#{index}: duplicate {label!r}, skipped")
            continue

        team = str(item.get("Team") or "").strip()
        if not team:
            warnings.append(f"#{index}: empty 'Team' ({key})")

        if branch is None:
            warnings.append(
                f"#{index}: empty 'Branch' ({key}), the latest release branch will be detected"
            )

        seen.add(identity)
        projects.append(Project(key=key, team=team, branch=branch))

    return projects, warnings
