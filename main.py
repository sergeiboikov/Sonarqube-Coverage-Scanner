import argparse
import sys
from datetime import date
from pathlib import Path

from scripts.collector import collect_all
from scripts.config import ConfigError, load_config
from scripts.projects import ProjectsError, load_projects
from scripts.report import resolve_report_path, write_report
from scripts.sonarqube import SUPPORTED_VERSION_PREFIX, SonarQubeClient, SonarQubeError


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _configure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sonarqube-coverage-scanner",
        description="Code coverage report (New Code and Overall) from SonarQube (CSV).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the environment file (default: .env in the current directory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_streams()
    report_date = date.today().strftime("%Y%m%d")
    args = build_parser().parse_args(argv)
    try:
        config = load_config(Path(args.env_file))
        if not config.verify_ssl:
            log("warning: TLS verification disabled (SONAR_VERIFY_SSL=false)")

        projects, warnings = load_projects(config.projects_file)
        for warning in warnings:
            log(f"warning: {warning}")

        if not projects:
            log("no projects to report")
            return 1

        log(f"projects: {len(projects)}; workers: {config.workers}")
        with SonarQubeClient(config) as client:
            version = client.server_version()
            log(f"server: {config.sonar_url} (SonarQube {version})")
            if not version.startswith(SUPPORTED_VERSION_PREFIX):
                log(f"warning: tested with SonarQube {SUPPORTED_VERSION_PREFIX}x, server is {version}")
            client.validate_authentication()
            rows = collect_all(projects, client, config, log)

        report_path = resolve_report_path(config.output_folder, report_date)
        write_report(rows, report_path)

        failed = sum(1 for row in rows if row.error)
        log(f"report: {report_path} (rows: {len(rows)}, errors: {failed})")
        return 0
    except (ConfigError, ProjectsError, SonarQubeError) as exc:
        log(f"error: {exc}")
        return 1
    except OSError as exc:
        log(f"runtime error: {exc}")
        return 1
    except KeyboardInterrupt:
        log("interrupted by user")
        return 130
    except Exception as exc:
        log(f"unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
