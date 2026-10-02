"""Markdown summary of a run."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from .engine import REASONS_COL, REVIEW_COL, Result, accuracy, build_texts, confidence_col
from .questions import EXPERIMENTAL_TYPES

MAX_REVIEW_ROWS = 50
SNIPPET = 80


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET else text[: SNIPPET - 1] + "…"


def render_summary(result: Result) -> str:
    df = result.table
    n = len(df)
    flagged = df[df[REVIEW_COL] == "yes"]
    lines = [
        f"# LUAR summary: {result.source or 'table'}",
        "",
        f"- **Date:** {result.started:%Y-%m-%d %H:%M}",
        f"- **Engine:** {result.backend_name}",
        f"- **Rows:** {n}",
        f"- **Columns read:** {', '.join(result.text_columns)}",
        f"- **Confidence threshold:** {result.threshold:.2f}",
        f"- **Rows to review:** {len(flagged)} ({len(flagged) / n:.0%})" if n else "- **Rows to review:** 0",
        f"- **Time:** {result.seconds:.1f} s",
    ]
    if result.table_path:
        lines.append(f"- **Result file:** `{result.table_path.name}`")

    for q in result.questions:
        lines += ["", f"## {q.id} ({q.type})", "", f"> {q.question}", ""]
        if q.type in EXPERIMENTAL_TYPES:
            lines += [
                "> **Experimental:** `score` was the least reliable question type in our tests "
                "(about 70-80% agreement with hand labels, on both engines). Check these results by hand.",
                "",
            ]
        values = [v for v in df[q.id] if pd.notna(v)]
        counts = Counter(values)
        order = list(q.options) if q.options else ["yes", "no"]
        order += [v for v in counts if v not in order]
        lines += ["| Answer | Rows | % |", "|---|---:|---:|"]
        for label in order:
            c = counts.get(label, 0)
            lines.append(f"| {_cell(label)} | {c} | {c / n:.0%} |" if n else f"| {_cell(label)} | 0 | 0% |")
        unanswered = n - len(values)
        if unanswered:
            lines.append(f"| *(no answer)* | {unanswered} | {unanswered / n:.0%} |")

        confs = [float(c) for c in df[confidence_col(q.id)] if pd.notna(c)]
        if confs:
            low = sum(c < result.threshold for c in confs)
            lines += [
                "",
                f"Average confidence {sum(confs) / len(confs):.2f}; "
                f"{low} row(s) below the threshold.",
            ]
        acc = accuracy(result, q)
        if acc and acc[1]:
            hits, total = acc
            lines.append(f"**Accuracy against `expected_{q.id}`: {hits}/{total} ({hits / total:.0%}).**")

    lines += ["", "## Rows to review", ""]
    if flagged.empty:
        lines.append("None: every answer is above the confidence threshold.")
    else:
        texts = build_texts(flagged, result.text_columns)
        lines += ["| Row | Why | Text |", "|---:|---|---|"]
        for (idx, row), text in list(zip(flagged.iterrows(), texts))[:MAX_REVIEW_ROWS]:
            # +2: spreadsheet row number (1-based, after the header)
            lines.append(f"| {idx + 2} | {_cell(row[REASONS_COL])} | {_cell(_snippet(text))} |")
        if len(flagged) > MAX_REVIEW_ROWS:
            lines.append(
                f"\n…and {len(flagged) - MAX_REVIEW_ROWS} more. Filter `{REVIEW_COL}` = yes in the result file."
            )
    lines += [
        "",
        "---",
        "Answers come from an automated model and can be wrong. Rows marked "
        f"`{REVIEW_COL}` deserve a human look; the original file was not changed.",
        "",
    ]
    return "\n".join(lines)
