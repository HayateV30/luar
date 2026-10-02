# 🌙 LUAR: Local Utility for Automated Reviews

Drop a spreadsheet, say what you want to know about each row, and get back a copy with the answers
plus a Markdown summary. Everything runs **on your own computer**: no API keys, no data sent anywhere.

LUAR is a thin, friendly layer over [Laya](https://huggingface.co/convaiinnovations/laya), an open,
local decision model in the style of Jev. Instead of generating text, Laya answers *structured*
questions about a piece of text, with a confidence for each answer.

*[Leia em português](README.pt-BR.md)*

## What it does

| You give it | You get back |
|---|---|
| A `.csv` or `.xlsx` file | `<name>_luar.csv/.xlsx`: a **copy** with new columns (your original is never touched) |
| The column(s) to read | For each question: `<id>` (the answer) and `<id>_confidence` (0–1) |
| Your questions | `needs_review` = `yes` when any answer is below the confidence threshold, and `review_reasons` |
| | `<name>_luar_summary.md`: counts per answer, rows to review, accuracy (see below) |

### Question types

| Type | Answers | Example |
|---|---|---|
| `choice` | one of your options (2–20) | *What is this review about?* delivery / product / support / price |
| `noul` | `yes` or `no` | *Does the customer ask for their money back?* |
| `score` ⚠️ | a level on an ordered scale | *How severe is it?* low / medium / high |

> ⚠️ **`score` is experimental.** In our tests it was unreliable without fine-tuning: answers drifted to
> one end of the scale. Prefer `choice` or `noul`, or check `score` results by hand.

## Install

Requires Python 3.10+. The first run downloads the Laya model (a few hundred MB) from Hugging Face.

```bash
git clone https://github.com/<you>/luar.git
cd luar
pip install -e ".[ui]"
```

## Use it

### Web interface

```bash
luar ui
```

This opens `http://127.0.0.1:7860` in your browser (local only). Then:

1. Drop your file and tick the column(s) the model should read.
2. Fill in the questions table (or load a questions `.json`, or pick a bundled example).
3. Click **Run** and download the result copy and the summary.

### Command line

```bash
luar columns examples/reviews.csv
luar run examples/reviews.csv -q examples/reviews_questions.json -c review
```

Options: `-t/--threshold` (default `0.7`), `-o/--out-dir`, `--sheet` (Excel), `--checkpoint`
(`auto`, `multilingual`, `english`), `--device` (`cpu`/`cuda`).

### Python

```python
from luar import load_questions, run_file
from luar.backends import LayaBackend

result = run_file("data.csv", load_questions("questions.json"), ["text"], LayaBackend())
print(result.table_path, result.summary_path)
```

## Questions file

```json
[
  {
    "id": "topic",
    "type": "choice",
    "question": "What is this review mainly about?",
    "options": {
      "delivery": "shipping, delays, courier, package condition",
      "product": "quality, defects, how the item works"
    }
  },
  {"id": "sentiment", "type": "choice", "question": "Overall sentiment?", "options": ["positive", "neutral", "negative"]},
  {"id": "wants_refund", "type": "noul", "question": "Does the customer explicitly ask for their money back?"}
]
```

- `id`: letters, digits and `_`; becomes the column name.
- `options`: a list of labels, or `{label: description}`. Descriptions help the model a lot.
- Laya's native format (`{"id": {"type", "instructions", "criteria"}}`) is accepted too.

## Check before you trust it

A model can be confidently wrong, so measure it on your own data before using the results:

1. Label 20–50 rows by hand in columns named **`expected_<id>`** (e.g. `expected_topic`).
   For `noul`, `yes/no`, `sim/não`, `true/false` and `1/0` all work.
2. Run LUAR. The summary shows **accuracy against `expected_<id>`** for each question.
3. Adjust the questions (wording, option descriptions) or the threshold until you are happy.

`expected_*` columns are never offered to the model as input.

## Tips from testing

- **Language:** `auto` picks the `english` model when the file is in English and `multilingual`
  otherwise. On English text, the English model was clearly better; on Portuguese, the multilingual one.
- **Describe options.** `"price": "cost, value for money, charges"` beats a bare `"price"`.
- **Option order can change answers.** Put the most specific options first and test with `expected_*`.
- **Keep to about 20 options per question.** Split larger lists into two questions.
- **Confidence is a hint, not a guarantee.** Use `needs_review` to decide where a human should look.

## Architecture

```
src/luar/
  questions.py   question model + validation (choice / score / noul)
  tables.py      CSV/XLSX reading (separator & encoding sniffing) and never-overwrite writing
  engine.py      runs the questions over rows, confidence threshold, accuracy
  report.py      Markdown summary
  backends/      the "socket" for decision engines; Laya is the first one
  cli.py, app.py command line and Gradio interface
```

A new engine (for example a local LLM through an OpenAI-compatible endpoint) only needs to implement
`Backend.decide(texts, questions) -> [{question_id: Answer(value, confidence)}]`.

## Development

```bash
pip install -e ".[ui,dev]"
pytest              # fast tests, no model needed
pytest -m slow -s   # runs the real Laya model on the examples
```

## License

MIT for LUAR's code. Laya (the package and the model weights) is a separate project with its own
license; check its [model card](https://huggingface.co/convaiinnovations/laya) before redistributing it.
