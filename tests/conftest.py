from pathlib import Path

import pytest

from luar.backends.base import Answer

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class KeywordBackend:
    """Deterministic stand-in for a model: picks the first option whose label
    appears in the text; low confidence when nothing matches."""

    name = "keyword (test)"

    def __init__(self):
        self.calls = 0

    def decide(self, texts, questions, progress=None):
        self.calls += 1
        out = []
        for i, text in enumerate(texts):
            low = text.lower()
            row = {}
            for q in questions:
                if q.type == "noul":
                    hit = any(w in low for w in ("refund", "money back", "reembolso", "dinheiro de volta"))
                    row[q.id] = Answer("yes" if hit else "no", 0.95 if hit else 0.8)
                else:
                    label = next((o for o in q.options if o in low), None)
                    row[q.id] = Answer(label or list(q.options)[0], 0.9 if label else 0.3)
            out.append(row)
            if progress:
                progress(i + 1, len(texts))
        return out


@pytest.fixture
def backend():
    return KeywordBackend()
