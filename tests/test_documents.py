"""PDFs and images as a table (luar[ocr]). Fast tests use a stand-in for LiteParse; `-m slow` runs it."""
import hashlib
import io
import sys
import types

import pytest

from luar import documents
from luar.cli import main as cli_main
from luar.tables import output_paths, read_table, write_table


class FakeParser:
    calls = []

    def __init__(self, **options):
        self.options = options

    def parse(self, path):
        FakeParser.calls.append((path, self.options))
        pages = [types.SimpleNamespace(page_num=1, text="  Recibo de R$ 350,00  "),
                 types.SimpleNamespace(page_num=2, text="Pedido nº 482193\n")]
        return types.SimpleNamespace(pages=pages, total_pages=FakeParser.total_pages)


@pytest.fixture
def fake_liteparse(monkeypatch, tmp_path):
    """liteparse as a stand-in, with a verified Portuguese model already in place."""
    FakeParser.calls, FakeParser.total_pages = [], 2
    installed = []
    models = types.SimpleNamespace(list=lambda: installed, pull=lambda spec: f"pulled {spec}")
    # like the real package: `models` is a submodule, not an attribute of `liteparse`
    monkeypatch.setitem(sys.modules, "liteparse", types.SimpleNamespace(LiteParse=FakeParser))
    monkeypatch.setitem(sys.modules, "liteparse.models", models)
    model = tmp_path / "tessdata" / "por.traineddata"
    model.parent.mkdir()
    model.write_bytes(b"model")
    monkeypatch.setattr(documents, "TESSDATA_DIR", model.parent)
    monkeypatch.setattr(documents, "TESSDATA_SHA256", hashlib.sha256(b"model").hexdigest())
    documents._read.cache_clear()
    yield types.SimpleNamespace(installed=installed)
    documents._read.cache_clear()


@pytest.fixture
def scan(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4 stand-in")
    return path


def test_a_document_becomes_one_row_per_page(fake_liteparse, scan):
    df, info = read_table(scan)
    assert list(df.columns) == ["file", "page", "text"]
    assert df.values.tolist() == [["scan.pdf", "1", "Recibo de R$ 350,00"], ["scan.pdf", "2", "Pedido nº 482193"]]
    assert (info.kind, info.sheet) == ("document", "pages")


def test_tesseract_is_the_default_and_gets_the_verified_model(fake_liteparse, scan, tmp_path):
    read_table(scan)
    _, options = FakeParser.calls[0]
    assert options["ocr_backend"] == "tesseract"
    assert (options["ocr_language"], options["tessdata_path"]) == ("por", str(tmp_path / "tessdata"))
    assert options["max_pages"] == documents.MAX_PAGES


def test_ocria_is_never_used_unless_chosen_and_installed(fake_liteparse, scan):
    with pytest.raises(ValueError, match="US\\$ 2 million"):
        read_table(scan, reader="ocria-nano")
    assert FakeParser.calls == []
    fake_liteparse.installed.append(types.SimpleNamespace(name="ocria-nano", complete=True, version="0.9.0"))
    with pytest.raises(ValueError, match="luar download ocria-nano"):  # another version than the tested one
        read_table(scan, reader="ocria-nano")
    fake_liteparse.installed.append(types.SimpleNamespace(name="ocria-nano", complete=True, version="1.0.0"))
    read_table(scan, reader="ocria-nano")
    _, options = FakeParser.calls[0]
    assert options["ocr_backend"] == "ocria-nano" and "tessdata_path" not in options


def test_the_page_reads_a_document_once(fake_liteparse, scan):
    read_table(scan)  # on upload
    read_table(scan)  # on Run
    assert len(FakeParser.calls) == 1
    scan.write_bytes(b"%PDF-1.4 another file")  # a changed file is read again
    read_table(scan)
    assert len(FakeParser.calls) == 2


def test_too_many_pages_are_refused(fake_liteparse, scan):
    FakeParser.total_pages = documents.MAX_PAGES + 1
    with pytest.raises(ValueError, match="501 pages"):
        read_table(scan)


def test_an_unreadable_document_says_so(fake_liteparse, scan, monkeypatch):
    def broken(self, path):
        raise RuntimeError("password required")

    monkeypatch.setattr(FakeParser, "parse", broken)
    with pytest.raises(ValueError, match="password"):
        read_table(scan)


def test_without_the_extra_it_says_how_to_install(monkeypatch, scan):
    monkeypatch.setitem(sys.modules, "liteparse", None)
    documents._read.cache_clear()
    with pytest.raises(ValueError, match=r'pip install "luar\[ocr\]"'):
        read_table(scan)


def test_spreadsheets_do_not_need_the_extra(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "liteparse", None)
    sheet = tmp_path / "data.csv"
    sheet.write_text("text\nhello\n", encoding="utf-8")
    df, info = read_table(sheet)
    assert info.kind == "csv" and df["text"].tolist() == ["hello"]


def test_the_tesseract_model_is_downloaded_pinned_and_checked(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "TESSDATA_DIR", tmp_path / "tessdata")
    asked = []

    def fake_urlopen(url, timeout):
        asked.append(url)
        return io.BytesIO(b"model")

    monkeypatch.setattr(documents.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(documents, "TESSDATA_SHA256", hashlib.sha256(b"model").hexdigest())
    assert documents.tessdata_dir() == tmp_path / "tessdata"
    assert asked == [documents.TESSDATA_URL] and documents.TESSDATA_COMMIT in asked[0]
    documents.tessdata_dir()  # already there and verified: no second download
    assert len(asked) == 1


def test_a_tampered_tesseract_model_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "TESSDATA_DIR", tmp_path)
    (tmp_path / "por.traineddata").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="does not match"):
        documents.tessdata_dir()
    monkeypatch.setattr(documents.urllib.request, "urlopen", lambda url, timeout: io.BytesIO(b"tampered"))
    (tmp_path / "por.traineddata").unlink()
    with pytest.raises(ValueError, match="does not match"):
        documents.tessdata_dir()
    assert not any(tmp_path.iterdir())  # the bad download is not kept


