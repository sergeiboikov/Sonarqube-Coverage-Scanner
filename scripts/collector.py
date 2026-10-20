from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlencode

from .branches import select_release_branch
from .config import Config
from .projects import Project
from .report import BRANCH_SOURCE_AUTO, BRANCH_SOURCE_CONFIG, CoverageMetrics, ReportRow
from .sonarqube import NEW_CODE_METRICS, OVERALL_METRICS, SonarQubeClient

SONAR_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
REPORT_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
COMMENT_NO_COVERAGE = "no coverage data"
COMMENT_NO_NEW_LINES = "no new lines to cover"


class CollectError(RuntimeError):
    pass


def build_dashboard_url(sonar_url: str, project_key: str, branch: str | None) -> str:
    params = {"id": project_key}
    if branch:
        params["branch"] = branch
    return f"{sonar_url}/dashboard?{urlencode(params)}"


def format_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        moment = datetime.strptime(value, SONAR_DATETIME_FORMAT)
    except ValueError:
        return value
    return moment.astimezone().strftime(REPORT_DATETIME_FORMAT)


def format_period(period: dict | None) -> str:
    if not period:
        return ""
    mode = str(period.get("mode") or "")
    parameter = str(period.get("parameter") or "")
    return f"{mode}={parameter}" if mode and parameter else mode


def _measure_value(measure: dict) -> str | None:
    if measure.get("value") is not None:
        return str(measure["value"])
    period = measure.get("period") or next(iter(measure.get("periods") or []), None) or {}
    value = period.get("value")
    return None if value is None else str(value)


def _percent(value: str | None) -> str:
    if value is None:
        return ""
    quantized = Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{quantized:.1f}".replace(".", ",")


def _count(value: str | None) -> str:
    return "" if value is None else str(int(Decimal(value)))


def _coverage_metrics(measures: dict[str, str], metric_keys: tuple[str, ...]) -> CoverageMetrics | None:
    coverage, line_coverage, branch_coverage, lines_to_cover, uncovered_lines = (
        measures.get(key) for key in metric_keys
    )
    if coverage is None:
        return None
    return CoverageMetrics(
        coverage=_percent(coverage),
        line_coverage=_percent(line_coverage),
        branch_coverage=_percent(branch_coverage),
        lines_to_cover=_count(lines_to_cover),
        uncovered_lines=_count(uncovered_lines),
    )


def apply_measures(row: ReportRow, payload: dict) -> None:
    component = payload.get("component") or {}
    measures: dict[str, str] = {}
    for measure in component.get("measures") or []:
        value = _measure_value(measure)
        if measure.get("metric") and value is not None:
            measures[measure["metric"]] = value

    period = payload.get("period") or next(iter(payload.get("periods") or []), None)
    row.new_code_definition = format_period(period)
    row.new_code_start = format_datetime((period or {}).get("date"))

    row.overall = _coverage_metrics(measures, OVERALL_METRICS)
    row.new_code = _coverage_metrics(measures, NEW_CODE_METRICS)
    if row.overall is None:
        row.comment = COMMENT_NO_COVERAGE
    elif row.new_code is None:
        row.comment = COMMENT_NO_NEW_LINES


def _resolve_branch(project: Project, branches: list[dict], config: Config, log) -> dict:
    if project.branch:
        for branch in branches:
            if branch.get("name") == project.branch:
                return branch
        raise CollectError(f"branch {project.branch!r} not found in SonarQube")

    selection = select_release_branch(branches, config.excluded_branches)
    if selection.warning:
        log(f"[{project.key}] warning: {selection.warning}")
    log(f"[{project.key}] branch auto-detected: {selection.name}")
    return next(branch for branch in branches if branch.get("name") == selection.name)


def collect_project(project: Project, client: SonarQubeClient, config: Config, log) -> ReportRow:
    row = ReportRow(
        key=project.key,
        url=build_dashboard_url(config.sonar_url, project.key, project.branch),
        team=project.team,
        branch=project.branch or "",
        branch_source=BRANCH_SOURCE_CONFIG if project.branch else BRANCH_SOURCE_AUTO,
    )
    try:
        branch = _resolve_branch(project, client.list_branches(project.key), config, log)
        row.branch = str(branch["name"])
        branch_param = None if branch.get("isMain") else row.branch
        row.url = build_dashboard_url(config.sonar_url, project.key, branch_param)

        if not branch.get("analysisDate"):
            raise CollectError("no analysis")
        row.analysis_date = format_datetime(branch["analysisDate"])

        apply_measures(row, client.component_measures(project.key, branch_param))
        overall = row.overall.coverage if row.overall else "-"
        new_code = row.new_code.coverage if row.new_code else "-"
        log(f"[{project.key}] done ({row.branch}): overall={overall} new_code={new_code}")
    except Exception as exc:
        row.error = str(exc) or type(exc).__name__
        log(f"[{project.key}] ERROR: {row.error}")
    return row


def collect_all(projects: list[Project], client: SonarQubeClient, config: Config, log) -> list[ReportRow]:
    workers = max(1, min(config.workers, len(projects)))
    rows: list[ReportRow] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(collect_project, project, client, config, log) for project in projects]
        for future in as_completed(futures):
            rows.append(future.result())
    return rows
