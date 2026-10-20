import csv

from scripts.report import (
    HEADER,
    CoverageMetrics,
    ReportRow,
    resolve_report_path,
    write_report,
)


def read_report(path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle, delimiter=";"))


def test_write_report(tmp_path):
    rows = [
        ReportRow(
            key="app-two",
            url="https://sonar/dashboard?id=app-two",
            team="=B",
            branch="",
            branch_source="auto",
            error="no release\nbranch found",
        ),
        ReportRow(
            key="app-one",
            url="https://sonar/dashboard?id=app-one&branch=r125.1",
            team="A",
            branch="r125.1",
            branch_source="config",
            analysis_date="2024-12-01 13:00:00",
            new_code_definition="NUMBER_OF_DAYS=30",
            new_code_start="2024-11-01 03:00:00",
            overall=CoverageMetrics("85,3", "87,0", "70,1", "1200", "156"),
            comment="no new lines to cover",
        ),
    ]
    path = tmp_path / "report.csv"
    write_report(rows, path)

    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    header, first, second = read_report(path)
    assert header == HEADER
    assert len(HEADER) == 20
    assert first == [
        "app-one",
        "https://sonar/dashboard?id=app-one&branch=r125.1",
        "A",
        "r125.1",
        "config",
        "2024-12-01 13:00:00",
        "NUMBER_OF_DAYS=30",
        "2024-11-01 03:00:00",
        "85,3",
        "87,0",
        "70,1",
        "1200",
        "156",
        "",
        "",
        "",
        "",
        "",
        "Success",
        "no new lines to cover",
    ]
    assert second[:6] == ["app-two", "https://sonar/dashboard?id=app-two", "'=B", "", "auto", ""]
    assert second[6:18] == [""] * 12
    assert second[18:] == ["Failed", "no release branch found"]


def test_rows_sorted_by_key_then_branch(tmp_path):
    rows = [
        ReportRow(key=key, url="", team="", branch=branch, branch_source="config")
        for key, branch in [("b", "r1.0"), ("A", "r20.0"), ("a", "r10.0")]
    ]
    path = tmp_path / "report.csv"
    write_report(rows, path)
    assert [row[:4:3] for row in read_report(path)[1:]] == [["a", "r10.0"], ["A", "r20.0"], ["b", "r1.0"]]


def test_resolve_report_path(tmp_path):
    folder = tmp_path / "reports"
    assert resolve_report_path(folder, "20261020").name == "coverage_report_20261020_1.csv"
    (folder / "coverage_report_20261020_1.csv").touch()
    (folder / "coverage_report_20261020_7.csv").touch()
    (folder / "coverage_report_20261019_9.csv").touch()
    assert resolve_report_path(folder, "20261020").name == "coverage_report_20261020_8.csv"
