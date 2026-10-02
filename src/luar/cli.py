"""Command line: `luar run`, `luar columns`, `luar ui`."""
from __future__ import annotations

import argparse
import sys

from .engine import DEFAULT_THRESHOLD


def _cmd_columns(args) -> int:
    from .tables import read_table

    df, info = read_table(args.file, sheet=args.sheet)
    print(f"{info.path.name}: {len(df)} rows ({info.kind}"
          + (f", separator {info.sep!r}, {info.encoding}" if info.kind == "csv" else f", sheet {info.sheet!r}")
          + ")")
    for col in df.columns:
        sample = next((str(v) for v in df[col] if str(v).strip()), "")
        print(f"  - {col}: {sample[:60]}")
    return 0


def _cmd_run(args) -> int:
    from .backends import make_backend
    from .engine import run_file
    from .questions import load_questions

    from .backends import default_engine

    questions = load_questions(args.questions)
    args.engine = args.engine or default_engine()
    if args.engine == "laya":
        backend = make_backend("laya", checkpoint=args.checkpoint, device=args.device)
    else:
        backend = make_backend("lmstudio", model=args.model, base_url=args.lmstudio_url)

    def progress(done, total):
        print(f"\r  {done}/{total} rows", end="", file=sys.stderr, flush=True)

    print(f"Engine: {backend.name}" + (" (the first run downloads the model)" if args.engine == "laya" else ""),
          file=sys.stderr)
    result = run_file(
        args.file, questions, args.columns, backend,
        threshold=args.threshold, out_dir=args.out_dir, sheet=args.sheet, progress=progress,
    )
    flagged = (result.table["needs_review"] == "yes").sum()
    print(file=sys.stderr)
    print(f"Done: {len(result.table)} rows, {flagged} to review.")
    print(f"  Result:  {result.table_path}")
    print(f"  Summary: {result.summary_path}")
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
    p.add_argument("-e", "--engine", choices=["laya", "lmstudio"],
                   help="decision engine (default: laya if installed, otherwise lmstudio)")
    p.add_argument("--checkpoint", default="auto", choices=["auto", "multilingual", "english", "typed-decisions"],
                   help="laya: model variant (default: auto, by the file's language)")
    p.add_argument("--device", help="laya: cpu or cuda (default: automatic)")
    p.add_argument("--model", help="lmstudio: model id (default: the first loaded model)")
    p.add_argument("--lmstudio-url", help="lmstudio: server URL (default: $LUAR_LMSTUDIO_URL or http://localhost:1234/v1)")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("columns", help="list a file's columns with a sample value")
    p.add_argument("file")
    p.add_argument("--sheet")
    p.set_defaults(func=_cmd_columns)

    p = sub.add_parser("ui", help="open the web interface (local only)")
    p.add_argument("--port", type=int, default=7860)
    p.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    p.set_defaults(func=_cmd_ui)

    args = ap.parse_args(argv)
    from .backends.base import BackendError

    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, FileExistsError, BackendError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
