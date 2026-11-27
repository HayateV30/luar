"""Evaluate LUAR's PDF and image reading on made-up Portuguese documents.

    python bench/ocr_documents.py --data-dir <folder> --readers tesseract ocria-nano

Draws ten fictional documents (an invoice, an all-caps receipt, a contract, a table, a skewed photo,
a low-resolution scan, a typewritten letter, an image-only PDF...) with their exact text, reads them
the way a user would (`read_table`) and writes character error rate, accents, numbers and time to
bench/results/ocr.{json,md}. No real document is used.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from luar.tables import read_table

RESULTS = Path(__file__).resolve().parent / "results"
FONT_DIRS = [Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]
FALLBACK = {"arialbd.ttf": "DejaVuSans-Bold.ttf", "times.ttf": "DejaVuSerif.ttf", "cour.ttf": "DejaVuSansMono.ttf"}
W, H = 1654, 2339  # A4 at 200 dpi
ACCENTED = set("áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ")

DOCS = {
    "01_invoice": ("arial.ttf", 34, [
        "NOTA FISCAL DE SERVIÇO ELETRÔNICA", "Prestador: Clínica Sorriso Fictício Ltda",
        "CNPJ: 12.345.678/0001-90", "Tomador: Maria Antônia da Conceição", "Data de emissão: 14/03/2026",
        "Descrição: Manutenção de aparelho ortodôntico", "Valor total: R$ 1.349,90", "ISS retido: R$ 67,50"]),
    "02_receipt_all_caps": ("arialbd.ttf", 38, [
        "RECIBO", "RECEBI DE JOÃO DA CONCEIÇÃO", "A QUANTIA DE R$ 350,00", "(TREZENTOS E CINQUENTA REAIS)",
        "REFERENTE À CONSULTA DE AVALIAÇÃO", "SÃO JOSÉ DOS CAMPOS, 02 DE ABRIL DE 2026"]),
    "03_complaint": ("arial.ttf", 36, [
        "Formulário de reclamação", "Nome: Luíza Gonçalves", "Pedido nº 482193",
        "Produto: Escova elétrica com cabeça extra",
        "Problema: a bateria não carrega e o pedido chegou com atraso.",
        "Solicito o reembolso de R$ 249,99 no cartão."]),
    "04_contract": ("times.ttf", 34, [
        "CONTRATO DE PRESTAÇÃO DE SERVIÇOS", "Cláusula 1ª. O contratante pagará doze parcelas mensais",
        "de R$ 420,00, vencendo a primeira em 10/05/2026.", "Cláusula 2ª. Em caso de rescisão, aplicar-se-á multa",
        "de 10% sobre o saldo devedor, além de correção", "monetária pelo índice oficial."]),
    "05_prescription": ("times.ttf", 36, [
        "Receituário", "Paciente: Sebastião Araújo", "Uso oral",
        "Ibuprofeno 600 mg, 1 comprimido a cada 8 horas por 3 dias.", "Orientação: não ingerir bebida alcoólica.",
        "Dr. Fictício Ávila, CRO 98765"]),
    "06_table": ("arial.ttf", 32, [
        "Orçamento nº 2026-117", "Item                     Qtd    Preço unit.    Total",
        "Bráquete metálico         20       R$ 12,50     R$ 250,00",
        "Fio ortodôntico            4       R$ 35,90     R$ 143,60",
        "Elástico intraoral        50        R$ 0,80      R$ 40,00", "Total geral: R$ 433,60"]),
    "07_photo": ("cour.ttf", 32, [
        "FARMÁCIA POPULAR FICTÍCIA", "CUPOM NÃO FISCAL", "ESCOVA DENTAL MACIA    1 X 9,90",
        "FIO DENTAL 50M         2 X 7,45", "TOTAL R$ 24,80", "PAGAMENTO: CARTÃO DE DÉBITO"]),
    "08_low_resolution": ("arial.ttf", 34, [
        "Comunicado aos pacientes", "A unidade estará fechada no feriado de 21 de abril.",
        "Atendimentos de urgência: (12) 3456-7890.", "Agradecemos a compreensão."]),
    "09_typewritten": ("cour.ttf", 34, [
        "Ofício nº 045/2026", "Ao Sr. Gerente da Agência Centro", "Solicitamos a emissão de segunda via do boleto",
        "nº 34191.79001 01043.510047 91020.150008 1", "com vencimento em 30/06/2026.",
        "Atenciosamente, Administração"]),
    "10_scanned_pdf": ("arial.ttf", 34, [
        "Declaração", "Declaro, para os devidos fins, que Paulo Évora",
        "esteve em atendimento nesta clínica no dia 18/09/2026,", "das 14h às 15h30.",
        "Itajubá, 18 de setembro de 2026."]),
}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for folder in FONT_DIRS:
        for candidate in (name, FALLBACK.get(name, "DejaVuSans.ttf")):
            if (folder / candidate).is_file():
                return ImageFont.truetype(str(folder / candidate), size)
    raise FileNotFoundError(f"no font for {name}")


def draw(data_dir: Path) -> dict[str, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, (font_file, size, lines) in DOCS.items():
        img = Image.new("L", (W, H), 255)
        pen, f, y = ImageDraw.Draw(img), font(font_file, size), 160
        for line in lines:
            pen.text((140, y), line, font=f, fill=0)
            y += int(size * 1.9)
        img = img.crop((0, 0, W, min(H, y + 200)))
        if name == "07_photo":  # skewed, blurred, noisy, grey background
            img = img.point(lambda v: int(v * 0.85 + 25)).rotate(3.5, expand=True, fillcolor=200)
            img = Image.blend(img.filter(ImageFilter.GaussianBlur(1.2)), Image.effect_noise(img.size, 18), 0.12)
            path, kwargs = data_dir / f"{name}.jpg", {"quality": 70}
        elif name == "08_low_resolution":  # 100 dpi, heavy JPEG
            img = img.resize((img.width // 2, img.height // 2)).filter(ImageFilter.GaussianBlur(0.6))
            path, kwargs = data_dir / f"{name}.jpg", {"quality": 35}
        elif name == "10_scanned_pdf":  # a PDF with no text layer, slightly crooked
            img = img.rotate(-1.2, expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(0.5))
            path, kwargs = data_dir / f"{name}.pdf", {"resolution": 200}
        else:
            path, kwargs = data_dir / f"{name}.png", {}
        img.convert("RGB").save(path, **kwargs)
        files[name] = path
    return files


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(gold: str, text: str) -> dict:
    g, o = norm(gold), norm(text)
    words = set(re.findall(r"[\wÀ-ÿ]+", o))
    accented = [w for w in re.findall(r"[\wÀ-ÿ]+", g) if ACCENTED & set(w)]
    numbers = re.findall(r"\d[\d.,/\-]*\d|\d", g)
    found = re.findall(r"\d[\d.,/\-]*\d|\d", o)
    return {"cer": round(distance(g, o) / max(1, len(g)), 3),
            "accents": [sum(w in words for w in accented), len(accented)],
            "numbers": [sum(n in found for n in numbers), len(numbers)]}


def to_markdown(runs: dict) -> str:
    lines = [f"# LUAR document reading ({date.today():%Y-%m-%d})", "",
             "| Reader | Document | Character error rate | Accents | Numbers | s/page |", "|---|---|---:|---|---|---:|"]
    for reader, run in runs.items():
        for name, r in run["documents"].items():
            lines.append(f"| {reader} | {name} | {r['cer']:.1%} | {r['accents'][0]}/{r['accents'][1]} "
                         f"| {r['numbers'][0]}/{r['numbers'][1]} | {r['seconds']} |")
        s = run["summary"]
        lines.append(f"| **{reader}** | **all ten** | **{s['cer']:.1%}** | **{s['accents']}** | **{s['numbers']}** "
                     f"| **{s['seconds_per_page']}** |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--readers", nargs="+", default=["tesseract"], choices=["tesseract", "ocria-nano"])
    args = ap.parse_args()
    files = draw(args.data_dir)
    runs = {}
    for reader in args.readers:
        docs = {}
        for name, path in files.items():
            t0 = time.perf_counter()
            df, _ = read_table(path, reader=reader)
            docs[name] = {**score("\n".join(DOCS[name][2]), "\n".join(df["text"])),
                          "seconds": round(time.perf_counter() - t0, 2)}
            print(reader, name, docs[name], flush=True)
        total = lambda k: "%d/%d" % tuple(map(sum, zip(*(d[k] for d in docs.values()))))
        runs[reader] = {"documents": docs, "summary": {
            "cer": round(sum(d["cer"] for d in docs.values()) / len(docs), 3), "accents": total("accents"),
            "numbers": total("numbers"),
            "seconds_per_page": round(sum(d["seconds"] for d in docs.values()) / len(docs), 2)}}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "ocr.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")
    (RESULTS / "ocr.md").write_text(to_markdown(runs), encoding="utf-8")
    print(to_markdown(runs))


if __name__ == "__main__":
    sys.exit(main())
