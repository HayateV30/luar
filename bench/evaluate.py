"""Evaluate LUAR's engines on public, human-labeled datasets.

    python bench/evaluate.py --data-dir <folder> --rows 300

Downloads the datasets into --data-dir (they are not redistributed with LUAR), draws a fixed,
class-balanced sample, runs LUAR exactly as a user would (run_file on a CSV with expected_*
columns) and writes accuracy, timing and calibration to bench/results/.

Datasets
- B2W-Reviews01 (pt-BR product reviews, CC BY-NC-SA 4.0, B2W Digital):
  https://github.com/americanas-tech/b2w-reviews01
- AG News test split (en news topics): https://huggingface.co/datasets/fancyzhx/ag_news
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

from luar.backends import ENGINES, make_backend
from luar.engine import confidence_col, normalize_label, run_file
from luar.questions import parse_questions

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SEED = 20261002

SOURCES = {
    "B2W-Reviews01.csv": "https://raw.githubusercontent.com/americanas-tech/b2w-reviews01/main/B2W-Reviews01.csv",
    "ag_news_test.parquet": "https://huggingface.co/datasets/fancyzhx/ag_news/resolve/main/data/test-00000-of-00001.parquet",
}

B2W_QUESTIONS = parse_questions([
    {"id": "recomenda", "type": "noul",
     "question": "O cliente recomendaria este produto a um amigo?"},
    {"id": "sentimento", "type": "choice",
     "question": "Qual é o sentimento geral do cliente sobre a compra?",
     "options": {"positivo": "satisfeito, elogia, gostou",
                 "neutro": "satisfação mediana, pontos bons e ruins",
                 "negativo": "insatisfeito, reclama, se arrependeu"}},
    {"id": "estrelas", "type": "score",
     "question": "Quantas estrelas, de 1 a 5, o cliente deu ao produto?",
     "options": {"1": "péssimo, muito insatisfeito", "2": "ruim, insatisfeito",
                 "3": "regular, satisfação mediana", "4": "bom, satisfeito",
                 "5": "excelente, muito satisfeito"}},
])

AG_LABELS = {0: "world", 1: "sports", 2: "business", 3: "scitech"}
AG_QUESTIONS = parse_questions([
    {"id": "topic", "type": "choice", "question": "What is this news article about?",
     "options": {"world": "world news, politics, international affairs, conflicts",
                 "sports": "sports, games, athletes, teams, competitions",
                 "business": "business, companies, markets, economy, finance",
                 "scitech": "science and technology, computers, internet, research, space"}},
])


def download(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = data_dir / name
        if not target.exists():
            print(f"downloading {name}…")
            urllib.request.urlretrieve(url, target)


def balanced(df: pd.DataFrame, by: str, rows: int) -> pd.DataFrame:
    groups = df.groupby(by)
    per = rows // groups.ngroups
    parts = [g.sample(n=min(per, len(g)), random_state=SEED) for _, g in groups]
    return pd.concat(parts).sample(frac=1, random_state=SEED).reset_index(drop=True)


def sentiment_from_stars(stars: int) -> str:
    return "negativo" if stars <= 2 else "neutro" if stars == 3 else "positivo"


def b2w_sample(data_dir: Path, rows: int) -> Path:
    df = pd.read_csv(data_dir / "B2W-Reviews01.csv", dtype=str, keep_default_na=False)
    df = df[(df["review_text"].str.len() >= 20) & df["overall_rating"].isin(list("12345"))
            & df["recommend_to_a_friend"].isin(["Yes", "No"])]
    df = balanced(df, "overall_rating", rows)
    out = pd.DataFrame({
        "titulo": df["review_title"],
        "avaliacao": df["review_text"],
        "expected_recomenda": df["recommend_to_a_friend"],
        "expected_sentimento": df["overall_rating"].astype(int).map(sentiment_from_stars),
        "expected_estrelas": df["overall_rating"],
    })
    path = data_dir / f"b2w_sample_{rows}.csv"
    out.to_csv(path, index=False, encoding="utf-8")
    return path


def ag_sample(data_dir: Path, rows: int) -> Path:
    df = pd.read_parquet(data_dir / "ag_news_test.parquet")
    df = balanced(df, "label", rows)
    out = pd.DataFrame({"text": df["text"], "expected_topic": df["label"].map(AG_LABELS)})
    path = data_dir / f"ag_news_sample_{rows}.csv"
    out.to_csv(path, index=False, encoding="utf-8")
    return path


def calibration(conf: pd.Series, correct: pd.Series, bins: int = 10) -> dict:
    """Expected calibration error, and accuracy above/below the 0.7 threshold."""
    ece = 0.0
    edges = [i / bins for i in range(bins + 1)]
    for lo, hi in zip(edges, edges[1:]):
        mask = (conf > lo) & (conf <= hi) if lo else (conf >= lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(conf[mask].mean() - correct[mask].mean())
    hi_mask = conf >= 0.7
    return {
        "ece": round(float(ece), 3),
        "mean_confidence": round(float(conf.mean()), 3),
        "accuracy_conf_ge_0.7": round(float(correct[hi_mask].mean()), 3) if hi_mask.any() else None,
        "share_conf_ge_0.7": round(float(hi_mask.mean()), 3),
        "accuracy_conf_lt_0.7": round(float(correct[~hi_mask].mean()), 3) if (~hi_mask).any() else None,
    }


def score_question(table: pd.DataFrame, q) -> dict:
    exp = table["expected_" + q.id].map(lambda v: normalize_label(v, q.type))
    got = table[q.id].map(lambda v: normalize_label(v, q.type))
    correct = (exp == got)
    conf = pd.to_numeric(table[confidence_col(q.id)], errors="coerce").fillna(0.0)
    res = {"type": q.type, "rows": int(len(table)), "accuracy": round(float(correct.mean()), 3)}
    if q.type == "score":
        e, g = pd.to_numeric(exp, errors="coerce"), pd.to_numeric(got, errors="coerce")
        res["within_1"] = round(float(((e - g).abs() <= 1).mean()), 3)
        res["mean_abs_error"] = round(float((e - g).abs().mean()), 3)
    if q.type in ("choice", "score"):
        res["confusion"] = pd.crosstab(exp, got).to_dict()
    res["calibration"] = calibration(conf, correct.astype(float))
    return res


def evaluate(engine: str, dataset: str, csv_path: Path, questions, columns, out_dir: Path) -> dict:
    backend = make_backend(engine)
    t0 = time.perf_counter()
    result = run_file(csv_path, questions, columns, backend, out_dir=out_dir)
    seconds = time.perf_counter() - t0
    table = result.table
    return {
        "dataset": dataset, "engine": result.backend_name, "rows": int(len(table)),
        "seconds_total": round(seconds, 1), "seconds_per_row": round(seconds / len(table), 2),
        "needs_review_share": round(float((table["needs_review"] == "yes").mean()), 3),
        "questions": {q.id: score_question(table, q) for q in questions},
    }


def to_markdown(runs: list[dict]) -> str:
    lines = [f"# LUAR evaluation ({date.today():%Y-%m-%d})", "",
             "| Dataset | Engine | Question | Type | Accuracy | Extra | ECE | Acc. conf≥0.7 (share) | Acc. conf<0.7 | s/row |",
             "|---|---|---|---|---:|---|---:|---|---:|---:|"]
    for r in runs:
        for qid, q in r["questions"].items():
            c = q["calibration"]
            extra = f"±1: {q['within_1']:.0%}, MAE {q['mean_abs_error']}" if q["type"] == "score" else ""
            hi = "–" if c["accuracy_conf_ge_0.7"] is None else f"{c['accuracy_conf_ge_0.7']:.0%} ({c['share_conf_ge_0.7']:.0%})"
            lo = "–" if c["accuracy_conf_lt_0.7"] is None else f"{c['accuracy_conf_lt_0.7']:.0%}"
            lines.append(f"| {r['dataset']} | {r['engine']} | {qid} | {q['type']} | {q['accuracy']:.0%} | {extra} "
                         f"| {c['ece']} | {hi} | {lo} | {r['seconds_per_row']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--engines", nargs="+", default=["laya"], choices=ENGINES)
    ap.add_argument("--datasets", nargs="+", default=["b2w", "ag_news"], choices=["b2w", "ag_news"])
    ap.add_argument("--rows", type=int, default=300)
    args = ap.parse_args()

    download(args.data_dir)
    samples = {
        "b2w": (b2w_sample(args.data_dir, args.rows), B2W_QUESTIONS, ["titulo", "avaliacao"]),
        "ag_news": (ag_sample(args.data_dir, args.rows), AG_QUESTIONS, ["text"]),
    }
    RESULTS.mkdir(exist_ok=True)
    out_dir = args.data_dir / "outputs"
    for engine in args.engines:
        runs = []
        for name in args.datasets:
            path, questions, columns = samples[name]
            print(f"[{engine}] {name}: {path.name}", flush=True)
            run = evaluate(engine, name, path, questions, columns, out_dir)
            runs.append(run)
            print(json.dumps({k: v for k, v in run.items() if k != "questions"}), flush=True)
            for qid, q in run["questions"].items():
                print(f"   {qid}: accuracy {q['accuracy']:.1%}  ECE {q['calibration']['ece']}", flush=True)
            # save after every dataset, so an interrupted run keeps what it finished
            (RESULTS / f"{engine}.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")
            (RESULTS / f"{engine}.md").write_text(to_markdown(runs), encoding="utf-8")


if __name__ == "__main__":
    main()
