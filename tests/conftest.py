import os
from pathlib import Path

import httpx
import pytest

from scripts.branches import DEFAULT_EXCLUDED_BRANCHES
from scripts.config import Config
from scripts.sonarqube import SonarQubeClient

ENV_KEYS = (
    "SONAR_URL",
    "SONAR_TOKEN",
    "SONAR_VERIFY_SSL",
    "PROJECTS_FILE",
    "OUTPUT_FOLDER",
    "WORKERS",
    "HTTP_TIMEOUT_SEC",
    "EXCLUDED_BRANCHES",
)


@pytest.fixture(autouse=True)
def isolated_environ(monkeypatch):
    environ = os.environ.copy()
    for key in ENV_KEYS:
        environ.pop(key, None)
    monkeypatch.setattr(os, "environ", environ)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("scripts.sonarqube.time.sleep", lambda seconds: None)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        sonar_url="https://sonar.example.com",
        sonar_token="squ_test",
        verify_ssl=False,
        projects_file=tmp_path / "projects.json",
        output_folder=tmp_path / "reports",
        workers=2,
        http_timeout_sec=5,
        excluded_branches=frozenset(DEFAULT_EXCLUDED_BRANCHES),
    )


class FakeSonar:
    """Routes requests by path to canned JSON responses and records every request."""

    def __init__(self):
        self.routes: dict[str, object] = {}
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"errors": [{"msg": "not found"}]})
        if callable(route):
            return route(request)
        return httpx.Response(200, json=route)

    def client(self, config: Config) -> SonarQubeClient:
        return SonarQubeClient(config, transport=httpx.MockTransport(self.handler))


@pytest.fixture
def fake_sonar() -> FakeSonar:
    return FakeSonar()
