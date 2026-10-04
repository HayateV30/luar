"""Web interface helpers (need the `ui` extra)."""
import pytest

from luar.questions import QuestionError, load_questions
from luar.tables import read_table

from .conftest import EXAMPLES

app = pytest.importorskip("luar.app")


def test_the_starting_row_is_not_a_question():
    """The questions table opens with only the type filled in; that row must be ignored."""
    real = ["topic", "choice", "What is it about?", "a; b"]
    assert [q.id for q in app._rows_to_questions([real, ["", "choice", "", ""]])] == ["topic"]
    assert [q.id for q in app._rows_to_questions([["", "noul", "", ""], real])] == ["topic"]


def test_no_questions_explains_what_to_do():
    for table in ([["", "choice", "", ""]], [["", "", "", ""]]):
        with pytest.raises(QuestionError, match="no questions yet"):
            app._rows_to_questions(table)


def test_half_written_row_still_reports_the_missing_id():
    with pytest.raises(QuestionError, match="Invalid question id"):
        app._rows_to_questions([["", "choice", "What is it about?", "a; b"]])


def test_every_example_set_loads_and_matches_its_answer_key():
    for name, (data, questions) in app.EXAMPLE_SETS.items():
        df, _ = read_table(EXAMPLES / data)
        for q in load_questions(EXAMPLES / questions):
            assert f"expected_{q.id}" in df.columns, f"{name}: no expected_{q.id}"
        file, rows = app.on_example(name)
        assert [r[0] for r in rows] == [q.id for q in load_questions(EXAMPLES / questions)]
