"""Web interface (Gradio). Runs on 127.0.0.1 only and makes no outside connections:
files never leave the machine and the page works offline."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

# Gradio sends usage telemetry and checks its version online unless told not to
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
import pandas as pd

from .backends.base import BackendError
from .backends.laya_backend import INSTALL_HINT, LayaBackend, laya_installed, pick_checkpoint
from .engine import DEFAULT_THRESHOLD, EXPECTED_PREFIX, REVIEW_COL, classify, save_result
from .questions import EXPERIMENTAL_TYPES, QuestionError, dump_questions, load_questions, parse_questions
from .report import render_summary
from .tables import read_table

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
# the manual and the sample ship with the repo, not the wheel: their buttons hide when missing
READMES = {"Português": ROOT / "README.pt-BR.md", "English": ROOT / "README.md"}
SAMPLE_CSV = EXAMPLES / "amostra_teste.csv"
SAMPLE_QUESTIONS = EXAMPLES / "amostra_teste_perguntas.json"  # the questions that go with the sample
# the READMEs link their screenshots on GitHub (so PyPI shows them); the app serves the local copies
IMAGES = ROOT / "docs" / "images"
REMOTE_IMAGES = "https://raw.githubusercontent.com/HayateV30/luar/main/docs/images/"
QUESTION_HEADERS = ["id", "type", "question", "options"]
PREVIEW_ROWS = 8
_backends: dict[str, LayaBackend] = {}  # loaded models, reused between runs

TAGLINE = """
**Local Utility for Automated Reviews.** Drop a spreadsheet, say what you want to know about each row,
and get a copy with the answers plus a summary. Everything runs on this computer, with the Laya model.
"""

# Neutral slate palette: the only strong color is the dark primary button (AA contrast in both modes).
THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.slate,
    secondary_hue=gr.themes.colors.slate,
    neutral_hue=gr.themes.colors.slate,
    radius_size=gr.themes.sizes.radius_md,
    font=["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
    font_mono=["ui-monospace", "Consolas", "monospace"],
).set(
    body_background_fill="*neutral_50",
    body_background_fill_dark="*neutral_950",
    block_background_fill="white",
    block_background_fill_dark="*neutral_900",
    block_border_color="*neutral_200",
    block_border_color_dark="*neutral_800",
    block_shadow="0 1px 2px rgb(15 23 42 / 0.06)",
    button_primary_background_fill="*neutral_900",
    button_primary_background_fill_hover="*neutral_700",
    button_primary_background_fill_dark="*neutral_100",
    button_primary_background_fill_hover_dark="*neutral_300",
    button_primary_text_color="white",
    button_primary_text_color_dark="*neutral_900",
    button_primary_border_color="*neutral_900",
    button_primary_border_color_dark="*neutral_100",
    button_secondary_background_fill="white",
    button_secondary_background_fill_hover="*neutral_100",
    button_secondary_background_fill_dark="*neutral_800",
    button_secondary_background_fill_hover_dark="*neutral_700",
    button_secondary_border_color="*neutral_300",
    button_secondary_border_color_dark="*neutral_700",
    checkbox_background_color_selected="*neutral_900",
    checkbox_background_color_selected_dark="*neutral_100",
    checkbox_border_color_selected="*neutral_900",
    checkbox_border_color_selected_dark="*neutral_100",
    slider_color="*neutral_900",
    slider_color_dark="*neutral_100",
)

CSS = """
.gradio-container { max-width: 1200px !important; margin: 0 auto; }
/* header: title centered on the page, actions on the right of the same line */
#luar-header { display: grid !important; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px; }
#luar-header > :first-child { grid-column: 2; }
#luar-header h1 { margin: 0; text-align: center; letter-spacing: 0.08em; }
#luar-actions { grid-column: 3; justify-self: end; display: flex; flex-wrap: nowrap; justify-content: flex-end; gap: 8px; }
#luar-actions > * { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
#luar-actions button { min-height: 40px; padding: 0 16px; white-space: nowrap; }
#luar-tagline { text-align: center; max-width: 72ch; margin: 0 auto; }
@media (max-width: 640px) {
  #luar-header { grid-template-columns: 1fr; }
  #luar-header > :first-child, #luar-actions { grid-column: 1; justify-self: center; justify-content: center; }
}
.luar-step h3 { margin-top: 8px; }
#luar-run { min-height: 48px; font-size: 1rem; }
button, [role="button"], label:has(input) { cursor: pointer; }
:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
"""

QUESTION_HELP = """
**Question types:** `choice` picks one option · `noul` answers yes/no · `score` places the row on an
ordered scale (*experimental*: the least reliable type in our tests).
**Options:** separate with `;` and optionally add a description after `:`, e.g.
`delivery: shipping, delays; product: defects, quality`. Up to 20 options; `noul` takes none.
Add a column named `expected_<id>` to your file to measure accuracy on rows you already know.
"""

NO_QUESTIONS = (
    "There are no questions yet. In step 2, fill in at least the id and the question of one row, "
    "or load a questions .json file in \"Load questions (.json)\"."
)
# only offered where the sample buttons and the examples menu exist (a repository checkout, not PyPI)
SAMPLE_HINT = (
    " Trying the Sample CSV? Download Sample JSON at the top of the page and load it there, or pick "
    "\"Amostra de teste (Sample CSV)\" in \"…or try an example\" to load both at once."
)


def no_questions_message() -> str:
    return NO_QUESTIONS + (SAMPLE_HINT if SAMPLE_QUESTIONS.exists() else "")


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
        qid, qtype, text, opts = values
        # the table starts with a row whose type is already filled in: a type alone is not a question
        if not (qid or text or opts):
            continue
        data.append({"id": qid, "type": qtype.lower(), "question": text, "options": opts})
    if not data:
        raise QuestionError(no_questions_message())
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


EXAMPLE_SETS = {
    "English reviews": ("reviews.csv", "reviews_questions.json"),
    "English reviews: severity (score)": ("reviews.csv", "reviews_severity_question.json"),
    "Avaliações em português": ("avaliacoes.csv", "avaliacoes_perguntas.json"),
    "Amostra de teste (Sample CSV)": ("amostra_teste.csv", "amostra_teste_perguntas.json"),
}


def on_example(name):
    data, questions = EXAMPLE_SETS[name]
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
    try:
        backend = _backend(checkpoint, texts, questions)
        result = classify(
            df, columns, questions, backend, threshold,
            progress=lambda done, total: progress(done / total, desc=f"{done}/{total} rows"),
        )
    except (ValueError, BackendError) as e:
        raise gr.Error(str(e)) from e
    # uploads live in a temp folder; write the outputs to a fresh one
    save_result(result, info, out_dir=tempfile.mkdtemp(prefix="luar_"))
    flagged = (result.table[REVIEW_COL] == "yes").sum()
    gr.Info(f"Done: {len(result.table)} rows, {flagged} to review.")
    return result.table, render_summary(result), [str(result.table_path), str(result.summary_path)]


def readme_markdown(path: Path) -> str:
    """The README with its screenshots pointed at the local files, so the manual works offline."""
    local = f"/gradio_api/file={quote(IMAGES.as_posix())}/"
    return path.read_text(encoding="utf-8").replace(REMOTE_IMAGES, local)


def build() -> gr.Blocks:
    with gr.Blocks(title="LUAR", analytics_enabled=False) as demo:
        readmes = {lang: path for lang, path in READMES.items() if path.exists()}
        with gr.Row(elem_id="luar-header"):
            gr.Markdown("# LUAR")
            with gr.Row(elem_id="luar-actions"):
                readme_btn = gr.Button("README", variant="secondary", size="md", visible=bool(readmes))
                for label, path in (("Sample CSV", SAMPLE_CSV), ("Sample JSON", SAMPLE_QUESTIONS)):
                    gr.DownloadButton(
                        label, value=str(path) if path.exists() else None,
                        variant="secondary", size="md", visible=path.exists(),
                    )
        gr.Markdown(TAGLINE, elem_id="luar-tagline")
        with gr.Sidebar(label="README", open=False, position="right", width="min(760px, 92vw)") as manual:
            with gr.Tabs():
                for lang, path in readmes.items():
                    with gr.Tab(lang):
                        gr.Markdown(readme_markdown(path))
        readme_btn.click(lambda: gr.Sidebar(open=True), None, manual)
        if not laya_installed():
            gr.Markdown(f"**The Laya engine could not be loaded.** Reinstall it with `{INSTALL_HINT}` and restart LUAR.")
        source = gr.State()
        with gr.Row(equal_height=False):
            with gr.Column(scale=1, elem_classes="luar-step"):
                gr.Markdown("### 1. Spreadsheet")
                upload = gr.File(label="CSV or XLSX", file_types=[".csv", ".xlsx", ".xlsm", ".txt"])
                status = gr.Markdown()
                columns = gr.CheckboxGroup(label="Column(s) the model should read", choices=[])
                example = gr.Dropdown(
                    list(EXAMPLE_SETS), label="…or try an example", value=None,
                    visible=EXAMPLES.exists(),  # examples ship with the repo, not the wheel
                )
            with gr.Column(scale=2, elem_classes="luar-step"):
                gr.Markdown("### Preview")
                preview = gr.Dataframe(interactive=False, max_height=260, wrap=True)

        with gr.Column(elem_classes="luar-step"):
            gr.Markdown("### 2. What do you want to know about each row?")
            questions = gr.Dataframe(
                headers=QUESTION_HEADERS,
                datatype=["str", "str", "str", "str"],
                value=[["", "choice", "", ""]],
                interactive=True,
                # An int means (1, "dynamic"): rows can be added. Tuples are deprecated for row_count,
                # and row_limits/column_limits are not implemented yet (Gradio 6.29).
                row_count=1,
                column_count=(4, "fixed"),
                wrap=True,
                column_widths=["12%", "10%", "38%", "40%"],
            )
            gr.Markdown(QUESTION_HELP)
        with gr.Row():
            q_upload = gr.File(label="Load questions (.json)", file_types=[".json"], scale=1)
            q_save = gr.Button("Save questions as .json", variant="secondary", scale=0)
            q_file = gr.File(label="Questions file", interactive=False, scale=1)

        gr.Markdown("### 3. Run", elem_classes="luar-step")
        with gr.Row():
            threshold = gr.Slider(
                0.5, 0.95, value=DEFAULT_THRESHOLD, step=0.05, label="Confidence threshold",
                info="Answers below it mark the row as needs_review",
            )
            checkpoint = gr.Dropdown(
                ["auto", "multilingual", "english"], value="auto", label="Laya model variant",
                info="auto: English files use the English model, others the multilingual one",
            )
        run = gr.Button("Run", variant="primary", size="lg", elem_id="luar-run")

        gr.Markdown("### Result", elem_classes="luar-step")
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
        run.click(
            on_run, [source, columns, questions, threshold, checkpoint],
            [result, summary, downloads],
        )
    return demo


def launch(port: int = 7860, share: bool = False, open_browser: bool = True) -> None:
    build().launch(
        server_name="127.0.0.1", server_port=port, share=share, inbrowser=open_browser,
        theme=THEME, css=CSS, allowed_paths=[str(IMAGES)],
    )


if __name__ == "__main__":
    launch()
