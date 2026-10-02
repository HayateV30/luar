"""Web interface (Gradio). Runs on 127.0.0.1 only: files never leave the machine."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import gradio as gr
import pandas as pd

from .backends.laya_backend import LayaBackend, pick_checkpoint
from .engine import DEFAULT_THRESHOLD, EXPECTED_PREFIX, REVIEW_COL, classify, save_result
from .questions import EXPERIMENTAL_TYPES, QuestionError, dump_questions, load_questions, parse_questions
from .report import render_summary
from .tables import read_table

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
QUESTION_HEADERS = ["id", "type", "question", "options"]
PREVIEW_ROWS = 8
_backends: dict[str, LayaBackend] = {}  # loaded models, reused between runs

INTRO = """
# 🌙 LUAR
**Local Utility for Automated Reviews.** Drop a spreadsheet, say what you want to know about each row,
and get a copy with the answers plus a summary. Everything runs on this computer.
"""

QUESTION_HELP = """
**Question types:** `choice` picks one option · `noul` answers yes/no · `score` places the row on an
ordered scale (*experimental*: unreliable without fine-tuning).
**Options:** separate with `;` and optionally add a description after `:`, e.g.
`delivery: shipping, delays; product: defects, quality`. Up to 20 options; `noul` takes none.
Add a column named `expected_<id>` to your file to measure accuracy on rows you already know.
"""


def _questions_to_rows(questions) -> list[list[str]]:
    rows = []
    for q in questions:
        opts = "; ".join(f"{k}: {v}" if v else k for k, v in q.options.items())
        rows.append([q.id, q.type, q.question, opts])
    return rows


def _rows_to_questions(table) -> list:
    df = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table, columns=QUESTION_HEADERS)
    data = []
    for _, r in df.iterrows():
        values = ["" if pd.isna(v) else str(v).strip() for v in r.tolist()[:4]]
        if not any(values):
            continue
        qid, qtype, text, opts = values
        data.append({"id": qid, "type": qtype.lower(), "question": text, "options": opts})
    return parse_questions(data)


def on_file(file):
    if file is None:
        return gr.update(choices=[], value=[]), None, "", None
    try:
        df, info = read_table(file)
    except Exception as e:  # unreadable file: tell the user, keep the UI alive
        raise gr.Error(f"Could not read this file: {e}") from e
    # expected_* columns hold known answers: never offer them as model input
    readable = [c for c in df.columns if not str(c).startswith(EXPECTED_PREFIX)]
    # suggest the column with the longest text on average
    lengths = {c: df[c].astype(str).str.len().mean() for c in readable}
    best = max(lengths, key=lengths.get) if lengths else None
    detail = f"separator `{info.sep}`, {info.encoding}" if info.kind == "csv" else f"sheet `{info.sheet}`"
    status = f"**{Path(file).name}**: {len(df)} rows, {len(df.columns)} columns ({detail})."
    return (
        gr.update(choices=readable, value=[best] if best else []),
        df.head(PREVIEW_ROWS),
        status,
        file,
    )


def on_load_questions(file):
    if file is None:
        return gr.update()
    try:
        return _questions_to_rows(load_questions(file))
    except (QuestionError, json.JSONDecodeError) as e:
        raise gr.Error(str(e)) from e


def on_save_questions(table):
    try:
        questions = _rows_to_questions(table)
    except QuestionError as e:
        raise gr.Error(str(e)) from e
    path = Path(tempfile.mkdtemp(prefix="luar_")) / "questions.json"
    path.write_text(dump_questions(questions), encoding="utf-8")
    return path


def on_example(name):
    data, questions = {
        "English reviews": ("reviews.csv", "reviews_questions.json"),
        "Avaliações em português": ("avaliacoes.csv", "avaliacoes_perguntas.json"),
    }[name]
    rows = _questions_to_rows(load_questions(EXAMPLES / questions))
    return str(EXAMPLES / data), rows


def _backend(checkpoint: str, texts: list[str], questions) -> LayaBackend:
    resolved = pick_checkpoint(texts, questions) if checkpoint == "auto" else checkpoint
    if resolved not in _backends:
        _backends[resolved] = LayaBackend(checkpoint=resolved)
    backend = _backends[resolved]
    backend.name = f"laya ({resolved}{', chosen automatically' if checkpoint == 'auto' else ''})"
    return backend


def on_run(file, columns, table, threshold, checkpoint, progress=gr.Progress()):
    if not file:
        raise gr.Error("Drop a CSV or XLSX file first.")
    if not columns:
        raise gr.Error("Choose at least one column to read.")
    try:
        questions = _rows_to_questions(table)
    except QuestionError as e:
        raise gr.Error(str(e)) from e
    if any(q.type in EXPERIMENTAL_TYPES for q in questions):
        gr.Warning("`score` questions are experimental: check those answers by hand.")

    df, info = read_table(file)
    texts = df[columns].astype(str).agg(" ".join, axis=1).tolist()
    progress(0, desc="Loading the model (the first run downloads it)…")
    backend = _backend(checkpoint, texts, questions)
    try:
        result = classify(
            df, columns, questions, backend, threshold,
            progress=lambda done, total: progress(done / total, desc=f"{done}/{total} rows"),
        )
    except ValueError as e:
        raise gr.Error(str(e)) from e
    # uploads live in a temp folder; write the outputs to a fresh one
    save_result(result, info, out_dir=tempfile.mkdtemp(prefix="luar_"))
    flagged = (result.table[REVIEW_COL] == "yes").sum()
    gr.Info(f"Done: {len(result.table)} rows, {flagged} to review.")
    return result.table, render_summary(result), [str(result.table_path), str(result.summary_path)]


def build() -> gr.Blocks:
    with gr.Blocks(title="LUAR") as demo:
        gr.Markdown(INTRO)
        source = gr.State()
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 1. Spreadsheet")
                upload = gr.File(label="CSV or XLSX", file_types=[".csv", ".xlsx", ".xlsm", ".txt"])
                status = gr.Markdown()
                columns = gr.CheckboxGroup(label="Column(s) the model should read", choices=[])
                example = gr.Dropdown(
                    ["English reviews", "Avaliações em português"], label="…or try an example", value=None,
                    visible=EXAMPLES.exists(),  # examples ship with the repo, not the wheel
                )
            with gr.Column(scale=2):
                gr.Markdown("### Preview")
                preview = gr.Dataframe(interactive=False, max_height=260, wrap=True)

        gr.Markdown("### 2. What do you want to know about each row?")
        questions = gr.Dataframe(
            headers=QUESTION_HEADERS,
            datatype=["str", "str", "str", "str"],
            value=[["", "choice", "", ""]],
            interactive=True,
            row_count=(1, "dynamic"),
            column_count=(4, "fixed"),
            wrap=True,
            column_widths=["12%", "10%", "38%", "40%"],
        )
        gr.Markdown(QUESTION_HELP)
        with gr.Row():
            q_upload = gr.File(label="Load questions (.json)", file_types=[".json"], scale=1)
            q_save = gr.Button("Save questions as .json", scale=0)
            q_file = gr.File(label="Questions file", interactive=False, scale=1)

        gr.Markdown("### 3. Run")
        with gr.Row():
            threshold = gr.Slider(
                0.5, 0.95, value=DEFAULT_THRESHOLD, step=0.05, label="Confidence threshold",
                info="Answers below it mark the row as needs_review",
            )
            checkpoint = gr.Dropdown(
                ["auto", "multilingual", "english"], value="auto", label="Model variant",
                info="auto: English files use the English model, others the multilingual one",
            )
        run = gr.Button("Run", variant="primary")

        gr.Markdown("### Result")
        downloads = gr.File(label="Download (result copy + summary)", file_count="multiple", interactive=False)
        with gr.Tabs():
            with gr.Tab("Summary"):
                summary = gr.Markdown()
            with gr.Tab("Table"):
                result = gr.Dataframe(interactive=False, max_height=420, wrap=True)

        upload.change(on_file, upload, [columns, preview, status, source])
        example.change(on_example, example, [upload, questions])
        q_upload.change(on_load_questions, q_upload, questions)
        q_save.click(on_save_questions, questions, q_file)
        run.click(on_run, [source, columns, questions, threshold, checkpoint], [result, summary, downloads])
    return demo


def launch(port: int = 7860, share: bool = False, open_browser: bool = True) -> None:
    build().launch(
        server_name="127.0.0.1", server_port=port, share=share, inbrowser=open_browser,
        theme=gr.themes.Soft(primary_hue="indigo", secondary_hue="slate"),
    )


if __name__ == "__main__":
    launch()
