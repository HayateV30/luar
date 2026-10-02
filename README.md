# 🌙 LUAR: Local Utility for Automated Reviews

Drop a spreadsheet, say what you want to know about each row, and get back a copy with the answers
plus a Markdown summary. Everything runs **on your own computer**: no cloud, no data sent anywhere.

LUAR has two local engines:

| Engine | What it is | Speed* | When to use |
|---|---|---|---|
| **Laya** (default) | [Laya](https://huggingface.co/convaiinnovations/laya), an open decision model in the style of Jev: it answers *structured* questions with a probability, instead of generating text | ~0.6 s per row | large files, quick passes |
| **LM Studio** | any chat model you run in [LM Studio](https://lmstudio.ai) (tested with Qwen 3.5 4B) | ~5 s per row *per question* | smaller files, when accuracy matters most |

<sub>*On a laptop CPU without a dedicated GPU. Both engines give a real probability as confidence.</sub>

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

> ⚠️ **`score` is experimental.** It was the least reliable type in our tests: 71% (Laya) and 79%
> (LM Studio) agreement with hand labels on the bundled severity example. Prefer `choice` or `noul`,
> or check `score` results by hand.

## Install

Requires Python 3.10+. The first run downloads the Laya model (a few hundred MB) from Hugging Face.

```bash
git clone https://github.com/HayateV30/luar.git
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
3. Pick the engine (Laya or LM Studio), click **Run** and download the result copy and the summary.

### Command line

```bash
luar columns examples/reviews.csv
luar run examples/reviews.csv -q examples/reviews_questions.json -c review
```

Options: `-t/--threshold` (default `0.7`), `-o/--out-dir`, `--sheet` (Excel), `-e/--engine`
(`laya` or `lmstudio`). Laya: `--checkpoint` (`auto`, `multilingual`, `english`), `--device`
(`cpu`/`cuda`). LM Studio: `--model`, `--lmstudio-url`.

### Using LM Studio

1. Install [LM Studio](https://lmstudio.ai) and download a chat model (e.g. `qwen3.5-4b`).
2. Start the server and load the model, in the app (*Developer → Start Server*) or with its CLI:
   ```bash
   lms server start
   lms load qwen3.5-4b
   ```
3. Run with `--engine lmstudio` (or choose **LM Studio** in the web interface).

The server URL defaults to `http://localhost:1234/v1` (change it with `LUAR_LMSTUDIO_URL`). If you turned
on *Require API key* in LM Studio, put the key in the `LMSTUDIO_API_KEY` environment variable, never in
a file you commit. LUAR turns the model's "thinking" off (`reasoning_effort: none`): each answer is a
single token.

### Python

```python
from luar import load_questions, run_file
from luar.backends import make_backend

backend = make_backend("laya")          # or make_backend("lmstudio", model="qwen3.5-4b")
result = run_file("data.csv", load_questions("questions.json"), ["text"], backend)
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

- **Accuracy on the bundled examples:** Laya got 86–100% on `choice`/`noul`; LM Studio with
  Qwen 3.5 4B got 100% on all of them, but took over 20x longer (3 questions: ~14 s vs ~0.6 s per row).
- **Language (Laya):** `auto` picks the `english` model when the file is in English and `multilingual`
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
  backends/      the "socket" for decision engines: Laya and LM Studio
  cli.py, app.py command line and Gradio interface
```

A new engine only needs to implement
`Backend.decide(texts, questions) -> [{question_id: Answer(value, confidence)}]`.

**How the LM Studio engine gets a confidence:** each option is shown with a letter (A, B, C…), the model
answers with one token, and LUAR reads the probability the model gave each letter (`logprobs`),
renormalized over the valid letters. That is the model's actual probability, not a number it writes
about itself.

## Development

```bash
pip install -e ".[ui,dev]"
pytest              # fast tests, no model needed
pytest -m slow -s   # runs the real models on the examples (LM Studio tests skip if the server is off)
```

## License

MIT for LUAR's code. Laya (the package and the model weights) is a separate project with its own
license; check its [model card](https://huggingface.co/convaiinnovations/laya) before redistributing it.
