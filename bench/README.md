# LUAR evaluation on public data

How well does LUAR label real text? This folder holds the script and the results of a test on two
public datasets labeled by people. The user manual summarizes them in
[section 8](../README.md#8-how-accurate-is-laya).

## Setup

- **Samples:** 300 texts per dataset, balanced by label, drawn with a fixed seed (`20261002`).
- **How the engine is run:** exactly as a user would, with `run_file` on a CSV with `expected_*`
  columns and the default confidence threshold (0.7).
- **Machine:** Windows laptop, Intel Iris Xe (no dedicated GPU), 16 GB RAM.
- **Version:** Laya 0.3.21 with `auto` checkpoint.

| Dataset | Language | Questions | Labels from |
|---|---|---|---|
| [AG News](https://huggingface.co/datasets/fancyzhx/ag_news) (test split) | English | `topic` (choice: world, sports, business, sci/tech) | dataset authors |
| [B2W-Reviews01](https://github.com/americanas-tech/b2w-reviews01) (Americanas.com, 2018; CC BY-NC-SA 4.0, B2W Digital) | Portuguese | `recomenda` (noul), `sentimento` (choice, derived from stars: 1–2 negative, 3 neutral, 4–5 positive), `estrelas` (score, 1–5) | the customers themselves |

The B2W labels are the ratings the customers gave, which do not always match what they wrote, so
that dataset is a hard and noisy test. Sampling is balanced by stars (60 per star), which makes
the neutral and two-star cases more frequent than in the raw data.

## Results

| Dataset | Question | Type | Accuracy |
|---|---|---|---:|
| AG News | topic | choice | **93%** |
| B2W | recomenda | noul | 70% |
| B2W | sentimento | choice | 68% |
| B2W | estrelas | score | 26% (60% within ±1) |

| | |
|---|---|
| Time per row | 1.0 s (AG News, 1 question) · 1.28 s (B2W, 3 questions) |
| Accuracy when confidence ≥ 0.7 (share of rows) | AG News 98% (84%) · B2W 72–75% (82–83%) |
| Expected calibration error (ECE) | AG News 0.085 · B2W 0.12–0.18 |

Notable findings:

- **Laya on AG News (93%) is close to the 94.7% its authors report**, so LUAR's pipeline does not lose
  accuracy.
- **Sentiment:** Laya gets negative (87%) and positive (82%) right, but chose `neutral` only 3 times
  out of 60.
- **`score` is weak:** the exact star rating was right 26% of the time (chance is 20%). Its confidence
  was below 0.7 for 96% of the rows, which is why `score` questions no longer mark rows for review.

Full numbers, including confusion matrices: [`results/laya.json`](results/laya.json).

## Running it yourself

```bash
pip install -e ".[all]" pyarrow
python bench/evaluate.py --data-dir <a folder for the downloads> --rows 300
```

The script downloads the two datasets (49 MB + 1.2 MB) into `--data-dir`. They are not included in
this repository because of their licenses. Results are written to `bench/results/` after each dataset.
