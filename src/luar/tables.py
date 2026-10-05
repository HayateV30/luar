"""Reading and writing spreadsheets (CSV, XLSX) without touching the original."""
from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .i18n import t

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
EXCEL_SUFFIXES = (".xlsx", ".xlsm")
# an .xlsx is a zip: a small file can unpack to gigabytes ("zip bomb") and freeze the machine
MAX_XLSX_UNPACKED = 300 * 1024 * 1024


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
        _check_excel(path)
        # openpyxl reads the XML through defusedxml when it is installed (a LUAR dependency);
        # macros in .xlsm files are never run, and the copy is written as .xlsx without them
        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        name = sheet if isinstance(sheet, str) else list(sheets)[sheet or 0]
        df = sheets[name]
        return df, TableInfo(path=path, kind="excel", sheet=name)
    if suffix == ".xls":
        raise ValueError(t("t_xls"))

    raw = path.read_bytes()
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sep = _sniff_sep(text[:20000])
    # A row with more fields than the header (often a separator inside unquoted text) would make
    # pandas either use the text as the row index or silently cut it; refuse instead of losing text.
    widths = Counter(len(row) for row in csv.reader(io.StringIO(text), delimiter=sep) if row)
    header = len(next(csv.reader(io.StringIO(text), delimiter=sep), []))
    if any(width > header for width in widths):
        bad = next(i for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=sep), 1) if len(row) > header)
        raise ValueError(t("t_extra_fields", line=bad, header=header, sep=sep))
    df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str, keep_default_na=False, index_col=False)
    return df, TableInfo(path=path, kind="csv", sep=sep, encoding=enc)


def _check_excel(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as z:
            unpacked = sum(info.file_size for info in z.infolist())
    except zipfile.BadZipFile as e:
        raise ValueError(t("t_bad_xlsx")) from e
    if unpacked > MAX_XLSX_UNPACKED:
        raise ValueError(t("t_xlsx_too_big", size=unpacked // 2**20, max=MAX_XLSX_UNPACKED // 2**20))


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
        raise FileExistsError(t("t_overwrite", path=path))
    if info.kind == "excel":
        sheet = info.sheet or "Sheet1"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet)
            # openpyxl turns any text starting with "=" into a live formula; every cell LUAR writes
            # is data, so keep it as text (otherwise "=HYPERLINK(...)" in a review becomes a link)
            for row in writer.sheets[sheet].iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"
    else:
        # utf-8-sig so Excel opens accents correctly; keep the source separator
        df.to_csv(path, index=False, sep=info.sep, encoding="utf-8-sig")
    return path
