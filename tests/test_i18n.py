"""Interface texts: both languages complete and consistent; English stays the default."""
import string

import pytest

from luar.i18n import TEXTS, dec, language, normalize, num, rows, t
from luar.questions import QuestionError, parse_questions
from luar.safety import describe_sensitive


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_both_languages_have_the_same_keys_and_placeholders():
    en, pt = TEXTS["en"], TEXTS["pt"]
    assert set(en) == set(pt)
    for key in en:
        assert _fields(en[key]) == _fields(pt[key]), key


def test_every_portuguese_text_is_translated():
    # the same text in both languages is only fine for names and codes
    same = {k for k in TEXTS["en"] if TEXTS["en"][k] == TEXTS["pt"][k]}
    assert same <= {"ckpt_auto", "kind_CPF", "kind_CNPJ", "kind_e-mail", "status"}


def test_english_is_the_default_and_the_context_is_restored():
    assert t("run") == "Run"
    with language("pt-BR"):
        assert t("run") == "Executar"
        with language("en"):
            assert t("run") == "Run"
        assert t("run") == "Executar"
    assert t("run") == "Run"


@pytest.mark.parametrize("raw, code", [("pt", "pt"), ("pt-BR", "pt"), ("PT_pt", "pt"), ("en-US", "en"),
                                       ("es", "en"), ("", "en"), (None, "en")])
def test_normalize(raw, code):
    assert normalize(raw) == code


def test_numbers_and_plurals():
    assert (num(20000), dec(0.7), rows(1), rows(3)) == ("20,000", "0.70", "1 row", "3 rows")
    with language("pt"):
        assert (num(20000), dec(0.7), rows(1), rows(3)) == ("20.000", "0,70", "1 linha", "3 linhas")


def test_core_errors_follow_the_language():
    with language("pt"), pytest.raises(QuestionError, match="Pergunta 'x': perguntas de sim/não"):
        parse_questions([{"id": "x", "type": "noul", "question": "Sim?", "options": "a; b"}])
    with pytest.raises(QuestionError, match="yes/no \\(noul\\) questions take no options"):
        parse_questions([{"id": "x", "type": "noul", "question": "Yes?", "options": "a; b"}])


def test_personal_data_description():
    counts = {"e-mail": 1, "card number": 3}
    assert describe_sensitive(counts) == "card number in 3 rows, e-mail in 1 row"
    with language("pt"):
        assert describe_sensitive(counts) == "número de cartão em 3 linhas, e-mail em 1 linha"
