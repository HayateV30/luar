"""Command line: `luar run`, `luar columns`, `luar download`, `luar ui`."""
from __future__ import annotations

import argparse
import sys

from .documents import READERS
from .engine import DEFAULT_THRESHOLD


def _cmd_columns(args) -> int:
    from .tables import read_table

    df, info = read_table(args.file, sheet=args.sheet, reader=args.ocr)
    detail = {"csv": f", separator {info.sep!r}, {info.encoding}", "excel": f", sheet {info.sheet!r}",
              "document": f", one row per page, read with {args.ocr}"}[info.kind]
    print(f"{info.path.name}: {len(df)} rows ({info.kind}{detail})")
    for col in df.columns:
        sample = next((str(v) for v in df[col] if str(v).strip()), "")
        print(f"  - {col}: {sample[:60]}")
    return 0


def _cmd_run(args) -> int:
    from .backends import make_backend
    from .engine import run_file
    from .questions import load_questions

    questions = load_questions(args.questions)
    if args.engine == "thx":
        if args.checkpoint != "auto":
            raise ValueError("--checkpoint only applies to the Laya engine.")
        backend = make_backend("thx", device=args.device)
    else:
        backend = make_backend("laya", checkpoint=args.checkpoint, device=args.device)

    def progress(done, total):
        print(f"\r  {done}/{total} rows", end="", file=sys.stderr, flush=True)

    print(f"Engine: {backend.name}", file=sys.stderr)
    result = run_file(
        args.file, questions, args.columns, backend,
        threshold=args.threshold, out_dir=args.out_dir, sheet=args.sheet, progress=progress,
        allow_sensitive=args.allow_sensitive_data, reader=args.ocr,
    )
    flagged = (result.table["needs_review"] == "yes").sum()
    print(file=sys.stderr)
    print(f"Done: {len(result.table)} rows, {flagged} to review.")
    if result.manipulation_rows:
        print(f"  Warning: {result.manipulation_rows} row(s) look written to steer the answers; "
              "they are marked for review.")
    print(f"  Result:  {result.table_path}")
    print(f"  Summary: {result.summary_path}")
    return 0


DOWNLOAD_DEFAULT = ("multilingual", "english")  # the two checkpoints `auto` picks from
THX_MODEL = "thx-01"
OCR_MODELS = ("ocr", "ocria-nano")  # Tesseract's Portuguese model; the optional OCRia-nano


def _cmd_download(args) -> int:
    from .backends.laya_backend import download_checkpoints
    from .backends.thx_backend import download_model

    asked = tuple(args.checkpoints or DOWNLOAD_DEFAULT)
    laya = tuple(name for name in asked if name != THX_MODEL and name not in OCR_MODELS)
    if laya:
        print("Downloading the Laya models (about 1.5 GB, only once)…", file=sys.stderr)
        for folder in download_checkpoints(checkpoints=laya):
            print(f"  {folder}")
    if THX_MODEL in asked:
        print("Downloading the THX-01 model (about 650 MB, only once)…", file=sys.stderr)
        print(f"  {download_model()}")
    if "ocr" in asked:
        from .documents import tessdata_dir

        print("Downloading Tesseract's Portuguese model (about 8 MB, only once)…", file=sys.stderr)
        print(f"  {tessdata_dir()}")
    if "ocria-nano" in asked:
        from .documents import OCRIA_LICENSE, download_ocria

        print("Downloading OCRia-nano (about 50 MB). Its license is free for personal use and for "
              f"organizations under US$ 2 million in annual revenue; read it first: {OCRIA_LICENSE}",
              file=sys.stderr)
        print(f"  {download_ocria()}")
    print("Done: LUAR now runs offline.")
    return 0


def _cmd_ui(args) -> int:
    from .app import launch

    launch(port=args.port, share=False, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="luar",
        description="LUAR (Local Utility for Automated Reviews): catalog spreadsheet rows with a local decision model.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="classify a CSV/XLSX file")
    p.add_argument("file")
    p.add_argument("-q", "--questions", required=True, help="questions JSON file")
    p.add_argument("-c", "--columns", required=True, nargs="+", help="column(s) to read")
    p.add_argument("-t", "--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help=f"confidence below this marks the row for review (default {DEFAULT_THRESHOLD})")
    p.add_argument("-o", "--out-dir", help="output folder (default: next to the file)")
    p.add_argument("--sheet", help="Excel sheet name (default: first)")
    p.add_argument("--engine", default="laya", choices=["laya", "thx"],
                   help='decision engine (default: laya; thx needs pip install "luar[thx]")')
    p.add_argument("--checkpoint", default="auto", choices=["auto", "multilingual", "english", "typed-decisions"],
                   help="Laya model variant (default: auto, by the file's language)")
    p.add_argument("--device", help="cpu or cuda (default: automatic)")
    p.add_argument("--allow-sensitive-data", action="store_true",
                   help="read columns holding personal data (CPF, CNPJ, card numbers, e-mails, phones); "
                        "only if you are allowed to process it")
    p.add_argument("--ocr", default="tesseract", choices=READERS,
                   help='reader for PDFs and images (default: tesseract; needs pip install "luar[ocr]"). '
                        "ocria-nano has a restricted license: see the manual")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("columns", help="list a file's columns with a sample value")
    p.add_argument("file")
    p.add_argument("--sheet")
    p.add_argument("--ocr", default="tesseract", choices=READERS, help="reader for PDFs and images")
    p.set_defaults(func=_cmd_columns)

    p = sub.add_parser("download", help="fetch the models now, so LUAR works offline afterwards")
    # no list default: before Python 3.14, argparse checks a list default against `choices` as one value
    p.add_argument("checkpoints", nargs="*",
                   choices=["multilingual", "english", "typed-decisions", THX_MODEL, *OCR_MODELS],
                   help="which models (default: multilingual and english, the ones `auto` picks from)")
    p.set_defaults(func=_cmd_download)

    p = sub.add_parser("ui", help="open the web interface (local only)")
    p.add_argument("--port", type=int, default=7860)
    p.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    p.set_defaults(func=_cmd_ui)

    args = ap.parse_args(argv)
    from .backends.base import BackendError

    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, FileExistsError, BackendError) as e:
        from .safety import SensitiveDataError

        hint = " On the command line, confirm with --allow-sensitive-data." if isinstance(e, SensitiveDataError) else ""
        print(f"error: {e}{hint}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
