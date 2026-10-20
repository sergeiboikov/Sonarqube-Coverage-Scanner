import time

import httpx

from .config import Config

RETRY_ATTEMPTS = 3
RETRY_DELAYS_SEC = (1, 2)
RETRY_STATUS_CODES = {502, 503, 504}
SUPPORTED_VERSION_PREFIX = "24.12."

OVERALL_METRICS = (
    "coverage",
    "line_coverage",
    "branch_coverage",
    "lines_to_cover",
    "uncovered_lines",
)
NEW_CODE_METRICS = tuple(f"new_{metric}" for metric in OVERALL_METRICS)


class SonarQubeError(RuntimeError):
    pass


def _error_message(response: httpx.Response) -> str:
    details = ""
    try:
        payload = response.json()
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            details = "; ".join(str(error.get("msg") or "") for error in errors if error)
    except ValueError:
        details = response.text.strip()[:200]
    message = f"HTTP {response.status_code} for {response.request.url.path}"
    return f"{message}: {details}" if details else message


class SonarQubeClient:
    def __init__(self, config: Config, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=config.sonar_url,
            headers={
                "Authorization": f"Bearer {config.sonar_token}",
                "Accept": "application/json",
            },
            timeout=config.http_timeout_sec,
            verify=config.verify_ssl,
            transport=transport,
        )

    def __enter__(self) -> "SonarQubeClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt == RETRY_ATTEMPTS:
                    reason = str(exc) or type(exc).__name__
                    raise SonarQubeError(f"request to {path} failed: {reason}") from exc
                time.sleep(RETRY_DELAYS_SEC[attempt - 1])
                continue

            if response.status_code in RETRY_STATUS_CODES and attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAYS_SEC[attempt - 1])
                continue
            if response.is_error:
                raise SonarQubeError(_error_message(response))
            return response
        raise AssertionError("unreachable")

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict:
        response = self._get(path, params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SonarQubeError(f"invalid JSON from {path}") from exc
        if not isinstance(payload, dict):
            raise SonarQubeError(f"unexpected response from {path}")
        return payload

    def server_version(self) -> str:
        return self._get("/api/server/version").text.strip()

    def validate_authentication(self) -> None:
        payload = self._get_json("/api/authentication/validate")
        if payload.get("valid") is not True:
            raise SonarQubeError("SONAR_TOKEN is invalid or expired")

    def list_branches(self, project_key: str) -> list[dict]:
        payload = self._get_json("/api/project_branches/list", {"project": project_key})
        return [branch for branch in payload.get("branches") or [] if isinstance(branch, dict)]

    def component_measures(self, project_key: str, branch: str | None) -> dict:
        params = {
            "component": project_key,
            "metricKeys": ",".join(OVERALL_METRICS + NEW_CODE_METRICS),
            "additionalFields": "period",
        }
        if branch:
            params["branch"] = branch
        return self._get_json("/api/measures/component", params)
