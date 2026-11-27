"""PDFs and images as a table, one row per page, read by LiteParse (optional: luar[ocr]).

Two readers. Tesseract is the default: free for everyone. OCRia-nano reads photos and poor scans
better, but its model license limits who may use it (personal use, and organizations under
US$ 2 million in revenue), so LUAR only uses it when chosen, never because it was downloaded.
"""
from __future__ import annotations

import hashlib
import importlib
import shutil
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .i18n import t

DOCUMENT_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
READERS = ("tesseract", "ocria-nano")
INSTALL_HINT = 'pip install "luar[ocr]"'
MAX_PAGES = 500
COLUMNS = ("file", "page", "text")  # like every column LUAR writes, in English

# Tesseract's Portuguese model, pinned: LiteParse fetches a missing one from the moving `main` branch
TESSDATA_COMMIT = "9ddc24e750eec0994223a9edc3fcb434a2244f3b"
TESSDATA_URL = f"https://github.com/tesseract-ocr/tessdata_best/raw/{TESSDATA_COMMIT}/por.traineddata"
TESSDATA_SHA256 = "711de9dbb8052067bd42f16b9119967f30bada80d57e2ef24f65d09f531adb04"
TESSDATA_DIR = Path.home() / ".cache" / "luar" / "tessdata"
OCRIA_VERSION = "1.0.0"  # the version LUAR was tested with; LiteParse checks its files' hashes
OCRIA_LICENSE = "https://huggingface.co/llamaindex/OCRia-nano-1"


def is_document(path: str | Path) -> bool:
    return Path(path).suffix.lower() in DOCUMENT_SUFFIXES


def import_liteparse():
    """Import the optional `liteparse` package, or explain how to install it."""
    try:
        import liteparse
    except ImportError as e:
        raise ValueError(t("o_missing", hint=INSTALL_HINT)) from e
    return liteparse


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tessdata_dir(download: bool = True) -> Path:
    """The folder holding the verified Portuguese model, downloading it once if allowed. LiteParse
    always gets this folder, so it never fetches an unpinned model on its own."""
    target = TESSDATA_DIR / "por.traineddata"
    if not target.is_file():
        if not download:
            raise ValueError(t("o_tess_missing"))
        TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=TESSDATA_DIR, delete=False) as tmp:
            with urllib.request.urlopen(TESSDATA_URL, timeout=60) as response:
                shutil.copyfileobj(response, tmp)
        part = Path(tmp.name)
        if _sha256(part) != TESSDATA_SHA256:
            part.unlink(missing_ok=True)
            raise ValueError(t("o_tess_integrity", path=target))
        part.replace(target)
    elif _sha256(target) != TESSDATA_SHA256:
        raise ValueError(t("o_tess_integrity", path=target))
    return TESSDATA_DIR


def _models():
    """LiteParse's model manager: a submodule the package does not import by itself."""
    import_liteparse()
    return importlib.import_module("liteparse.models")


def ocria_installed() -> bool:
    models = _models()
    return any(m.name == "ocria-nano" and m.complete and m.version == OCRIA_VERSION for m in models.list())


def download_ocria() -> str:
    """Pull OCRia-nano (LiteParse checks every file's hash and prints the model license)."""
    return _models().pull(f"ocria-nano@{OCRIA_VERSION}")


def _parser(reader: str):
    if reader not in READERS:
        raise ValueError(t("o_unknown_reader", name=reader, names=", ".join(READERS)))
    liteparse = import_liteparse()
    options = {"ocr_backend": reader, "output_format": "text", "quiet": True, "max_pages": MAX_PAGES,
               "num_workers": 1}
    if reader == "tesseract":
        options.update(ocr_language="por", tessdata_path=str(tessdata_dir()))
    elif not ocria_installed():
        raise ValueError(t("o_ocria_missing", url=OCRIA_LICENSE))
    return liteparse.LiteParse(**options)


@lru_cache(maxsize=4)
def _read(path: str, size: int, mtime_ns: int, reader: str) -> tuple[tuple[str, str], ...]:
    """(page, text) per page. Cached: the web interface reads the file on upload and again on Run."""
    parser = _parser(reader)  # missing package or model: its own message, not "unreadable"
    try:
        result = parser.parse(path)
    except Exception as e:  # LiteParse's ParseError and friends: an unreadable or protected file
        raise ValueError(t("o_unreadable", error=e)) from e
    if result.total_pages > MAX_PAGES:
        raise ValueError(t("o_too_many_pages", pages=result.total_pages, max=MAX_PAGES))
    return tuple((str(page.page_num), page.text.strip()) for page in result.pages)


def read_document(path: str | Path, reader: str = "tesseract") -> pd.DataFrame:
    """One row per page: `file`, `page` and `text`. The text of a PDF that has one is used as is;
    scanned pages and images are read by OCR."""
    path = Path(path)
    stat = path.stat()
    pages = _read(str(path.resolve()), stat.st_size, stat.st_mtime_ns, reader)
    return pd.DataFrame([(path.name, page, text) for page, text in pages], columns=list(COLUMNS), dtype=str)
