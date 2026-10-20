import json

import pytest

from scripts.projects import Project, ProjectsError, load_projects


def write_projects(tmp_path, data) -> object:
    path = tmp_path / "projects.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_projects(tmp_path):
    path = write_projects(
        tmp_path,
        [
            {"projectKey": "app-one", "Team": "A", "Branch": "r125.1"},
            {"projectKey": "app-one", "Team": "A", "Branch": "r124.3"},
            {"projectKey": " app-two ", "Team": "", "Branch": ""},
            {"projectKey": "app-one", "Team": "A", "Branch": "r125.1"},
            {"projectKey": "", "Team": "B"},
            "garbage",
        ],
    )
    projects, warnings = load_projects(path)
    assert projects == [
        Project(key="app-one", team="A", branch="r125.1"),
        Project(key="app-one", team="A", branch="r124.3"),
        Project(key="app-two", team="", branch=None),
    ]
    assert warnings == [
        "#3: empty 'Team' (app-two)",
        "#3: empty 'Branch' (app-two), the latest release branch will be detected",
        "#4: duplicate 'app-one@r125.1', skipped",
        "#5: empty 'projectKey', skipped",
        "#6: item is not an object, skipped",
    ]


def test_missing_file(tmp_path):
    with pytest.raises(ProjectsError, match="not found"):
        load_projects(tmp_path / "projects.json")


def test_invalid_json(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text("[", encoding="utf-8")
    with pytest.raises(ProjectsError, match="Invalid JSON"):
        load_projects(path)


def test_not_an_array(tmp_path):
    with pytest.raises(ProjectsError, match="expected a JSON array"):
        load_projects(write_projects(tmp_path, {"projectKey": "app"}))
