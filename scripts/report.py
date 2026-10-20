import csv
import re
from dataclasses import dataclass
from pathlib import Path

METRIC_TITLES = [
    "Покрытие, %",
    "Покрытие строк, %",
    "Покрытие условий, %",
    "Строк к покрытию",
    "Непокрытых строк",
]

HEADER = [
    "Ключ проекта",
    "URL",
    "Team",
    "Ветка",
    "Источник ветки",
    "Дата последнего анализа",
    "New Code: определение",
    "New Code: начало периода",
    *(f"Overall: {title}" for title in METRIC_TITLES),
    *(f"New Code: {title}" for title in METRIC_TITLES),
    "Статус проверки",
    "Комментарий",
]

STATUS_SUCCESS = "Success"
STATUS_FAILED = "Failed"
BRANCH_SOURCE_CONFIG = "config"
BRANCH_SOURCE_AUTO = "auto"


@dataclass
class CoverageMetrics:
    coverage: str
    line_coverage: str
    branch_coverage: str
    lines_to_cover: str
    uncovered_lines: str

    def values(self) -> list[str]:
        return [
            self.coverage,
            self.line_coverage,
            self.branch_coverage,
            self.lines_to_cover,
            self.uncovered_lines,
        ]


EMPTY_METRICS = [""] * len(METRIC_TITLES)


@dataclass
class ReportRow:
    key: str
    url: str
    team: str
    branch: str
    branch_source: str
    analysis_date: str = ""
    new_code_definition: str = ""
    new_code_start: str = ""
    overall: CoverageMetrics | None = None
    new_code: CoverageMetrics | None = None
    comment: str = ""
    error: str | None = None


FORMULA_PREFIXES = ("=", "+", "-", "@")


def _sanitize(value: object) -> str:
    text = "" if value is None else str(value)
    if text[:1] in FORMULA_PREFIXES:
        return "'" + text
    return text


def _sanitize_error(value: object) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return _sanitize(text)


def _metric_values(metrics: CoverageMetrics | None) -> list[str]:
    return metrics.values() if metrics else EMPTY_METRICS


def _row_values(row: ReportRow) -> list[object]:
    identity = [
        _sanitize(row.key),
        _sanitize(row.url),
        _sanitize(row.team),
        _sanitize(row.branch),
        row.branch_source,
        row.analysis_date,
    ]
    if row.error:
        return [
            *identity,
            "",
            "",
            *EMPTY_METRICS,
            *EMPTY_METRICS,
            STATUS_FAILED,
            _sanitize_error(row.error),
        ]
    return [
        *identity,
        _sanitize(row.new_code_definition),
        row.new_code_start,
        *_metric_values(row.overall),
        *_metric_values(row.new_code),
        STATUS_SUCCESS,
        _sanitize(row.comment),
    ]


REPORT_NAME_PREFIX = "coverage_report_"
REPORT_NAME_SUFFIX = ".csv"


def resolve_report_path(output_folder: Path, report_date: str) -> Path:
    output_folder.mkdir(parents=True, exist_ok=True)
    prefix = f"{REPORT_NAME_PREFIX}{report_date}_"
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(REPORT_NAME_SUFFIX)}$")
    max_number = 0
    for path in output_folder.iterdir():
        match = pattern.fullmatch(path.name)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return output_folder / f"{prefix}{max_number + 1}{REPORT_NAME_SUFFIX}"


def write_report(rows: list[ReportRow], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: (row.key.casefold(), row.branch.casefold()))
    with output_file.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(HEADER)
        for row in ordered:
            writer.writerow(_row_values(row))
