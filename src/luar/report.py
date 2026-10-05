"""Markdown summary of a run."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from .engine import REASONS_COL, REVIEW_COL, Result, accuracy, build_texts, confidence_col
from .i18n import dec, num, rows, t
from .questions import EXPERIMENTAL_TYPES
from .safety import describe_sensitive

MAX_REVIEW_ROWS = 50
SNIPPET = 80
# the English phrases engine.py and safety.py write to review_reasons, longest first
REASON_PHRASES = ("possible manipulation", "instructions to the model", "claimed answer for",
                  "fake answer for", "order about", "empty text")


# "!" and "[" "]" are enough to stop images and links; the rest stops formatting and table breaks
_MD_SPECIAL = set("\\`*_[]!|~#")


def _md(text) -> str:
    """Spreadsheet text shown as plain text: no images, links, HTML or formatting can come from it
    (e.g. "![x](https://tracker/pixel.png)" would make the browser fetch an outside URL)."""
    text = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join("\\" + c if c in _MD_SPECIAL else c for c in text)


def _cell(text) -> str:
    return _md(str(text).replace("\n", " ").strip())


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET else text[: SNIPPET - 1] + "…"


def _reasons(text: str) -> str:
    """review_reasons as written to the spreadsheet (English, it is data), in the interface language."""
    for phrase in REASON_PHRASES:
        text = text.replace(phrase, t("reason_" + phrase))
    return text


def _pct(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "0%"


def render_summary(result: Result) -> str:
    """The summary in the current interface language (English outside the web interface)."""
    df = result.table
    n = len(df)
    flagged = df[df[REVIEW_COL] == "yes"]
    lines = [
        t("r_title", source=_md(result.source or t("r_table"))),
        "",
        f"- **{t('r_date')}:** {result.started.strftime(t('r_date_format'))}",
        f"- **{t('r_engine')}:** {result.backend_name}",
        f"- **{t('r_rows')}:** {num(n)}",
        f"- **{t('r_columns_read')}:** {_md(', '.join(result.text_columns))}",
        f"- **{t('r_threshold')}:** {dec(result.threshold)}",
        f"- **{t('r_to_review')}:** {num(len(flagged))} ({_pct(len(flagged), n)})",
        f"- **{t('r_time')}:** {dec(result.seconds, 1)} s",
    ]
    if result.table_path:
        lines.append(f"- **{t('r_result_file')}:** {_md(result.table_path.name)}")
    if result.sensitive:
        lines += ["", t("r_personal", found=describe_sensitive(result.sensitive))]
    if result.manipulation_rows:
        lines += ["", t("r_manipulation", rows=rows(result.manipulation_rows))]

    for q in result.questions:
        lines += ["", f"## {_md(q.id)} ({q.type})", "", f"> {_md(q.question)}", ""]
        if q.type in EXPERIMENTAL_TYPES:
            lines += [t("r_experimental"), ""]
        values = [v for v in df[q.id] if pd.notna(v)]
        counts = Counter(values)
        order = list(q.options) if q.options else ["yes", "no"]
        order += [v for v in counts if v not in order]
        lines += [t("r_answers_header"), "|---|---:|---:|"]
        for label in order:
            c = counts.get(label, 0)
            # yes/no stay as written to the file; the summary adds their translation
            shown = t("r_" + label) if q.type == "noul" and label in ("yes", "no") else _cell(label)
            lines.append(f"| {shown} | {num(c)} | {_pct(c, n)} |")
        unanswered = n - len(values)
        if unanswered:
            lines.append(f"| {t('r_no_answer')} | {num(unanswered)} | {_pct(unanswered, n)} |")

        confs = [float(c) for c in df[confidence_col(q.id)] if pd.notna(c)]
        if confs:
            low = sum(c < result.threshold for c in confs)
            lines += ["", t("r_confidence", avg=dec(sum(confs) / len(confs)), low=rows(low))]
        acc = accuracy(result, q)
        if acc and acc[1]:
            hits, total = acc
            lines.append(t("r_accuracy", column=f"expected_{q.id}", hits=num(hits), total=num(total),
                           pct=_pct(hits, total)))

    lines += ["", t("r_review_title"), ""]
    if flagged.empty:
        lines.append(t("r_review_none"))
    else:
        texts = build_texts(flagged, result.text_columns)
        lines += [t("r_review_header"), "|---:|---|---|"]
        for (idx, row), text in list(zip(flagged.iterrows(), texts))[:MAX_REVIEW_ROWS]:
            # +2: spreadsheet row number (1-based, after the header)
            lines.append(f"| {idx + 2} | {_cell(_reasons(row[REASONS_COL]))} | {_cell(_snippet(text))} |")
        if len(flagged) > MAX_REVIEW_ROWS:
            lines.append("\n" + t("r_review_more", n=num(len(flagged) - MAX_REVIEW_ROWS), column=REVIEW_COL))
    lines += ["", "---", t("r_footer", column=REVIEW_COL), ""]
    return "\n".join(lines)
