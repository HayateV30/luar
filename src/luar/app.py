"""Web interface (Gradio). Runs on 127.0.0.1 only and makes no outside connections:
files never leave the machine and the page works offline."""
from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

# Gradio sends usage telemetry and checks its version online unless told not to
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
import pandas as pd

from .backends.base import BackendError
from .backends.laya_backend import INSTALL_HINT, LayaBackend, laya_installed, pick_checkpoint
from .engine import DEFAULT_THRESHOLD, EXPECTED_PREFIX, REVIEW_COL, build_texts, classify, save_result
from .safety import describe_sensitive, scan_sensitive
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
# limits that keep a huge or hostile file from freezing the machine (the command line has no row limit)
MAX_UPLOAD = "50mb"
MAX_ROWS = 20_000
# copies of the user's data (results, saved questions) live here and are deleted when LUAR closes;
# leftovers from a crash are removed after a day. Gradio's own upload cache is cleaned by delete_cache.
WORK_DIR = Path(tempfile.gettempdir()) / "luar"
STALE_AFTER = 24 * 3600
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
/* help icon (i) at the right of a step title; its box opens on hover or keyboard focus */
h3:has(.luar-help) { display: flex; align-items: center; gap: 8px; }
.block:has(.luar-help) { overflow: visible !important; }  /* Gradio's block would clip the box */
.luar-help { position: relative; margin-left: auto; flex: 0 0 auto; width: 20px; height: 20px;
  border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  font: 600 12px/1 Georgia, serif; font-style: italic; cursor: help;
  background: var(--neutral-700); color: white; }
.dark .luar-help { background: var(--neutral-300); color: var(--neutral-900); }
.luar-tip { visibility: hidden; opacity: 0; position: absolute; top: calc(100% + 10px); right: -6px;
  z-index: 50; width: min(340px, 80vw); padding: 12px 14px; border-radius: 8px;
  font: normal 400 14px/1.55 "Inter", ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  letter-spacing: normal; text-align: left; white-space: normal;
  color: var(--body-text-color); background: var(--block-background-fill);
  border: 1px solid var(--border-color-primary); box-shadow: 0 8px 24px rgb(15 23 42 / 0.14);
  transition: opacity 0.12s ease; pointer-events: none; }
.luar-help:hover .luar-tip, .luar-help:focus .luar-tip, .luar-help:focus-within .luar-tip {
  visibility: visible; opacity: 1; }
@media (prefers-reduced-motion: reduce) { .luar-tip { transition: none; } }
/* background: four crosses of light points in a row along the X axis, turning together around it
   (inspired by an old TV intro); behind everything, never clickable, still when motion is reduced */
#luar-bg { position: fixed; inset: 0; z-index: 0; pointer-events: none; perspective: 900px;
  perspective-origin: 15% 85%; --dot: 15, 23, 42; --a: 0.30; --b: 4;
  -webkit-mask: radial-gradient(circle at 14% 86%, #000 0, #000 210px, transparent 540px);
  mask: radial-gradient(circle at 14% 86%, #000 0, #000 210px, transparent 540px); }
.dark #luar-bg { --dot: 255, 255, 255; }
.gradio-container > * { position: relative; z-index: 1; }
#luar-bg .cam { position: absolute; left: 16%; bottom: 16%; transform-style: preserve-3d;
  transform: rotateX(-22deg) rotateY(58deg); }
#luar-bg .spin { position: absolute; transform-style: preserve-3d; animation: luar-spin 120s linear infinite; }
#luar-bg .cross { position: absolute; transform-style: preserve-3d; }
#luar-bg .arm { position: absolute; left: 0; top: calc(var(--w) / -2); height: var(--w);
  width: calc(var(--R) - var(--h)); transform-origin: 0 50%; filter: blur(var(--bl));
  background: radial-gradient(circle, rgba(var(--dot), var(--o)) 0 var(--r), transparent calc(var(--r) + 1.5px))
    left center / var(--g) var(--w) repeat-x; }
