import json

import httpx
import pytest

import main
from scripts.sonarqube import SonarQubeClient

ANALYZED = "2024-12-01T10:00:00+0000"


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".env").write_text(
        "SONAR_URL=https://sonar.example.com\nSONAR_TOKEN=squ_test\n", encoding="utf-8"
    )
    (tmp_path / "projects.json").write_text(
        json.dumps([{"projectKey": "app-one", "Team": "A", "Branch": ""}]), encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def use_fake_sonar(monkeypatch, fake_sonar):
    fake_sonar.routes.update(
        {
            "/api/server/version": lambda request: httpx.Response(200, text="24.12.0.100206"),
            "/api/authentication/validate": {"valid": True},
            "/api/project_branches/list": {
                "branches": [{"name": "r125.1", "isMain": False, "analysisDate": ANALYZED}]
            },
            "/api/measures/component": {
                "component": {"measures": [{"metric": "coverage", "value": "80.0"}]},
                "period": {"mode": "PREVIOUS_VERSION"},
            },
        }
    )
    monkeypatch.setattr(
        main,
        "SonarQubeClient",
        lambda config: SonarQubeClient(config, transport=httpx.MockTransport(fake_sonar.handler)),
    )
    return fake_sonar


def test_writes_report(workspace, use_fake_sonar, capsys):
    assert main.main(["--env-file", str(workspace / ".env")]) == 0

    reports = list((workspace / "reports").glob("coverage_report_*_1.csv"))
    assert len(reports) == 1
    content = reports[0].read_text(encoding="utf-8-sig")
    assert "app-one;https://sonar.example.com/dashboard?id=app-one&branch=r125.1;A;r125.1;auto" in content

    stderr = capsys.readouterr().err
    assert "warning: TLS verification disabled (SONAR_VERIFY_SSL=false)" in stderr
    assert "SonarQube 24.12.0.100206" in stderr
    assert "tested with" not in stderr
    assert "(rows: 1, errors: 0)" in stderr


def test_warns_on_other_server_version(workspace, use_fake_sonar, capsys):
    use_fake_sonar.routes["/api/server/version"] = lambda request: httpx.Response(200, text="25.1.0.1")
    assert main.main(["--env-file", str(workspace / ".env")]) == 0
    assert "warning: tested with SonarQube 24.12.x, server is 25.1.0.1" in capsys.readouterr().err


def test_invalid_token_exits_with_error(workspace, use_fake_sonar, capsys):
    use_fake_sonar.routes["/api/authentication/validate"] = {"valid": False}
    assert main.main(["--env-file", str(workspace / ".env")]) == 1
    assert "error: SONAR_TOKEN is invalid or expired" in capsys.readouterr().err
    assert not (workspace / "reports").exists()


def test_no_projects_exits_with_error(workspace, use_fake_sonar, capsys):
    (workspace / "projects.json").write_text("[]", encoding="utf-8")
    assert main.main(["--env-file", str(workspace / ".env")]) == 1
    assert "no projects to report" in capsys.readouterr().err


def test_config_error_exits_with_error(tmp_path, capsys):
    assert main.main(["--env-file", str(tmp_path / ".env")]) == 1
    assert "error: Environment file not found" in capsys.readouterr().err
