"""Reading and writing spreadsheets (CSV, XLSX) without touching the original."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
EXCEL_SUFFIXES = (".xlsx", ".xlsm")


@dataclass
class TableInfo:
    """How the source file was written, so the copy can be written the same way."""
    path: Path
    kind: str  # "csv" or "excel"
    sep: str = ","
    encoding: str = "utf-8-sig"
    sheet: str | None = None


def _sniff_sep(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def read_table(path: str | Path, sheet: str | int | None = None) -> tuple[pd.DataFrame, TableInfo]:
    """Read a CSV or Excel file. CSVs are sniffed for separator (, ; tab |)
    and encoding (UTF-8, then Windows-1252/Latin-1). All cells are read as text."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        name = sheet if isinstance(sheet, str) else list(sheets)[sheet or 0]
        df = sheets[name]
        return df, TableInfo(path=path, kind="excel", sheet=name)
    if suffix == ".xls":
        raise ValueError("Old .xls files are not supported; save the file as .xlsx or .csv.")

    raw = path.read_bytes()
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sep = _sniff_sep(text[:20000])
    df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str, keep_default_na=False)
    return df, TableInfo(path=path, kind="csv", sep=sep, encoding=enc)


def free_path(path: Path) -> Path:
    """Return `path`, or `name_2.ext`, `name_3.ext`... if it already exists. Never overwrite."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def output_paths(info: TableInfo, out_dir: str | Path | None = None) -> tuple[Path, Path]:
    """Paths for the result copy and the summary, next to the source by default."""
    folder = Path(out_dir) if out_dir else info.path.parent
    folder.mkdir(parents=True, exist_ok=True)
    stem = info.path.stem
    suffix = ".xlsx" if info.kind == "excel" else ".csv"
    table = free_path(folder / f"{stem}_luar{suffix}")
    summary = free_path(folder / f"{table.stem}_summary.md")
    return table, summary


def write_table(df: pd.DataFrame, path: Path, info: TableInfo) -> Path:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    if info.kind == "excel":
        df.to_excel(path, index=False, sheet_name=info.sheet or "Sheet1")
    else:
        # utf-8-sig so Excel opens accents correctly; keep the source separator
        df.to_csv(path, index=False, sep=info.sep, encoding="utf-8-sig")
    return path
