from pathlib import Path

import pytest

from scripts.config import ConfigError, load_config


def write_env(tmp_path: Path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    return env_file


def test_defaults(tmp_path):
    env_file = write_env(tmp_path, "SONAR_URL=https://sonar.example.com/\nSONAR_TOKEN=squ_1\n")
    config = load_config(env_file)
    assert config.sonar_url == "https://sonar.example.com"
    assert config.verify_ssl is False
    assert config.projects_file == tmp_path.resolve() / "projects.json"
    assert config.output_folder == tmp_path.resolve() / "reports"
    assert config.workers == 4
    assert config.http_timeout_sec == 60
    assert config.excluded_branches == {"p99.9", "r99.9"}


def test_missing_env_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / ".env")


@pytest.mark.parametrize(
    "content, message",
    [
        ("SONAR_TOKEN=squ_1\n", "SONAR_URL is not set"),
        ("SONAR_URL=sonar.example.com\nSONAR_TOKEN=squ_1\n", "must start with http"),
        ("SONAR_URL=https://sonar.example.com\n", "SONAR_TOKEN is not set"),
    ],
)
def test_required_values(tmp_path, content, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write_env(tmp_path, content))


@pytest.mark.parametrize("value, expected", [("true", True), ("TRUE", True), ("False", False)])
def test_verify_ssl(tmp_path, value, expected):
    env_file = write_env(
        tmp_path,
        f"SONAR_URL=https://sonar.example.com\nSONAR_TOKEN=squ_1\nSONAR_VERIFY_SSL={value}\n",
    )
    assert load_config(env_file).verify_ssl is expected


@pytest.mark.parametrize("value", ["1", "yes", "off"])
def test_verify_ssl_rejects_other_values(tmp_path, value):
    env_file = write_env(
        tmp_path,
        f"SONAR_URL=https://sonar.example.com\nSONAR_TOKEN=squ_1\nSONAR_VERIFY_SSL={value}\n",
    )
    with pytest.raises(ConfigError, match="'true' or 'false'"):
        load_config(env_file)


def test_excluded_branches(tmp_path):
    env_file = write_env(
        tmp_path,
        "SONAR_URL=https://sonar.example.com\nSONAR_TOKEN=squ_1\n"
        "EXCLUDED_BRANCHES= p12.3 , r100.1 ,\n",
    )
    assert load_config(env_file).excluded_branches == {"p12.3", "r100.1"}


def test_excluded_branches_empty_value_uses_default(tmp_path):
    env_file = write_env(
        tmp_path, "SONAR_URL=https://sonar.example.com\nSONAR_TOKEN=squ_1\nEXCLUDED_BRANCHES=\n"
    )
    assert load_config(env_file).excluded_branches == {"p99.9", "r99.9"}


def test_excluded_branches_rejects_invalid_names(tmp_path):
    env_file = write_env(
        tmp_path,
        "SONAR_URL=https://sonar.example.com\nSONAR_TOKEN=squ_1\nEXCLUDED_BRANCHES=p99.9,p99_9\n",
    )
    with pytest.raises(ConfigError, match="'p99_9'"):
        load_config(env_file)


def test_invalid_workers(tmp_path):
    env_file = write_env(
        tmp_path, "SONAR_URL=https://sonar.example.com\nSONAR_TOKEN=squ_1\nWORKERS=0\n"
    )
    with pytest.raises(ConfigError, match="WORKERS must be >= 1"):
        load_config(env_file)