def test_the_result_is_written_as_xlsx(fake_liteparse, scan, tmp_path):
    df, info = read_table(scan)
    table, summary = output_paths(info, tmp_path / "out")
    assert table.name == "scan_luar.xlsx"
    write_table(df, table, info)
    df2, _ = read_table(table)
    assert df2["text"].tolist() == df["text"].tolist()


def test_command_line_reader_option(fake_liteparse, scan, capsys):
    assert cli_main(["columns", str(scan)]) == 0
    assert "one row per page, read with tesseract" in capsys.readouterr().out
    assert cli_main(["columns", str(scan), "--ocr", "ocria-nano"]) == 2
    assert "luar download ocria-nano" in capsys.readouterr().err


def test_download_command_for_the_readers(monkeypatch):
    from luar.backends import laya_backend

    calls = []
    monkeypatch.setattr(laya_backend, "download_checkpoints", lambda checkpoints: calls.append(checkpoints) or [])
    monkeypatch.setattr(documents, "tessdata_dir", lambda: calls.append("ocr") or "folder")
    monkeypatch.setattr(documents, "download_ocria", lambda: calls.append("ocria") or "folder")
    assert cli_main(["download", "ocr"]) == 0
    assert calls == ["ocr"]  # no Laya, no OCRia-nano
    assert cli_main(["download", "ocria-nano"]) == 0
    assert calls == ["ocr", "ocria"]


def test_the_page_offers_the_reader_with_tesseract_selected(fake_liteparse, scan):
    app = pytest.importorskip("luar.app")
    demo = app.build()
    reader = next(c["props"] for c in demo.config["components"]
                  if c["type"] == "dropdown" and c["props"].get("label") == "Reader for PDFs and images")
    assert reader["value"] == "tesseract"
    relabel = next(fn for fn in demo.fns.values() if getattr(fn.fn, "__name__", "") == "relabel")
    out = relabel.fn("pt", app.questions_frame([]), None, None, "auto", "laya", "ocria-nano")
    assert len(out) == len(relabel.outputs)
    assert "Leitor de PDF e imagem" in repr(out) and "OCRia-nano (licença restrita)" in repr(out)
    columns, preview, status, *_ = app.on_file(str(scan), "pt", "tesseract", progress=lambda *a, **k: None)
    assert columns["value"] == ["text"]
    assert "uma linha por página, lido com Tesseract (padrão)" in status


@pytest.mark.slow
def test_real_tesseract_reads_a_generated_page(tmp_path):
    """Needs `pip install "luar[ocr]"`; downloads Tesseract's Portuguese model on first use."""
    pytest.importorskip("liteparse")
    image = pytest.importorskip("PIL.Image")
    draw = pytest.importorskip("PIL.ImageDraw")
    font = pytest.importorskip("PIL.ImageFont")
    page = image.new("L", (1400, 400), 255)
    draw.Draw(page).text((60, 120), "RECEBI DE JOÃO DA CONCEIÇÃO R$ 350,00", fill=0,
                         font=font.truetype("arial.ttf" if sys.platform == "win32" else "DejaVuSans.ttf", 44))
    path = tmp_path / "recibo.png"
    page.save(path)
    documents._read.cache_clear()
    df, _ = read_table(path)
    assert "JOÃO DA CONCEIÇÃO" in df["text"][0] and "350,00" in df["text"][0]
