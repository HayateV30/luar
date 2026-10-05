# Contributing to LUAR

Thanks for helping. This page is for people who want to change LUAR's code; the user manual is the
[README](README.md).

## Setup

```bash
git clone https://github.com/HayateV30/luar.git
cd luar
pip install -e ".[all,dev]"
```

## Tests

```bash
pytest              # fast tests: no model, no server (about 5 s)
pytest -m slow -s   # real models on the bundled examples
```

The slow tests run Laya (downloads the weights on first use, or run `luar download` before). They
check accuracy on the files in `examples/`, which carry `expected_<id>` answer-key columns, and that
a downloaded model runs with the network blocked.

## Layout

```
src/luar/
  questions.py   question model and validation (choice / score / noul, up to 20 options)
  tables.py      CSV/XLSX reading (separator and encoding sniffing) and never-overwrite writing
  engine.py      runs the questions over rows, confidence threshold, needs_review, accuracy
  report.py      Markdown summary
  safety.py      manipulation alerts and personal-data checks on the spreadsheet text
  backends/      the decision engines
    base.py            Answer, Backend protocol, BackendError
    laya_backend.py    Laya (a required dependency), loaded from the local cache once downloaded
  cli.py         `luar run`, `luar columns`, `luar download`, `luar ui`
  app.py         Gradio web interface (luar[ui])
examples/        sample data and questions, with expected_* columns
docs/images/     screenshots used in the README
```

## Adding an engine

An engine is any object with a `name` and a `decide` method:

```python
def decide(self, texts: list[str], questions: list[Question], progress=None) -> list[dict[str, Answer]]:
    """One {question_id: Answer(value, confidence)} per text, in the same order."""
```

- `value` must be one of the question's option labels (`yes`/`no` for `noul`), or `None` if the
  engine could not answer.
- `confidence` should be a real probability between 0 and 1, not a number the model writes about
  itself. Rows below the threshold are marked `needs_review`, so a made-up confidence defeats the
  point.
- Raise a `BackendError` subclass with a message that says how to fix the problem (install
  something, download a model…). The CLI and the web interface show that message as is.
- Register it in `backends/__init__.py` (`make_backend`) and expose it in `cli.py` and `app.py`.

## How Laya works

**Laya** answers typed questions in one forward pass and returns probabilities for every option.
`auto` picks the `english` checkpoint when the questions and at least 80% of the sampled rows are
English, and `multilingual` otherwise; on English text the English checkpoint was clearly more
accurate in our tests.

LUAR makes no outside connection once installed: the interface turns off Gradio's telemetry and
serves the README screenshots from `docs/images/`, and Laya is loaded from the Hugging Face cache
when it is there. Keep it that way: `tests/test_offline.py` fails any connection to another host.

## Releasing

1. Bump `version` in `pyproject.toml` and `__version__` in `src/luar/__init__.py`.
2. Commit, push, and create a GitHub release with a `vX.Y.Z` tag.
3. The `Publish to PyPI` workflow runs the fast tests, builds the package and uploads it using
   PyPI Trusted Publishing (no token involved).

## Security

The threat model and the protections are described in the user manual (section 10, "Security and
privacy"). When you change code, keep these properties:

- Text from a spreadsheet is data, never code or markup: write it to `.xlsx` as text
  (`tables.write_table`) and pass it through `report._md` before it reaches the summary.
- Personal data is only read after the user confirms (`allow_sensitive`); reports give counts, never values.
- Only load model weights that match `WEIGHTS_SHA256` (`backends/laya_backend.verify_weights`).
- Copies of user data go under `app.WORK_DIR` (cleaned on exit), never next to the code.
- `tests/test_safety.py` covers each of these; the manipulation patterns in `safety.py` were checked
  against 600 real texts (no false alarm). Re-run that check (see `bench/`) when you change them.