@keyframes luar-spin { from { transform: rotateX(0); } to { transform: rotateX(360deg); } }
/* still while the app works (Gradio marks running outputs .pending, also on errors): CPU for Laya */
body:has(.pending) #luar-bg .spin { animation-play-state: paused !important; }
@media (prefers-reduced-motion: reduce) { #luar-bg .spin { animation: none; } }
#luar-run { min-height: 48px; font-size: 1rem; }
button, [role="button"], label:has(input) { cursor: pointer; }
:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
"""

# Help boxes: an (i) icon at the right of each step title; the box opens on hover and on keyboard focus
TIPS = {
    "sheet": "Drop a .csv or .xlsx file (up to 50 MB and 20,000 rows). LUAR works on a copy: your file is "
             "never changed. Then tick the column(s) with the text the model should read. Columns named "
             "expected_... hold answers you already know; they are used to measure accuracy and are never read.",
    "preview": "The first rows of your file, to check it was read correctly: columns, accents and separator.",
    "questions": "Each row is one question. id: a short name (letters, numbers, _) that becomes the new "
                 "column. type: choice picks one option, noul answers yes/no, score places the row on a "
                 "scale (experimental). question: plain language. options: separated by ; with an optional "
                 "description after : (descriptions help a lot).",
    "run": "Confidence threshold: answers below it mark the row needs_review. Laya model variant: auto uses "
           "the English model for English files and the multilingual one for the rest. The first run "
           "downloads the model; later runs work offline.",
    "result": "Download the copy of your spreadsheet with the new columns, and the summary (.md). Rows with "
              "needs_review = yes deserve a human look: low confidence, possible manipulation or empty "
              "text. These files are deleted when LUAR closes, so download them first.",
}


def heading(title: str, tip: str) -> str:
    """A step title with its help icon (kept by Gradio's Markdown sanitizer: class, tabindex, role)."""
    return (f'### {title} <span class="luar-help" tabindex="0">i'
            f'<span class="luar-tip" role="tooltip">{tip}</span></span>')


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


def work_dir() -> Path:
    """A fresh folder for this session's outputs, removed when LUAR closes."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=WORK_DIR))


def clean_work_dir(all_of_it: bool = False) -> None:
    if not WORK_DIR.is_dir():
        return
    now = time.time()
    for folder in WORK_DIR.iterdir():
        try:
            if all_of_it or now - folder.stat().st_mtime > STALE_AFTER:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            pass


def on_file(file):
    hidden = gr.update(visible=False, value=False)
    if file is None:
        return gr.update(choices=[], value=[]), None, "", None, hidden
    try:
        df, info = read_table(file)
    except Exception as e:  # unreadable file: tell the user, keep the UI alive
        raise gr.Error(f"Could not read this file: {e}") from e
    if len(df) > MAX_ROWS:
        raise gr.Error(
            f"This file has {len(df):,} rows; the interface takes up to {MAX_ROWS:,} (about one row per "
            "second with Laya). Split the file, or use the command line: luar run"
        )
    # expected_* columns hold known answers: never offer them as model input
    readable = [c for c in df.columns if not str(c).startswith(EXPECTED_PREFIX)]
    # suggest the column with the longest text on average
    lengths = {c: df[c].astype(str).str.len().mean() for c in readable}
    best = max(lengths, key=lengths.get) if lengths else None
    detail = f"separator `{info.sep}`, {info.encoding}" if info.kind == "csv" else f"sheet `{info.sheet}`"
    status = f"**{Path(file).name}**: {len(df)} rows, {len(df.columns)} columns ({detail})."
    sensitive = scan_sensitive(build_texts(df, readable)) if readable else None
    if sensitive:
        status += (f"\n\n**Personal data found:** {describe_sensitive(sensitive)}. LUAR will only read "
                   "these columns if you confirm you are allowed to process this data.")
    return (
        gr.update(choices=readable, value=[best] if best else []),
        df.head(PREVIEW_ROWS),
        status,
        file,
        gr.update(visible=bool(sensitive), value=False),
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
    path = work_dir() / "questions.json"
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


def on_run(file, columns, table, threshold, checkpoint, allow_sensitive, progress=gr.Progress()):
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
    # before loading the model: personal data is only read with the user's confirmation
    sensitive = scan_sensitive(build_texts(df, columns))
    if sensitive and not allow_sensitive:
        raise gr.Error(
            f"The columns to read hold personal data ({describe_sensitive(sensitive)}). If you are allowed "
            "to process it, tick the confirmation under the columns; otherwise remove that data from the file."
        )
    texts = df[columns].astype(str).agg(" ".join, axis=1).tolist()
    progress(0, desc="Loading the model (the first run downloads it)…")
    try:
        backend = _backend(checkpoint, texts, questions)
        result = classify(
            df, columns, questions, backend, threshold,
            progress=lambda done, total: progress(done / total, desc=f"{done}/{total} rows"),
            allow_sensitive=bool(allow_sensitive),
        )
    except (ValueError, BackendError) as e:
        raise gr.Error(str(e)) from e
    # uploads live in a temp folder; write the outputs to a fresh one
    save_result(result, info, out_dir=work_dir())
    flagged = (result.table[REVIEW_COL] == "yes").sum()
    gr.Info(f"Done: {len(result.table)} rows, {flagged} to review.")
    if result.manipulation_rows:
        gr.Warning(f"{result.manipulation_rows} row(s) look written to steer the answers. They are marked "
                   "for review; check them by hand.")
    return result.table, render_summary(result), [str(result.table_path), str(result.summary_path)]


# Background geometry (see CSS above): each section is 15% smaller than the one in front of it
BG_SECTIONS = 4
BG_SHRINK = 0.15
BG_GAP = 70        # px between sections along the X axis
BG_HOLE = 0.06     # gap at the center of each cross, as a share of the arm length
BG_BLUR = (1, 0.45, 0.15, 0)        # front section blurred, back ones sharp (depth of field)
BG_OPACITY = (1, 0.85, 0.72, 0.6)


def background_html() -> str:
    """Four aligned crosses of four arms each, from the largest (front) to the smallest (back)."""
    crosses = []
    for i in range(BG_SECTIONS):
        f = (1 - BG_SHRINK) ** i
        radius = round(230 * f)
        style = (
            f"transform: translateX({i * BG_GAP}px) rotateY(90deg); --R: {radius}px; "
            f"--h: {round(radius * BG_HOLE)}px; --r: {6 * f:.1f}px; --w: {round(16 * f)}px; "
            f"--g: {round(30 * f)}px; --o: calc(var(--a) * {BG_OPACITY[i]}); "
            f"--bl: calc(var(--b) * {BG_BLUR[i]}px)"
        )
        arms = "".join(
            f'<div class="arm" style="transform: rotate({-90 + 90 * j}deg) translateX(var(--h))"></div>'
            for j in range(4)
        )
        crosses.append(f'<div class="cross" style="{style}">{arms}</div>')
    return f'<div id="luar-bg" aria-hidden="true"><div class="cam"><div class="spin">{"".join(crosses)}</div></div></div>'


def readme_markdown(path: Path) -> str:
    """The README with its screenshots pointed at the local files, so the manual works offline."""
    local = f"/gradio_api/file={quote(IMAGES.as_posix())}/"
    return path.read_text(encoding="utf-8").replace(REMOTE_IMAGES, local)


def build() -> gr.Blocks:
    # Gradio's upload cache (copies of the user's files): checked hourly, removed after 3 hours
    with gr.Blocks(title="LUAR", analytics_enabled=False, delete_cache=(3600, 3 * 3600)) as demo:
        gr.HTML(background_html(), padding=False, container=False)
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
                gr.Markdown(heading("1. Spreadsheet", TIPS["sheet"]))
                upload = gr.File(label="CSV or XLSX", file_types=[".csv", ".xlsx", ".xlsm", ".txt"])
                status = gr.Markdown()
                columns = gr.CheckboxGroup(label="Column(s) the model should read", choices=[])
                allow_sensitive = gr.Checkbox(
                    label="These columns hold personal data, and I am allowed to process it",
                    value=False, visible=False,
                )
                example = gr.Dropdown(
                    list(EXAMPLE_SETS), label="…or try an example", value=None,
                    visible=EXAMPLES.exists(),  # examples ship with the repo, not the wheel
                )
            with gr.Column(scale=2, elem_classes="luar-step"):
                gr.Markdown(heading("Preview", TIPS["preview"]))
                preview = gr.Dataframe(interactive=False, max_height=260, wrap=True)

        with gr.Column(elem_classes="luar-step"):
            gr.Markdown(heading("2. What do you want to know about each row?", TIPS["questions"]))
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

        gr.Markdown(heading("3. Run", TIPS["run"]), elem_classes="luar-step")
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

        gr.Markdown(heading("Result", TIPS["result"]), elem_classes="luar-step")
        downloads = gr.File(label="Download (result copy + summary)", file_count="multiple", interactive=False)
        with gr.Tabs():
            with gr.Tab("Summary"):
                summary = gr.Markdown()
            with gr.Tab("Table"):
                result = gr.Dataframe(interactive=False, max_height=420, wrap=True)

        upload.change(on_file, upload, [columns, preview, status, source, allow_sensitive])
        example.change(on_example, example, [upload, questions])
        q_upload.change(on_load_questions, q_upload, questions)
        q_save.click(on_save_questions, questions, q_file)
        run.click(
            on_run, [source, columns, questions, threshold, checkpoint, allow_sensitive],
            [result, summary, downloads],
        )
    return demo


def launch(port: int = 7860, share: bool = False, open_browser: bool = True) -> None:
    clean_work_dir()                                   # leftovers older than a day (e.g. after a crash)
    atexit.register(clean_work_dir, all_of_it=True)    # this session's copies, when LUAR closes
    build().launch(
        server_name="127.0.0.1", server_port=port, share=share, inbrowser=open_browser,
        theme=THEME, css=CSS, allowed_paths=[str(IMAGES)], max_file_size=MAX_UPLOAD,
    )


if __name__ == "__main__":
    launch()
