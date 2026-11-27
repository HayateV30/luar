# LUAR evaluation on public data

How well does LUAR label real text? This folder holds the script and the results of a test on two
public datasets labeled by people. The user manual summarizes them in
[section 8](../README.md#8-how-accurate-is-laya).

## Setup

- **Samples:** 300 texts per dataset, balanced by label, drawn with a fixed seed (`20261002`).
- **How the engine is run:** exactly as a user would, with `run_file` on a CSV with `expected_*`
  columns and the default confidence threshold (0.7).
- **Machine:** Windows laptop, Intel Iris Xe (no dedicated GPU), 16 GB RAM.
- **Version:** Laya 0.5.6 with `auto` checkpoint. Laya 0.4.22 and 0.3.21 gave the same answers on these samples (0.5.6 was about 10–20% faster per row).

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
| B2W | estrelas | score | 33% (68% within ±1) |

| | |
|---|---|
| Time per row | 0.63 s (AG News, 1 question) · 1.09 s (B2W, 3 questions) |
| Accuracy when confidence ≥ 0.7 (share of rows) | AG News 98% (84%) · B2W `noul` and `choice` 72–75% (82–83%), `score` 44% (44%) |
| Expected calibration error (ECE) | AG News 0.085 · B2W 0.18 (`noul`, `choice`), 0.32 (`score`) |

Notable findings:

- **Laya on AG News (93%) is close to the 94.7% its authors report**, so LUAR's pipeline does not lose
  accuracy.
- **Sentiment:** Laya gets negative (87%) and positive (82%) right, but chose `neutral` only 3 times
  out of 60.
- **`score` is weak:** the exact star rating was right 33% of the time (chance is 20%). Its confidence
  is not reliable (44% right at 0.7 or more, 24% below), which is why `score`
  questions do not mark rows for review.

Full numbers, including confusion matrices: [`results/laya.json`](results/laya.json).

## THX-01, the optional engine

Same samples, questions and machine, with `thx01` 1.0.0 and the weights at revision `b323afc`:

| Dataset | Question | Type | Accuracy | ECE | Accuracy at confidence ≥ 0.7 (share of rows) |
|---|---|---|---:|---:|---|
| AG News | topic | choice | 91% | 0.027 | 93% (95%) |
| B2W | recomenda | noul | 82% | 0.033 | 89% (79%) |
| B2W | sentimento | choice | 72% (neutral: 10 of 60) | 0.025 | 82% (67%) |
| B2W | estrelas | score | 45% (93% within ±1) | 0.17 | 59% (25%) |

- **Time per row, model loading included:** 0.34 s (AG News), 1.06 s (B2W). Without loading, on B2W:
  THX-01 0.62 s, Laya 1.16 s.
- **Peak memory** of the process (Windows peak working set) on 300 B2W rows: THX-01 4.5 GB, reached
  while loading; Laya (multilingual) 2.5 GB. Measured once, each engine in its own process.
- **Rows marked for review:** AG News 5%, B2W 44%.
- With 300 rows, the differences from Laya in AG News and sentiment may be chance.
- LUAR calls `predict_batch`. Its answers were identical to `thx01`'s `decide` on all 1,200 answers
  (confidence differs by at most 0.0001).

Full numbers: [`results/thx.json`](results/thx.json).

## Reading PDFs and images

`ocr_documents.py` draws ten made-up Portuguese documents with known text (an invoice, an all-caps
receipt, a complaint form, a contract, a prescription, a table, a skewed and noisy photo, a 100-dpi JPEG
scan, a typewritten letter with a bank slip number, an image-only PDF) and reads them with `read_table`,
as LUAR does. No real document is used.

```bash
python bench/ocr_documents.py --data-dir <a folder> --readers tesseract ocria-nano
```

| Reader | Character error rate | Accented words | Numbers | s/page |
|---|---:|---|---|---:|
| Tesseract (Portuguese, `tessdata_best` at `9ddc24e`) | 2.6% | 66/66 | 51/51 | 0.55 |
| OCRia-nano 1.0.0 | 0.4% | 66/66 | 50/51 | 0.50 |

LiteParse 2.21.3, same laptop. Tesseract's error comes from the photo (9.4%), the low-resolution scan
(12.4%) and the table (3.2%); on the other seven it is 0–0.7%. Per document:
[`results/ocr.md`](results/ocr.md).

## Running it yourself

```bash
pip install -e ".[all]" pyarrow
python bench/evaluate.py --data-dir <a folder for the downloads> --rows 300
python bench/evaluate.py --data-dir <a folder for the downloads> --rows 300 --engines thx
```

The script downloads the two datasets (49 MB + 1.2 MB) into `--data-dir`. They are not included in
this repository because of their licenses. Results are written to `bench/results/` after each dataset.
