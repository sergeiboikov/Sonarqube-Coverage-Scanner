import httpx

from scripts.collector import collect_all, collect_project, format_period
from scripts.projects import Project
from scripts.report import BRANCH_SOURCE_AUTO, BRANCH_SOURCE_CONFIG, CoverageMetrics

ANALYZED = "2024-12-01T10:00:00+0000"


def measures_payload(measures: dict[str, str], new_measures: dict[str, str]) -> dict:
    items = [{"metric": key, "value": value} for key, value in measures.items()]
    items += [
        {"metric": key, "period": {"index": 1, "value": value, "bestValue": False}}
        for key, value in new_measures.items()
    ]
    return {
        "component": {"key": "app-one", "measures": items},
        "period": {"mode": "NUMBER_OF_DAYS", "date": "2024-11-01T00:00:00+0000", "parameter": "30"},
    }


FULL_MEASURES = measures_payload(
    {
        "coverage": "85.34",
        "line_coverage": "87",
        "branch_coverage": "70.06",
        "lines_to_cover": "1200",
        "uncovered_lines": "156",
    },
    {
        "new_coverage": "72.0",
        "new_line_coverage": "75.55",
        "new_branch_coverage": "60.0",
        "new_lines_to_cover": "40",
        "new_uncovered_lines": "10",
    },
)

BRANCHES = {
    "branches": [
        {"name": "main", "isMain": True, "analysisDate": ANALYZED},
        {"name": "r125.1", "isMain": False, "analysisDate": ANALYZED},
        {"name": "r124.0", "isMain": False, "analysisDate": ANALYZED},
        {"name": "r126.0", "isMain": False},
    ]
}


def collect(config, fake_sonar, project, logs=None):
    with fake_sonar.client(config) as client:
        return collect_project(project, client, config, (logs if logs is not None else []).append)


def test_explicit_branch(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    fake_sonar.routes["/api/measures/component"] = FULL_MEASURES
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch="r124.0"))

    assert row.error is None
    assert row.branch == "r124.0"
    assert row.branch_source == BRANCH_SOURCE_CONFIG
    assert row.url == "https://sonar.example.com/dashboard?id=app-one&branch=r124.0"
    assert row.analysis_date
    assert row.new_code_definition == "NUMBER_OF_DAYS=30"
    assert row.new_code_start
    assert row.overall == CoverageMetrics("85.3", "87.0", "70.1", "1200", "156")
    assert row.new_code == CoverageMetrics("72.0", "75.6", "60.0", "40", "10")
    assert row.comment == ""
    assert fake_sonar.requests[-1].url.params["branch"] == "r124.0"


def test_auto_detected_branch(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    fake_sonar.routes["/api/measures/component"] = FULL_MEASURES
    logs: list[str] = []
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch=None), logs)

    assert row.error is None
    assert row.branch == "r125.1"
    assert row.branch_source == BRANCH_SOURCE_AUTO
    assert "[app-one] warning: newer release branch without analysis skipped: r126.0" in logs
    assert "[app-one] branch auto-detected: r125.1" in logs


def test_main_branch_is_requested_without_branch_param(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    fake_sonar.routes["/api/measures/component"] = FULL_MEASURES
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch="main"))

    assert row.error is None
    assert row.url == "https://sonar.example.com/dashboard?id=app-one"
    assert "branch" not in fake_sonar.requests[-1].url.params


def test_no_release_branch(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = {
        "branches": [{"name": "main", "isMain": True, "analysisDate": ANALYZED}]
    }
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch=None))

    assert row.error == "no release branch found"
    assert row.branch == ""
    assert row.branch_source == BRANCH_SOURCE_AUTO


def test_branch_not_found(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch="r200.0"))
    assert row.error == "branch 'r200.0' not found in SonarQube"
    assert row.branch == "r200.0"


def test_branch_without_analysis(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch="r126.0"))
    assert row.error == "no analysis"


def test_project_not_found(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = lambda request: httpx.Response(
        404, json={"errors": [{"msg": "Project 'app-x' not found"}]}
    )
    row = collect(config, fake_sonar, Project(key="app-x", team="A", branch="r1.0"))
    assert "Project 'app-x' not found" in row.error


def test_no_coverage_data(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    fake_sonar.routes["/api/measures/component"] = measures_payload({}, {})
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch="r125.1"))

    assert row.error is None
    assert row.overall is None
    assert row.new_code is None
    assert row.comment == "no coverage data"


def test_no_new_lines_to_cover(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    fake_sonar.routes["/api/measures/component"] = measures_payload(
        {"coverage": "80.0", "lines_to_cover": "100", "uncovered_lines": "20"},
        {"new_lines_to_cover": "0"},
    )
    row = collect(config, fake_sonar, Project(key="app-one", team="A", branch="r125.1"))

    assert row.overall == CoverageMetrics("80.0", "", "", "100", "20")
    assert row.new_code is None
    assert row.comment == "no new lines to cover"


def test_collect_all(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = BRANCHES
    fake_sonar.routes["/api/measures/component"] = FULL_MEASURES
    projects = [
        Project(key="app-one", team="A", branch="r125.1"),
        Project(key="app-one", team="A", branch="r200.0"),
        Project(key="app-one", team="A", branch=None),
    ]
    with fake_sonar.client(config) as client:
        rows = collect_all(projects, client, config, lambda message: None)
    assert sorted((row.branch, row.error is None) for row in rows) == [
        ("r125.1", True),
        ("r125.1", True),
        ("r200.0", False),
    ]


def test_format_period():
    assert format_period(None) == ""
    assert format_period({"mode": "PREVIOUS_VERSION"}) == "PREVIOUS_VERSION"
    assert format_period({"mode": "REFERENCE_BRANCH", "parameter": "main"}) == "REFERENCE_BRANCH=main"
