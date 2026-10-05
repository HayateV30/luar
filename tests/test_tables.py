import pandas as pd
import pytest

from luar.tables import output_paths, read_table, write_table

from .conftest import EXAMPLES


def test_brazilian_excel_style_csv():
    # semicolon separator + Windows-1252 accents, as Excel exports in pt-BR
    df, info = read_table(EXAMPLES / "avaliacoes.csv")
    assert info.sep == ";"
    assert info.encoding in ("cp1252", "latin-1")
    assert "três" in df.loc[2, "avaliacao"]
    assert len(df) == 10


def test_utf8_comma_csv_with_quotes():
    df, info = read_table(EXAMPLES / "reviews.csv")
    assert info.sep == "," and info.encoding == "utf-8-sig"
    assert df.loc[0, "review"].startswith("The package arrived")
    assert df["id"].tolist()[:3] == ["1", "2", "3"]  # read as text, never reformatted


def test_never_overwrites(tmp_path):
    src = tmp_path / "data.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    df, info = read_table(src)
    first, summary = output_paths(info)
    assert first.name == "data_luar.csv" and summary.name == "data_luar_summary.md"
    write_table(df, first, info)
    second, summary2 = output_paths(info)
    assert second.name == "data_luar_2.csv" and summary2.name == "data_luar_2_summary.md"
    with pytest.raises(FileExistsError):
        write_table(df, first, info)
    assert src.read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_keeps_separator_on_output(tmp_path):
    src = tmp_path / "br.csv"
    src.write_bytes("nome;nota\nJoão;8,5\n".encode("cp1252"))
    df, info = read_table(src)
    out, _ = output_paths(info)
    write_table(df, out, info)
    assert out.read_text(encoding="utf-8-sig").splitlines()[1] == "João;8,5"


def test_excel_round_trip(tmp_path):
    src = tmp_path / "book.xlsx"
    pd.DataFrame({"text": ["hello", "world"], "n": ["01", "02"]}).to_excel(src, index=False, sheet_name="Data")
    df, info = read_table(src)
    assert info.kind == "excel" and info.sheet == "Data"
    assert df["n"].tolist() == ["01", "02"]
    out, _ = output_paths(info)
    assert out.suffix == ".xlsx"
    write_table(df, out, info)
    back, _ = read_table(out)
    assert back["text"].tolist() == ["hello", "world"]


def test_rejects_old_xls(tmp_path):
    p = tmp_path / "old.xls"
    p.write_bytes(b"")
    with pytest.raises(ValueError, match=".xlsx"):
        read_table(p)


def test_unquoted_separator_inside_text_is_refused_not_cut(tmp_path):
    src = tmp_path / "bad.csv"
    src.write_text("avaliacao\nProduto chegou quebrado, quero devolver.\nAdorei\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Line 2 .* more fields than the header"):
        read_table(src)


def test_quoted_separator_inside_text_is_fine(tmp_path):
    src = tmp_path / "ok.csv"
    src.write_text('avaliacao\n"Produto chegou quebrado, quero devolver."\nAdorei\n', encoding="utf-8")
    df, _ = read_table(src)
    assert df["avaliacao"].tolist() == ["Produto chegou quebrado, quero devolver.", "Adorei"]
    assert list(df.index) == [0, 1]
