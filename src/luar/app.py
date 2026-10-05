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
from .i18n import TEXTS, language, normalize, num, rows, t
from .safety import describe_sensitive, scan_sensitive
from .questions import EXPERIMENTAL_TYPES, QuestionError, dump_questions, load_questions, parse_questions
from .report import render_summary
from .tables import read_table

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
# the manual and the sample ship with the repo, not the wheel: their buttons hide when missing
# (language code: tab name, file); the tab of the interface language opens first
READMES = {"pt": ("Português", ROOT / "README.pt-BR.md"), "en": ("English", ROOT / "README.md")}
SAMPLE_CSV = EXAMPLES / "amostra_teste.csv"
SAMPLE_QUESTIONS = EXAMPLES / "amostra_teste_perguntas.json"  # the questions that go with the sample
# the READMEs link their screenshots on GitHub (so PyPI shows them); the app serves the local copies
IMAGES = ROOT / "docs" / "images"
REMOTE_IMAGES = "https://raw.githubusercontent.com/HayateV30/luar/main/docs/images/"
PREVIEW_ROWS = 8
# limits that keep a huge or hostile file from freezing the machine (the command line has no row limit)
MAX_UPLOAD = "50mb"
MAX_ROWS = 20_000
# copies of the user's data (results, saved questions) live here and are deleted when LUAR closes;
# leftovers from a crash are removed after a day. Gradio's own upload cache is cleaned by delete_cache.
WORK_DIR = Path(tempfile.gettempdir()) / "luar"
STALE_AFTER = 24 * 3600
_backends: dict[str, LayaBackend] = {}  # loaded models, reused between runs

# The language button: the browser remembers the choice; the first visit follows the browser's language.
# Both run in the page only (no server round trip); changing the hidden language box re-labels the page.
LANG_KEY = "luar-lang"
# the button shows the flag of the language it switches to. Images, because Windows does not draw
# flag emoji; PNG, because Gradio serves SVG files only as downloads (an SVG can carry scripts).
# The .svg files next to them are the sources.
FLAGS = {"en": Path(__file__).parent / "assets" / "flag-br.png",
         "pt": Path(__file__).parent / "assets" / "flag-gb.png"}
# Gradio's own words ("Drop File Here", the footer, number formats) follow the browser's language;
# its page module exports changeLocale, so the button switches those too. Same module URL = same
# instance, nothing is downloaded. If a Gradio update renames it, only Gradio's words stay as they were.
_GRADIO_LOCALE_JS = """
  document.documentElement.dataset.luarLang = LANG;  // Gradio's upload box and toasts, see gradio_words_css()
  const ARIA = %s;
  document.querySelectorAll('[data-testid="upload-text"]').forEach(
    e => e.closest("button") && e.closest("button").setAttribute("aria-label", ARIA[LANG]));
  try {
    const urls = [...performance.getEntriesByType("resource").map(e => e.name),
                  ...[...document.querySelectorAll("script[src], link[href]")].map(e => e.src || e.href)];
    const core = urls.find(u => /\\/assets\\/core-[\\w-]+\\.js$/.test(u));
    if (core) import(core).then(m => m.changeLocale && m.changeLocale(LANG === "pt" ? "pt-BR" : "en"))
                          .catch(() => {});
  } catch (e) {}
""" % json.dumps({lang: TEXTS[lang]["upload_aria"] for lang in TEXTS}, ensure_ascii=False)


def _css_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def gradio_words_css() -> str:
    """Two of Gradio's own texts do not follow the language button: the upload box ("Drop File Here -
    or - Click to Upload" is written once, in the browser's language) and the toast titles (always
    the English type name, whatever title is passed). LUAR hides those words and writes its own;
    until the page sets data-luar-lang (a moment after loading), Gradio's words show."""
    on = "html[data-luar-lang]"
    rules = [
        f'{on} [data-testid="upload-text"] {{ font-size: 0 !important; }}',
        f'{on} [data-testid="upload-text"] .or {{ display: none; }}',
        f'{on} [data-testid="upload-text"]::after {{ white-space: pre; text-align: center; line-height: 1.6; '
        'font-size: var(--text-lg); }',
        f"{on} .toast-title {{ font-size: 0 !important; }}",
        f"{on} .toast-title::before {{ font-size: 16px; line-height: 22.4px; }}",
    ]
    for lang, texts in TEXTS.items():
        # "\A " is a line break; the space ends the escape (else "\AC" of "Click" is one hex code)
        words = "\\A ".join(_css_text(texts[k]) for k in ("upload_drop", "upload_or", "upload_click"))
        rules.append(f'html[data-luar-lang="{lang}"] [data-testid="upload-text"]::after {{ content: "{words}"; }}')
        for kind in ("error", "warning", "info"):
            rules.append(f'html[data-luar-lang="{lang}"] .toast-title.{kind}::before '
                         f'{{ content: "{_css_text(texts["title_" + kind])}"; }}')
    return "\n".join(rules) + "\n"


