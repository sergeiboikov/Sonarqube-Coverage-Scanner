import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .branches import DEFAULT_EXCLUDED_BRANCHES, release_version

DEFAULT_WORKERS = 4
DEFAULT_PROJECTS_FILE = "projects.json"
DEFAULT_OUTPUT_FOLDER = "reports"
DEFAULT_HTTP_TIMEOUT_SEC = 60
DEFAULT_VERIFY_SSL = "false"
BOOLEAN_VALUES = {"true": True, "false": False}


class ConfigError(RuntimeError):
    pass


@dataclass
class Config:
    sonar_url: str
    sonar_token: str
    verify_ssl: bool
    projects_file: Path
    output_folder: Path
    workers: int
    http_timeout_sec: int
    excluded_branches: frozenset[str]


def _optional(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _resolve_path(value: str | None, base_dir: Path, default: str) -> Path:
    raw = _optional(value) or default
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def _parse_positive_int(name: str, value: str | None, default: int) -> int:
    raw = _optional(value) or str(default)
    try:
        number = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got: {raw!r}") from exc
    if number < 1:
        raise ConfigError(f"{name} must be >= 1")
    return number


def _parse_bool(name: str, value: str | None, default: str) -> bool:
    raw = _optional(value) or default
    try:
        return BOOLEAN_VALUES[raw.lower()]
    except KeyError as exc:
        raise ConfigError(f"{name} must be 'true' or 'false', got: {raw!r}") from exc


def _parse_sonar_url(value: str | None) -> str:
    url = _optional(value)
    if not url:
        raise ConfigError("SONAR_URL is not set (see .env)")
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"SONAR_URL must start with http:// or https://, got: {url!r}")
    return url.rstrip("/")


def _parse_excluded_branches(value: str | None) -> frozenset[str]:
    names = [name.strip() for name in (value or "").split(",") if name.strip()]
    if not names:
        return frozenset(DEFAULT_EXCLUDED_BRANCHES)
    invalid = [name for name in names if release_version(name) is None]
    if invalid:
        raise ConfigError(
            "EXCLUDED_BRANCHES must contain branch names like p123.4 or r12.3, "
            f"got: {', '.join(repr(name) for name in invalid)}"
        )
    return frozenset(names)


def load_config(env_file: Path) -> Config:
    if not env_file.is_file():
        raise ConfigError(f"Environment file not found: {env_file}")
    load_dotenv(env_file)
    base_dir = env_file.resolve().parent

    sonar_token = _optional(os.environ.get("SONAR_TOKEN"))
    if not sonar_token:
        raise ConfigError("SONAR_TOKEN is not set (see .env)")

    return Config(
        sonar_url=_parse_sonar_url(os.environ.get("SONAR_URL")),
        sonar_token=sonar_token,
        verify_ssl=_parse_bool(
            "SONAR_VERIFY_SSL", os.environ.get("SONAR_VERIFY_SSL"), DEFAULT_VERIFY_SSL
        ),
        projects_file=_resolve_path(
            os.environ.get("PROJECTS_FILE"), base_dir, DEFAULT_PROJECTS_FILE
        ),
        output_folder=_resolve_path(os.environ.get("OUTPUT_FOLDER"), base_dir, DEFAULT_OUTPUT_FOLDER),
        workers=_parse_positive_int("WORKERS", os.environ.get("WORKERS"), DEFAULT_WORKERS),
        http_timeout_sec=_parse_positive_int(
            "HTTP_TIMEOUT_SEC", os.environ.get("HTTP_TIMEOUT_SEC"), DEFAULT_HTTP_TIMEOUT_SEC
        ),
        excluded_branches=_parse_excluded_branches(os.environ.get("EXCLUDED_BRANCHES")),
    )
