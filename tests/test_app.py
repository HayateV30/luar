"""Web interface helpers (need the `ui` extra)."""
import pandas as pd
import pytest

from luar.questions import QuestionError, load_questions
from luar.tables import read_table

from .conftest import EXAMPLES

app = pytest.importorskip("luar.app")
gr = pytest.importorskip("gradio")


def test_the_starting_row_is_not_a_question():
    """The questions table opens with only the type filled in; that row must be ignored."""
    real = ["topic", "choice", "What is it about?", "a; b"]
    assert [q.id for q in app._rows_to_questions([real, ["", "choice", "", ""]])] == ["topic"]
    assert [q.id for q in app._rows_to_questions([["", "noul", "", ""], real])] == ["topic"]


def test_no_questions_explains_what_to_do():
    for table in ([["", "choice", "", ""]], [["", "", "", ""]]):
        with pytest.raises(QuestionError, match="no questions yet"):
            app._rows_to_questions(table)


def test_no_questions_message_only_mentions_samples_that_exist(monkeypatch, tmp_path):
    with pytest.raises(QuestionError, match="Sample JSON") as repo:
        app._rows_to_questions([["", "choice", "", ""]])
    # an install from PyPI has no examples/ folder: the sample buttons and menu are hidden
    monkeypatch.setattr(app, "SAMPLE_QUESTIONS", tmp_path / "missing.json")
    with pytest.raises(QuestionError) as pypi:
        app._rows_to_questions([["", "choice", "", ""]])
    assert "Load questions (.json)" in str(pypi.value)
    assert "Sample" not in str(pypi.value) and "try an example" not in str(pypi.value)
    assert str(repo.value).startswith(str(pypi.value))


def test_half_written_row_still_reports_the_missing_id():
    with pytest.raises(QuestionError, match="Invalid question id"):
        app._rows_to_questions([["", "choice", "What is it about?", "a; b"]])


def test_sample_buttons_offer_a_matching_pair():
    """Sample CSV and Sample JSON must work together: every question has its answer column."""
    df, _ = read_table(app.SAMPLE_CSV)
    questions = load_questions(app.SAMPLE_QUESTIONS)
    assert questions and all(f"expected_{q.id}" in df.columns for q in questions)


def test_every_example_set_loads_and_matches_its_answer_key():
    for key, (_, data, questions) in app.EXAMPLE_SETS.items():
        df, _ = read_table(EXAMPLES / data)
        for q in load_questions(EXAMPLES / questions):
            assert f"expected_{q.id}" in df.columns, f"{key}: no expected_{q.id}"
        file, table = app.on_example(key)
        assert list(table.iloc[:, 0]) == [q.id for q in load_questions(EXAMPLES / questions)]


def test_background_has_four_aligned_crosses_shrinking_to_the_back():
    import re

    from luar.app import CSS, background_html

    html = background_html()
    assert html.count('class="cross"') == 4 and html.count('class="arm"') == 16
    radii = [int(r) for r in re.findall(r"--R: (\d+)px", html)]
    assert radii == sorted(radii, reverse=True) and len(set(radii)) == 4  # 1st largest, 4th smallest
    assert 'aria-hidden="true"' in html
    # never in the way: behind the page, not clickable, still when the OS asks for less motion
    assert "pointer-events: none" in CSS and "prefers-reduced-motion" in CSS
    assert "body:has(.pending)" in CSS  # paused while the app works


def test_every_step_has_a_help_box():
    from luar.i18n import TEXTS, language

    html = app.step_heading("sheet")
    assert html.startswith("### 1. Spreadsheet ")
    # what Gradio's Markdown sanitizer keeps: class, tabindex (keyboard focus) and role
    assert 'class="luar-help" tabindex="0"' in html and 'role="tooltip"' in html
    assert set(app.STEPS) == {"sheet", "preview", "questions", "run", "result"}
    for lang in TEXTS:
        with language(lang):
            tips = [TEXTS[lang][tip] for _, tip in app.STEPS.values()]
            assert all("<" not in tip and ">" not in tip for tip in tips)
    with language("pt"):
        assert app.step_heading("sheet").startswith("### 1. Planilha ")


