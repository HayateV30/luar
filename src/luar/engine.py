"""Runs the questions over every row and adds the answer columns."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from .backends.base import Answer, Backend, Progress
from .questions import Question, validate_questions
from .tables import TableInfo, output_paths, read_table, write_table

DEFAULT_THRESHOLD = 0.7
REVIEW_COL = "needs_review"
REASONS_COL = "review_reasons"
EXPECTED_PREFIX = "expected_"

_YES = {"yes", "y", "sim", "s", "true", "1", "verdadeiro", "x"}
_NO = {"no", "n", "nao", "não", "false", "0", "falso"}


@dataclass
class Result:
    table: pd.DataFrame
    questions: list[Question]
    text_columns: list[str]
    threshold: float
    backend_name: str
    source: str = ""
    started: datetime = field(default_factory=datetime.now)
    seconds: float = 0.0
    table_path: Path | None = None
    summary_path: Path | None = None


def confidence_col(qid: str) -> str:
    return f"{qid}_confidence"


def build_texts(df: pd.DataFrame, text_columns: list[str]) -> list[str]:
    """One text per row. A single column is used as is; several become "column: value" lines."""
    missing = [c for c in text_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {', '.join(missing)}")
    if not text_columns:
        raise ValueError("Choose at least one column to read.")
    texts = []
    for _, row in df[text_columns].iterrows():
        parts = []
        for col in text_columns:
            val = row[col]
            val = "" if pd.isna(val) else str(val).strip()
            if not val:
                continue
            parts.append(val if len(text_columns) == 1 else f"{col}: {val}")
        texts.append("\n".join(parts))
    return texts


def normalize_label(value, qtype: str) -> str | None:
    """Make answers and expected values comparable (case, spaces, yes/no synonyms)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if qtype == "noul":
        if s in _YES:
            return "yes"
        if s in _NO:
            return "no"
    return s


def _check_columns(df: pd.DataFrame, questions: list[Question]) -> None:
    new_cols = [REVIEW_COL, REASONS_COL]
    for q in questions:
        new_cols += [q.id, confidence_col(q.id)]
    clash = [c for c in new_cols if c in df.columns]
    if clash:
        raise ValueError(
            f"The file already has column(s) {', '.join(clash)}; rename the question id(s) "
            "or use the original file instead of a previous LUAR result."
        )


def classify(
    df: pd.DataFrame,
    text_columns: list[str],
    questions: list[Question],
    backend: Backend,
    threshold: float = DEFAULT_THRESHOLD,
    progress: Progress | None = None,
) -> Result:
    """Return a copy of `df` with, per question, `<id>` and `<id>_confidence`,
    plus `needs_review` / `review_reasons` for rows below the confidence threshold."""
    validate_questions(questions)
    _check_columns(df, questions)
    if not 0 <= threshold <= 1:
        raise ValueError("The confidence threshold must be between 0 and 1.")

    started = datetime.now()
    texts = build_texts(df, text_columns)
    filled = [i for i, t in enumerate(texts) if t]
    answers: list[dict[str, Answer] | None] = [None] * len(texts)
    if filled:
        decided = backend.decide([texts[i] for i in filled], questions, progress)
        for i, a in zip(filled, decided):
            answers[i] = a

    out = df.copy()
    review, reasons = [], []
    for q in questions:
        values, confs = [], []
        for a in answers:
            ans = a.get(q.id) if a else None
            values.append(ans.value if ans else None)
            confs.append(None if not ans or ans.confidence is None else round(ans.confidence, 3))
        out[q.id] = values
        out[confidence_col(q.id)] = confs

    for i, a in enumerate(answers):
        if a is None:
            why = ["empty text"]
        else:
            why = [
                q.id for q in questions
                if a.get(q.id) is None or a[q.id].value is None
                or a[q.id].confidence is None or a[q.id].confidence < threshold
            ]
        review.append("yes" if why else "")
        reasons.append(", ".join(why))
    out[REVIEW_COL] = review
    out[REASONS_COL] = reasons

    return Result(
        table=out,
        questions=questions,
        text_columns=text_columns,
        threshold=threshold,
        backend_name=getattr(backend, "name", type(backend).__name__),
        started=started,
        seconds=(datetime.now() - started).total_seconds(),
    )


def accuracy(result: Result, q: Question) -> tuple[int, int] | None:
    """(hits, compared) against an `expected_<id>` column, if the file has one."""
    col = EXPECTED_PREFIX + q.id
    if col not in result.table.columns:
        return None
    hits = total = 0
    for got, exp in zip(result.table[q.id], result.table[col]):
        exp_n = normalize_label(exp, q.type)
        if exp_n is None:
            continue
        total += 1
        hits += normalize_label(got, q.type) == exp_n
    return hits, total


def run_file(
    path: str | Path,
    questions: list[Question],
    text_columns: list[str],
    backend: Backend,
    threshold: float = DEFAULT_THRESHOLD,
    out_dir: str | Path | None = None,
    sheet: str | int | None = None,
    progress: Progress | None = None,
) -> Result:
    """Read `path`, classify it and write `<name>_luar.<ext>` + `<name>_luar_summary.md`.
    The source file is never modified."""
    df, info = read_table(path, sheet=sheet)
    result = classify(df, text_columns, questions, backend, threshold, progress)
    return save_result(result, info, out_dir)


def save_result(result: Result, info: TableInfo, out_dir: str | Path | None = None) -> Result:
    """Write the result copy and the Markdown summary next to the source (or in `out_dir`)."""
    from .report import render_summary

    result.source = info.path.name
    table_path, summary_path = output_paths(info, out_dir)
    write_table(result.table, table_path, info)
    result.table_path = table_path
    summary_path.write_text(render_summary(result), encoding="utf-8")
    result.summary_path = summary_path
    return result
