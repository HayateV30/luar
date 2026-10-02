import pandas as pd
import pytest

from luar.cli import main as cli_main
from luar.engine import accuracy, build_texts, classify, run_file
from luar.questions import load_questions, parse_questions
from luar.report import render_summary

from .conftest import EXAMPLES

QUESTIONS = parse_questions([
    {"id": "color", "type": "choice", "question": "Which color?", "options": ["red", "blue"]},
    {"id": "refund", "type": "noul", "question": "Wants a refund?"},
])


def test_build_texts_single_and_multiple_columns():
    df = pd.DataFrame({"title": ["A", ""], "body": ["text one", "text two"]})
    assert build_texts(df, ["body"]) == ["text one", "text two"]
    assert build_texts(df, ["title", "body"]) == ["title: A\nbody: text one", "body: text two"]
    with pytest.raises(ValueError, match="not found"):
        build_texts(df, ["nope"])


def test_classify_adds_columns_and_flags_low_confidence(backend):
    df = pd.DataFrame({"t": ["the red one, I want a refund", "something green", ""]})
    res = classify(df, ["t"], QUESTIONS, backend, threshold=0.7)
    out = res.table
    assert list(out.columns) == ["t", "color", "color_confidence", "refund", "refund_confidence",
                                 "needs_review", "review_reasons"]
    assert out.loc[0, "color"] == "red" and out.loc[0, "refund"] == "yes"
    assert out.loc[0, "needs_review"] == ""
    assert out.loc[1, "needs_review"] == "yes" and out.loc[1, "review_reasons"] == "color"
    # empty rows are not sent to the model
    assert pd.isna(out.loc[2, "color"]) and out.loc[2, "review_reasons"] == "empty text"
    assert df.columns.tolist() == ["t"]  # input untouched


def test_refuses_to_clobber_existing_columns(backend):
    df = pd.DataFrame({"t": ["x"], "color": ["old"]})
    with pytest.raises(ValueError, match="already has column"):
        classify(df, ["t"], QUESTIONS, backend)


def test_accuracy_against_expected_columns(backend):
    df = pd.DataFrame({
        "t": ["red, refund please", "blue thing", "red"],
        "expected_color": ["red", "Blue ", ""],     # blank expected values are skipped
        "expected_refund": ["Sim", "no", "yes"],    # yes/no synonyms are normalized
    })
    res = classify(df, ["t"], QUESTIONS, backend)
    assert accuracy(res, QUESTIONS[0]) == (2, 2)
    assert accuracy(res, QUESTIONS[1]) == (2, 3)


def test_summary_mentions_distribution_review_and_experimental(backend):
    qs = parse_questions([
        {"id": "level", "type": "score", "question": "How bad?", "options": ["low", "high"]},
    ])
    df = pd.DataFrame({"t": ["high", "meh | pipe\nnewline"]})
    md = render_summary(classify(df, ["t"], qs, backend))
    assert "## level (score)" in md and "Experimental" in md
    assert "| high | 1 | 50% |" in md
    # spreadsheet row 3 = second data row; pipes and newlines made table-safe
    assert "| 3 | level | meh \\| pipe newline |" in md


def test_run_file_examples_end_to_end(tmp_path, backend):
    qs = load_questions(EXAMPLES / "avaliacoes_perguntas.json")
    res = run_file(EXAMPLES / "avaliacoes.csv", qs, ["avaliacao"], backend, out_dir=tmp_path)
    assert res.table_path.name == "avaliacoes_luar.csv"
    written = pd.read_csv(res.table_path, sep=";", encoding="utf-8-sig", dtype=str)
    assert {"assunto", "quer_reembolso", "needs_review"} <= set(written.columns)
    summary = res.summary_path.read_text(encoding="utf-8")
    assert "Accuracy against `expected_quer_reembolso`" in summary


def test_cli_columns_and_errors(capsys, tmp_path):
    assert cli_main(["columns", str(EXAMPLES / "reviews.csv")]) == 0
    assert "review: The package arrived" in capsys.readouterr().out
    bad = tmp_path / "q.json"
    bad.write_text('[{"id": "x", "type": "choice", "question": "?", "options": ["a"]}]', encoding="utf-8")
    assert cli_main(["run", str(EXAMPLES / "reviews.csv"), "-q", str(bad), "-c", "review"]) == 2
    assert "at least 2" in capsys.readouterr().err