# --- language button -------------------------------------------------------------------------

def test_the_page_builds_and_relabels_in_both_languages():
    demo = app.build()
    relabel = next(fn for fn in demo.fns.values() if getattr(fn.fn, "__name__", "") == "relabel")
    table = app.questions_frame([["topic", "choice", "What is it about?", "a; b"]])
    info = {"name": "x.csv", "rows": 3, "columns": 2, "kind": "csv", "sep": ";", "encoding": "utf-8-sig",
            "sheet": None, "sensitive": {"e-mail": 1}}
    pt = relabel.fn("pt", table, info, "sample", "auto")
    en = relabel.fn("en", table, info, "sample", "auto")
    assert len(pt) == len(en) == len(relabel.outputs)
    flat = repr(pt)
    for text in ("English", "Manual", "CSV de exemplo", "1. Planilha", "Executar", "Resumo", "Tabela",
                 "3 linhas, 2 colunas", "e-mail em 1 linha", "Amostra de teste (CSV de exemplo)", "multilíngue"):
        assert text in flat, text
    # the questions keep their content; only the headers change
    questions = next(u for u in pt if isinstance(u, pd.DataFrame))
    assert list(questions.columns) == ["id", "tipo", "pergunta", "opções"]
    assert questions.values.tolist() == [["topic", "choice", "What is it about?", "a; b"]]
    assert "PT-BR" in repr(en) and "flag-br.png" in repr(en) and "flag-gb.png" in repr(pt)
    assert "3 rows, 2 columns" in repr(en)


def test_messages_follow_the_chosen_language():
    with pytest.raises(gr.Error, match="Ainda não há perguntas") as e:
        app.on_save_questions([["", "choice", "", ""]], "pt")
    assert "CSV de exemplo" in str(e.value)
    with pytest.raises(gr.Error, match="Id de pergunta inválido"):
        app.on_save_questions([["", "choice", "Sobre o quê?", "a; b"]], "pt")
    with pytest.raises(gr.Error, match="Primeiro, arraste um arquivo"):
        app.on_run(None, [], [], 0.7, "auto", False, "pt")
    with pytest.raises(gr.Error, match="Drop a CSV or XLSX file first"):
        app.on_run(None, [], [], 0.7, "auto", False, "en")


def test_file_status_in_both_languages():
    file = str(EXAMPLES / "avaliacoes.csv")
    *_, info = app.on_file(file, "pt")
    from luar.i18n import language

    with language("pt"):
        assert "linhas" in app.file_status(info) and "separador" in app.file_status(info)
    assert "rows" in app.file_status(info) and "separator" in app.file_status(info)


def test_flags_ship_as_png():
    # Gradio serves .svg only as a download, so an SVG flag would show as a broken image
    assert {path.suffix for path in app.FLAGS.values()} == {".png"}
    assert all(path.read_bytes().startswith(b"\x89PNG") for path in app.FLAGS.values())


def test_gradio_words_are_written_in_both_languages():
    css = app.gradio_words_css()
    for words in ("Drop File Here\\A - or -\\A Click to Upload",
                  "Arraste o arquivo aqui\\A - ou -\\A Clique para escolher",
                  '"Erro"', '"Atenção"', '"Aviso"', '"Error"', '"Warning"', '"Info"'):
        assert words in css, words
    # only once the page knows the language: before that, Gradio's own words stay visible
    assert all(rule.startswith("html[data-luar-lang") for rule in css.strip().splitlines())


def test_language_scripts_only_store_the_choice_in_the_browser():
    for js in (app.LOAD_LANG_JS, app.TOGGLE_LANG_JS):
        assert "fetch" not in js and "http" not in js
        assert "try" in js  # storage can be blocked (private windows): never break the page
    assert "navigator.language" in app.LOAD_LANG_JS