LOAD_LANG_JS = f"""() => {{
  let LANG = null;
  try {{ LANG = localStorage.getItem("{LANG_KEY}"); }} catch (e) {{}}
  LANG = (LANG || navigator.language || "en").toLowerCase().startsWith("pt") ? "pt" : "en";
  {_GRADIO_LOCALE_JS}
  return LANG;
}}"""
TOGGLE_LANG_JS = f"""(lang) => {{
  const LANG = lang === "pt" ? "en" : "pt";
  try {{ localStorage.setItem("{LANG_KEY}", LANG); }} catch (e) {{}}
  {_GRADIO_LOCALE_JS}
  return LANG;
}}"""

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
/* header: language button on the left, title centered on the page, actions on the right of the same line */
#luar-header { display: grid !important; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px; }
#luar-lang { grid-column: 1; justify-self: start; flex: 0 0 auto !important; width: auto !important;
  min-width: 0 !important; min-height: 40px; padding: 0 14px; white-space: nowrap; }
#luar-lang img { width: auto !important; height: 14px !important; max-width: none !important;
  border-radius: 2px; box-shadow: 0 0 0 1px rgb(15 23 42 / 0.15); }
#luar-title { grid-column: 2; }
#luar-header h1 { margin: 0; text-align: center; letter-spacing: 0.08em; }
#luar-actions { grid-column: 3; justify-self: end; display: flex; flex-wrap: nowrap; justify-content: flex-end; gap: 8px; }
#luar-actions > * { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
#luar-actions button { min-height: 40px; padding: 0 16px; white-space: nowrap; }
#luar-tagline { text-align: center; max-width: 72ch; margin: 0 auto; }
@media (max-width: 640px) {
  #luar-header { grid-template-columns: 1fr; }
  #luar-lang, #luar-title, #luar-actions { grid-column: 1; justify-self: center; justify-content: center; }
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

# The five steps: (title key, help key). Each title has an (i) icon at its right; the help box opens
# on hover and on keyboard focus
STEPS = {
    "sheet": ("step_sheet", "tip_sheet"),
    "preview": ("step_preview", "tip_preview"),
    "questions": ("step_questions", "tip_questions"),
    "run": ("step_run", "tip_run"),
    "result": ("step_result", "tip_result"),
}


def heading(title: str, tip: str) -> str:
    """A step title with its help icon (kept by Gradio's Markdown sanitizer: class, tabindex, role)."""
    return (f'### {title} <span class="luar-help" tabindex="0">i'
            f'<span class="luar-tip" role="tooltip">{tip}</span></span>')


def step_heading(step: str) -> str:
    title, tip = STEPS[step]
    return heading(t(title), t(tip))


def question_headers() -> list[str]:
    return t("headers").split("|")


def questions_frame(rows_: list[list[str]]) -> pd.DataFrame:
    """The questions table with its headers in the interface language."""
    return pd.DataFrame(rows_, columns=question_headers())


def no_questions_message() -> str:
    # the sample hint only where the sample buttons and the examples menu exist (a checkout, not PyPI)
    return t("no_questions") + (t("sample_hint") if SAMPLE_QUESTIONS.exists() else "")


def error(message: str) -> gr.Error:
    return gr.Error(message, title=t("title_error"))


def warning(message: str) -> None:
    gr.Warning(message, title=t("title_warning"))


def _questions_to_rows(questions) -> list[list[str]]:
    rows = []
    for q in questions:
        opts = "; ".join(f"{k}: {v}" if v else k for k, v in q.options.items())
        rows.append([q.id, q.type, q.question, opts])
    return rows


def _rows_to_questions(table) -> list:
    # columns by position: the headers depend on the interface language
    df = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
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


def file_status(info: dict | None) -> str:
    """The line under the upload, from what on_file found (kept so it can be shown in either language)."""
    if not info:
        return ""
    cols = t("status_cols_one") if info["columns"] == 1 else t("status_cols_many", n=num(info["columns"]))
    detail = (t("status_csv", sep=info["sep"], encoding=info["encoding"]) if info["kind"] == "csv"
              else t("status_excel", sheet=info["sheet"]))
    status = t("status", name=info["name"], rows=rows(info["rows"]), cols=cols, detail=detail)
    if info["sensitive"]:
        status += "\n\n" + t("status_sensitive", found=describe_sensitive(info["sensitive"]))
    return status


def on_file(file, lang="en"):
    with language(lang):
        hidden = gr.update(visible=False, value=False)
        if file is None:
            return gr.update(choices=[], value=[]), None, "", None, hidden, None
        try:
            df, info = read_table(file)
        except Exception as e:  # unreadable file: tell the user, keep the UI alive
            raise error(t("err_read", error=e)) from e
        if len(df) > MAX_ROWS:
            raise error(t("err_too_many_rows", rows=num(len(df)), max=num(MAX_ROWS)))
        # expected_* columns hold known answers: never offer them as model input
        readable = [c for c in df.columns if not str(c).startswith(EXPECTED_PREFIX)]
        # suggest the column with the longest text on average
        lengths = {c: df[c].astype(str).str.len().mean() for c in readable}
        best = max(lengths, key=lengths.get) if lengths else None
        sensitive = scan_sensitive(build_texts(df, readable)) if readable else None
        found = {
            "name": Path(file).name, "rows": len(df), "columns": len(df.columns), "kind": info.kind,
            "sep": info.sep, "encoding": info.encoding, "sheet": info.sheet,
            "sensitive": dict(sensitive or {}),
        }
        return (
            gr.update(choices=readable, value=[best] if best else []),
            df.head(PREVIEW_ROWS),
            file_status(found),
            file,
            gr.update(visible=bool(sensitive), value=False),
            found,
        )


def on_load_questions(file, lang="en"):
    with language(lang):
        if file is None:
            return gr.update()
        try:
            return questions_frame(_questions_to_rows(load_questions(file)))
        except json.JSONDecodeError as e:
            raise error(t("bad_json", error=e)) from e
        except QuestionError as e:
            raise error(str(e)) from e


def on_save_questions(table, lang="en"):
    with language(lang):
        try:
            questions = _rows_to_questions(table)
        except QuestionError as e:
            raise error(str(e)) from e
        path = work_dir() / "questions.json"
        path.write_text(dump_questions(questions), encoding="utf-8")
        return path


# id: (name key, data file, questions file)
EXAMPLE_SETS = {
    "reviews": ("ex_reviews", "reviews.csv", "reviews_questions.json"),
    "severity": ("ex_severity", "reviews.csv", "reviews_severity_question.json"),
    "avaliacoes": ("ex_avaliacoes", "avaliacoes.csv", "avaliacoes_perguntas.json"),
    "sample": ("ex_sample", "amostra_teste.csv", "amostra_teste_perguntas.json"),
}


def example_choices() -> list[tuple[str, str]]:
    return [(t(name), key) for key, (name, _, _) in EXAMPLE_SETS.items()]


def on_example(key, lang="en"):
    with language(lang):
        _, data, questions = EXAMPLE_SETS[key]
        rows_ = _questions_to_rows(load_questions(EXAMPLES / questions))
        return str(EXAMPLES / data), questions_frame(rows_)


CHECKPOINT_NAMES = {"auto": "ckpt_auto", "multilingual": "ckpt_multilingual", "english": "ckpt_english"}


def checkpoint_choices() -> list[tuple[str, str]]:
    return [(t(name), value) for value, name in CHECKPOINT_NAMES.items()]


def _backend(checkpoint: str, texts: list[str], questions) -> LayaBackend:
    resolved = pick_checkpoint(texts, questions) if checkpoint == "auto" else checkpoint
    if resolved not in _backends:
        _backends[resolved] = LayaBackend(checkpoint=resolved)
    backend = _backends[resolved]
    variant = t(CHECKPOINT_NAMES[resolved]) if resolved in CHECKPOINT_NAMES else resolved
    backend.name = f"laya ({variant}{', ' + t('engine_auto') if checkpoint == 'auto' else ''})"
    return backend


def on_run(file, columns, table, threshold, checkpoint, allow_sensitive, lang="en", progress=gr.Progress()):
    with language(lang):
        if not file:
            raise error(t("err_no_file"))
        if not columns:
            raise error(t("err_no_columns"))
        try:
            questions = _rows_to_questions(table)
        except QuestionError as e:
            raise error(str(e)) from e
        if any(q.type in EXPERIMENTAL_TYPES for q in questions):
            warning(t("warn_score"))

        df, info = read_table(file)
        # before loading the model: personal data is only read with the user's confirmation
        sensitive = scan_sensitive(build_texts(df, columns))
        if sensitive and not allow_sensitive:
            raise error(t("err_sensitive_ui", found=describe_sensitive(sensitive)))
        texts = df[columns].astype(str).agg(" ".join, axis=1).tolist()
        progress(0, desc=t("progress_loading"))
        try:
            backend = _backend(checkpoint, texts, questions)
            # the progress callback runs in this thread, inside the language block
            result = classify(
                df, columns, questions, backend, threshold,
                progress=lambda done, total: progress(done / total, desc=t("progress_rows", done=num(done),
                                                                           total=num(total))),
                allow_sensitive=bool(allow_sensitive),
            )
        except (ValueError, BackendError) as e:
            raise error(str(e)) from e
        # uploads live in a temp folder; write the outputs to a fresh one
        save_result(result, info, out_dir=work_dir())
        flagged = (result.table[REVIEW_COL] == "yes").sum()
        gr.Info(t("done", rows=rows(len(result.table)), flagged=num(flagged)), title=t("title_info"))
        if result.manipulation_rows:
            warning(t("warn_manipulation", rows=rows(result.manipulation_rows)))
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
    """The page, labelled in English; the language button (and the first visit, from the browser's
    language) re-labels it through `relabel`."""
    with language("en"):
        return _build()


def _build() -> gr.Blocks:
    # Gradio's upload cache (copies of the user's files): checked hourly, removed after 3 hours
    with gr.Blocks(title="LUAR", analytics_enabled=False, delete_cache=(3600, 3 * 3600)) as demo:
        gr.HTML(background_html(), padding=False, container=False)
        lang = gr.Textbox("en", visible=False)  # "en" or "pt": every event reads the language from here
        readmes = {code: (tab, path) for code, (tab, path) in READMES.items() if path.exists()}
        with gr.Row(elem_id="luar-header"):
            lang_btn = gr.Button(t("lang_button"), icon=str(FLAGS["en"]), variant="secondary", size="md",
                                 elem_id="luar-lang")
            gr.Markdown("# LUAR", elem_id="luar-title")
            with gr.Row(elem_id="luar-actions"):
                readme_btn = gr.Button(t("readme"), variant="secondary", size="md", visible=bool(readmes))
                sample_btns = [
                    gr.DownloadButton(
                        t(key), value=str(path) if path.exists() else None,
                        variant="secondary", size="md", visible=path.exists(),
                    )
                    for key, path in (("sample_csv", SAMPLE_CSV), ("sample_json", SAMPLE_QUESTIONS))
                ]
        tagline = gr.Markdown(t("tagline"), elem_id="luar-tagline")
        with gr.Sidebar(label=t("readme"), open=False, position="right", width="min(760px, 92vw)") as manual:
            with gr.Tabs(selected="en") as readme_tabs:
                for code, (tab, path) in readmes.items():
                    with gr.Tab(tab, id=code):
                        gr.Markdown(readme_markdown(path))
        readme_btn.click(lambda: gr.Sidebar(open=True), None, manual)
        laya_missing = gr.Markdown(t("laya_missing", hint=INSTALL_HINT), visible=not laya_installed())
        source = gr.State()
        file_info = gr.State()  # what on_file found, to show its status line in either language
        headings = {}
        with gr.Row(equal_height=False):
            with gr.Column(scale=1, elem_classes="luar-step"):
                headings["sheet"] = gr.Markdown(step_heading("sheet"))
                upload = gr.File(label=t("upload"), file_types=[".csv", ".xlsx", ".xlsm", ".txt"])
                status = gr.Markdown()
                columns = gr.CheckboxGroup(label=t("columns"), choices=[])
                allow_sensitive = gr.Checkbox(label=t("allow_sensitive"), value=False, visible=False)
                example = gr.Dropdown(
                    example_choices(), label=t("example"), value=None,
                    visible=EXAMPLES.exists(),  # examples ship with the repo, not the wheel
                )
            with gr.Column(scale=2, elem_classes="luar-step"):
                headings["preview"] = gr.Markdown(step_heading("preview"))
                preview = gr.Dataframe(interactive=False, max_height=260, wrap=True)

        with gr.Column(elem_classes="luar-step"):
            headings["questions"] = gr.Markdown(step_heading("questions"))
            questions = gr.Dataframe(
                headers=question_headers(),
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
            question_help = gr.Markdown(t("question_help"))
        with gr.Row():
            q_upload = gr.File(label=t("load_questions"), file_types=[".json"], scale=1)
            q_save = gr.Button(t("save_questions"), variant="secondary", scale=0)
            q_file = gr.File(label=t("questions_file"), interactive=False, scale=1)

        headings["run"] = gr.Markdown(step_heading("run"), elem_classes="luar-step")
        with gr.Row():
            threshold = gr.Slider(
                0.5, 0.95, value=DEFAULT_THRESHOLD, step=0.05, label=t("threshold"), info=t("threshold_info"),
            )
            checkpoint = gr.Dropdown(
                checkpoint_choices(), value="auto", label=t("checkpoint"), info=t("checkpoint_info"),
            )
        run = gr.Button(t("run"), variant="primary", size="lg", elem_id="luar-run")

        headings["result"] = gr.Markdown(step_heading("result"), elem_classes="luar-step")
        downloads = gr.File(label=t("downloads"), file_count="multiple", interactive=False)
        with gr.Tabs():
            with gr.Tab(t("tab_summary")) as summary_tab:
                summary = gr.Markdown()
            with gr.Tab(t("tab_table")) as table_tab:
                result = gr.Dataframe(interactive=False, max_height=420, wrap=True)

        def relabel(code, table, info, example_value, checkpoint_value):
            """Every text on the page in the chosen language. Results already shown (summary, table,
            files) stay as they were made: they are the output of that run."""
            code = normalize(code)
            with language(code):
                table = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
                return [
                    gr.update(value=t("lang_button"), icon=str(FLAGS[code])),
                    gr.update(value=t("readme")),
                    *[gr.update(label=t(key)) for key in ("sample_csv", "sample_json")],
                    gr.update(value=t("tagline")),
                    gr.update(label=t("readme")),
                    gr.update(selected=code if code in readmes else next(iter(readmes), None)),
                    gr.update(value=t("laya_missing", hint=INSTALL_HINT)),
                    *[gr.update(value=step_heading(step)) for step in headings],
                    gr.update(label=t("upload")),
                    gr.update(value=file_status(info)),
                    gr.update(label=t("columns")),
                    gr.update(label=t("allow_sensitive")),
                    gr.update(choices=example_choices(), value=example_value, label=t("example")),
                    questions_frame(table.iloc[:, :4].fillna("").values.tolist()),
                    gr.update(value=t("question_help")),
                    gr.update(label=t("load_questions")),
                    gr.update(value=t("save_questions")),
                    gr.update(label=t("questions_file")),
                    gr.update(label=t("threshold"), info=t("threshold_info")),
                    gr.update(choices=checkpoint_choices(), value=checkpoint_value, label=t("checkpoint"),
                              info=t("checkpoint_info")),
                    gr.update(value=t("run")),
                    gr.update(label=t("downloads")),
                    gr.update(label=t("tab_summary")),
                    gr.update(label=t("tab_table")),
                ]

        relabelled = [
            lang_btn, readme_btn, *sample_btns, tagline, manual, readme_tabs, laya_missing,
            *headings.values(), upload, status, columns, allow_sensitive, example, questions, question_help,
            q_upload, q_save, q_file, threshold, checkpoint, run, downloads, summary_tab, table_tab,
        ]
        # the language box changes in the page (button or first visit); the page is then re-labelled
        lang.change(relabel, [lang, questions, file_info, example, checkpoint], relabelled)
        lang_btn.click(None, lang, lang, js=TOGGLE_LANG_JS)
        demo.load(None, None, lang, js=LOAD_LANG_JS)

        upload.change(on_file, [upload, lang], [columns, preview, status, source, allow_sensitive, file_info])
        # .input, not .change: re-labelling the menu must not load the example again
        example.input(on_example, [example, lang], [upload, questions])
        q_upload.change(on_load_questions, [q_upload, lang], questions)
        q_save.click(on_save_questions, [questions, lang], q_file)
        run.click(
            on_run, [source, columns, questions, threshold, checkpoint, allow_sensitive, lang],
            [result, summary, downloads],
        )
    return demo


def launch(port: int = 7860, share: bool = False, open_browser: bool = True) -> None:
    clean_work_dir()                                   # leftovers older than a day (e.g. after a crash)
    atexit.register(clean_work_dir, all_of_it=True)    # this session's copies, when LUAR closes
    build().launch(
        server_name="127.0.0.1", server_port=port, share=share, inbrowser=open_browser,
        theme=THEME, css=CSS + gradio_words_css(), allowed_paths=[str(IMAGES)], max_file_size=MAX_UPLOAD,
    )


if __name__ == "__main__":
    launch()
