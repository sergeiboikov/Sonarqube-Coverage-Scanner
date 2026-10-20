import httpx
import pytest

from scripts.sonarqube import SonarQubeError


def test_sends_bearer_token_and_branch(config, fake_sonar):
    fake_sonar.routes["/api/measures/component"] = {"component": {"measures": []}}
    with fake_sonar.client(config) as client:
        client.component_measures("app-one", "r125.1")
    request = fake_sonar.requests[0]
    assert request.headers["Authorization"] == "Bearer squ_test"
    assert request.url.params["component"] == "app-one"
    assert request.url.params["branch"] == "r125.1"
    assert request.url.params["additionalFields"] == "period"
    assert "new_coverage" in request.url.params["metricKeys"].split(",")


def test_omits_branch_param_for_main_branch(config, fake_sonar):
    fake_sonar.routes["/api/measures/component"] = {"component": {"measures": []}}
    with fake_sonar.client(config) as client:
        client.component_measures("app-one", None)
    assert "branch" not in fake_sonar.requests[0].url.params


def test_keeps_base_url_path_prefix(config, fake_sonar):
    config.sonar_url = "https://host.example.com/sonar"
    fake_sonar.routes["/sonar/api/server/version"] = lambda request: httpx.Response(
        200, text="24.12.0.100206"
    )
    with fake_sonar.client(config) as client:
        assert client.server_version() == "24.12.0.100206"


def test_retries_on_gateway_errors(config, fake_sonar):
    responses = iter([httpx.Response(503), httpx.Response(502), httpx.Response(200, json={"branches": []})])
    fake_sonar.routes["/api/project_branches/list"] = lambda request: next(responses)
    with fake_sonar.client(config) as client:
        assert client.list_branches("app-one") == []
    assert len(fake_sonar.requests) == 3


def test_gives_up_after_three_attempts(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = lambda request: httpx.Response(504)
    with fake_sonar.client(config) as client:
        with pytest.raises(SonarQubeError, match="HTTP 504"):
            client.list_branches("app-one")
    assert len(fake_sonar.requests) == 3


def test_retries_on_transport_errors(config, fake_sonar):
    def fail(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    fake_sonar.routes["/api/project_branches/list"] = fail
    with fake_sonar.client(config) as client:
        with pytest.raises(SonarQubeError, match="failed: timed out"):
            client.list_branches("app-one")
    assert len(fake_sonar.requests) == 3


def test_does_not_retry_client_errors(config, fake_sonar):
    fake_sonar.routes["/api/project_branches/list"] = lambda request: httpx.Response(
        404, json={"errors": [{"msg": "Project 'app-x' not found"}]}
    )
    with fake_sonar.client(config) as client:
        with pytest.raises(SonarQubeError, match="HTTP 404 .*: Project 'app-x' not found"):
            client.list_branches("app-x")
    assert len(fake_sonar.requests) == 1


@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, json={"valid": False}), httpx.Response(401)],
)
def test_validate_authentication_fails(config, fake_sonar, response):
    fake_sonar.routes["/api/authentication/validate"] = lambda request: response
    with fake_sonar.client(config) as client:
        with pytest.raises(SonarQubeError):
            client.validate_authentication()
