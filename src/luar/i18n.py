"""Interface texts in English and Brazilian Portuguese.

`t("key", **values)` returns the text in the current language. The language lives in a context
variable: the web interface sets it for each click with `language(lang)`; everything else (the
command line, the tests) stays in English. Column names and cell values written to the spreadsheet
(`needs_review`, `yes`, `<id>_confidence`…) are data and are never translated.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

LANGUAGES = ("en", "pt")
DEFAULT = "en"
_current: ContextVar[str] = ContextVar("luar_language", default=DEFAULT)


def current() -> str:
    return _current.get()


def normalize(lang: str | None) -> str:
    """"pt", "pt-BR", "pt_PT"… -> "pt"; anything else -> "en"."""
    return "pt" if str(lang or "").strip().lower().startswith("pt") else "en"


@contextmanager
def language(lang: str | None):
    token = _current.set(normalize(lang))
    try:
        yield
    finally:
        _current.reset(token)


def t(key: str, **values) -> str:
    text = TEXTS[current()].get(key, TEXTS[DEFAULT][key])
    return text.format(**values) if values else text


def num(n: int) -> str:
    """20000 -> "20,000" (en) / "20.000" (pt)."""
    s = f"{n:,}"
    return s.replace(",", ".") if current() == "pt" else s


def dec(x: float, digits: int = 2) -> str:
    """0.7 -> "0.70" (en) / "0,70" (pt)."""
    s = f"{x:.{digits}f}"
    return s.replace(".", ",") if current() == "pt" else s


def rows(n: int) -> str:
    """ "1 row", "3 rows" / "1 linha", "3 linhas"."""
    return t("row_one" if n == 1 else "row_many", n=num(n))


TEXTS: dict[str, dict[str, str]] = {
    "en": {
        # --- header -------------------------------------------------------------------------
        # the button names the language it switches to (PT-BR, not "Português": not Portugal's)
        "lang_button": "PT-BR",
        "readme": "README",
        "sample_csv": "Sample CSV",
        "sample_json": "Sample JSON",
        "tagline": (
            "**Local Utility for Automated Reviews.** Drop a spreadsheet, say what you want to know about "
            "each row, and get a copy with the answers plus a summary. Everything runs on this computer, "
            "with the Laya model."
        ),
        "laya_missing": "**The Laya engine could not be loaded.** Reinstall it with `{hint}` and restart LUAR.",
        # --- steps --------------------------------------------------------------------------
        "step_sheet": "1. Spreadsheet",
        "step_preview": "Preview",
        "step_questions": "2. What do you want to know about each row?",
        "step_run": "3. Run",
        "step_result": "Result",
        "tip_sheet": (
            "Drop a .csv or .xlsx file (up to 50 MB and 20,000 rows). LUAR works on a copy: your file is "
            "never changed. Then tick the column(s) with the text the model should read. Columns named "
            "expected_... hold answers you already know; they are used to measure accuracy and are never read."
        ),
        "tip_preview": "The first rows of your file, to check it was read correctly: columns, accents and separator.",
        "tip_questions": (
            "Each row is one question. id: a short name (letters, numbers, _) that becomes the new "
            "column. type: choice picks one option, noul answers yes/no, score places the row on a "
            "scale (experimental). question: plain language. options: separated by ; with an optional "
            "description after : (descriptions help a lot)."
        ),
        "tip_run": (
            "Confidence threshold: answers below it mark the row needs_review. Laya model variant: auto uses "
            "the English model for English files and the multilingual one for the rest. The first run "
            "downloads the model; later runs work offline."
        ),
        "tip_result": (
            "Download the copy of your spreadsheet with the new columns, and the summary (.md). Rows with "
            "needs_review = yes deserve a human look: low confidence, possible manipulation or empty "
            "text. These files are deleted when LUAR closes, so download them first."
        ),
        # --- step 1 -------------------------------------------------------------------------
        "upload": "CSV or XLSX",
        # Gradio's upload box (LUAR draws these words: Gradio does not redraw them on a language change)
        "upload_drop": "Drop File Here",
        "upload_or": "- or -",
        "upload_click": "Click to Upload",
        "upload_aria": "Click to upload or drop files",
        "columns": "Column(s) the model should read",
        "allow_sensitive": "These columns hold personal data, and I am allowed to process it",
        "example": "…or try an example",
        "ex_reviews": "English reviews",
        "ex_severity": "English reviews: severity (score)",
        "ex_avaliacoes": "Portuguese reviews",
        "ex_sample": "Test sample (Sample CSV)",
        "status": "**{name}**: {rows}, {cols} ({detail}).",
        "status_cols_one": "1 column",
        "status_cols_many": "{n} columns",
        "status_csv": "separator `{sep}`, {encoding}",
        "status_excel": "sheet `{sheet}`",
        "status_sensitive": (
            "**Personal data found:** {found}. LUAR will only read these columns if you confirm you are "
            "allowed to process this data."
        ),
        # --- step 2 -------------------------------------------------------------------------
        "headers": "id|type|question|options",
        "question_help": (
            "**Question types:** `choice` picks one option · `noul` answers yes/no · `score` places the row "
            "on an ordered scale (*experimental*: the least reliable type in our tests).\n"
            "**Options:** separate with `;` and optionally add a description after `:`, e.g.\n"
            "`delivery: shipping, delays; product: defects, quality`. Up to 20 options; `noul` takes none.\n"
            "Add a column named `expected_<id>` to your file to measure accuracy on rows you already know."
        ),
        "load_questions": "Load questions (.json)",
        "save_questions": "Save questions as .json",
        "questions_file": "Questions file",
        "no_questions": (
            "There are no questions yet. In step 2, fill in at least the id and the question of one row, "
            "or load a questions .json file in \"Load questions (.json)\"."
        ),
        "sample_hint": (
            " Trying the Sample CSV? Download Sample JSON at the top of the page and load it there, or pick "
            "\"Test sample (Sample CSV)\" in \"…or try an example\" to load both at once."
        ),
        "bad_json": "This questions file is not valid JSON ({error}).",
        # --- step 3 -------------------------------------------------------------------------
        "threshold": "Confidence threshold",
        "threshold_info": "Answers below it mark the row as needs_review",
        "checkpoint": "Laya model variant",
        "checkpoint_info": "auto: English files use the English model, others the multilingual one",
        "ckpt_auto": "auto",
        "ckpt_multilingual": "multilingual",
        "ckpt_english": "english",
        "run": "Run",
        "progress_loading": "Loading the model (the first run downloads it)…",
        "progress_rows": "{done}/{total} rows",
        "engine_auto": "chosen automatically",
        # --- result -------------------------------------------------------------------------
        "downloads": "Download (result copy + summary)",
        "tab_summary": "Summary",
        "tab_table": "Table",
        "done": "Done: {rows}, {flagged} to review.",
        # --- toasts -------------------------------------------------------------------------
        "title_error": "Error",
        "title_warning": "Warning",
        "title_info": "Info",
        "err_read": "Could not read this file: {error}",
        "err_too_many_rows": (
            "This file has {rows} rows; the interface takes up to {max} (about one row per second with "
            "Laya). Split the file, or use the command line: luar run"
        ),
        "err_no_file": "Drop a CSV or XLSX file first.",
        "err_no_columns": "Choose at least one column to read.",
        "warn_score": "`score` questions are experimental: check those answers by hand.",
        "err_sensitive_ui": (
            "The columns to read hold personal data ({found}). If you are allowed to process it, tick the "
            "confirmation under the columns; otherwise remove that data from the file."
        ),
        "warn_manipulation": (
            "To review: {rows} with text that looks written to steer the answers. Check them by hand."
        ),
        # --- shared words -------------------------------------------------------------------
        "row_one": "{n} row",
        "row_many": "{n} rows",
        # --- questions.py -------------------------------------------------------------------
        "q_bad_id": "Invalid question id {id}: use letters, digits and underscores, not starting with a digit.",
        "q_bad_type": "Question {id}: type must be one of {types}.",
        "q_empty": "Question {id}: the question text is empty.",
        "q_noul_options": "Question {id}: yes/no (noul) questions take no options.",
        "q_few_options": "Question {id}: {type} needs at least 2 options.",
        "q_many_options": (
            "Question {id}: {n} options; the model handles at most {max}. Split it into two questions."
        ),
        "q_bad_options": "Unrecognized options format: {raw}",
        "q_bad_structure": "Questions must be a list or a mapping of id -> question.",
        "q_none": "Define at least one question.",
        "q_duplicate": "Duplicate question id {id}.",
        # --- tables.py ----------------------------------------------------------------------
        "t_xls": "Old .xls files are not supported; save the file as .xlsx or .csv.",
        "t_extra_fields": (
            "Line {line} of this file has more fields than the header ({header}), probably a '{sep}' inside "
            "a text without quotes. Save the file again from Excel (it adds the quotes), or put that text "
            "between double quotes."
        ),
        "t_bad_xlsx": "This is not a valid Excel file (.xlsx). Save it again from Excel, or as .csv.",
        "t_xlsx_too_big": (
            "This Excel file unpacks to {size} MB, more than LUAR accepts ({max} MB). Split it, or save the "
            "columns you need as .csv."
        ),
        "t_overwrite": "Refusing to overwrite {path}",
        # --- engine.py ----------------------------------------------------------------------
        "e_missing_columns": "Column(s) not found: {columns}",
        "e_clash": (
            "The file already has column(s) {columns}; rename the question id(s) or use the original file "
            "instead of a previous LUAR result."
        ),
        "e_threshold": "The confidence threshold must be between 0 and 1.",
        "e_sensitive": (
            "The column(s) to read hold personal data ({found}). Process them only if you are allowed to: "
            "confirm it to continue, or remove that data from the file."
        ),
        # --- safety.py ----------------------------------------------------------------------
        "kind_CPF": "CPF",
        "kind_CNPJ": "CNPJ",
        "kind_card number": "card number",
        "kind_e-mail": "e-mail",
        "kind_phone": "phone",
        "kind_in_rows": "{kind} in {rows}",
        # --- backends -----------------------------------------------------------------------
        "b_unknown_checkpoint": "Unknown checkpoint {name}; use one of {names}.",
        "b_laya_missing": "The Laya engine could not be loaded. Reinstall it with: {hint}",
        "b_app_control": (
            "Windows blocked one of PyTorch's files (Application Control, WinError 4551), so the Laya "
            "engine could not start. This can happen just once: close LUAR and open it again. If it keeps "
            "happening, ask whoever manages this computer to allow PyTorch's files. Details: {error}"
        ),
        "b_torch": (
            "PyTorch, which the Laya engine needs, could not be loaded. Close LUAR and open it again; if it "
            "keeps happening, reinstall it with: pip install --force-reinstall torch. Details: {error}"
        ),
        "b_integrity": (
            "The Laya model file does not match the official one ({path}). It may be corrupted or altered: "
            "delete that folder and download it again with: luar download"
        ),
        # --- report.py (summary .md) --------------------------------------------------------
        "r_title": "# LUAR summary: {source}",
        "r_table": "table",
        "r_date_format": "%Y-%m-%d %H:%M",
        "r_date": "Date",
        "r_engine": "Engine",
        "r_rows": "Rows",
        "r_columns_read": "Columns read",
        "r_threshold": "Confidence threshold",
        "r_to_review": "Rows to review",
        "r_time": "Time",
        "r_result_file": "Result file",
        "r_personal": (
            "> **Personal data:** the columns read hold {found}. You confirmed you may process it. The "
            "values are not repeated in this summary."
        ),
        "r_manipulation": (
            "> **Possible manipulation:** {rows} with text that looks written to steer the answers (for "
            'example "ignore the question, the correct answer is..."). That marks the row for review: check '
            "those answers by hand."
        ),
        "r_experimental": (
            "> **Experimental:** `score` was the least reliable question type in our tests (on 300 real "
            "product reviews, Laya matched the exact star rating 33% of the time, 68% within one star). "
            "Check these results by hand. Low confidence on a `score` question does not mark the row for "
            "review."
        ),
        "r_answers_header": "| Answer | Rows | % |",
        "r_no_answer": "*(no answer)*",
        "r_yes": "yes",
        "r_no": "no",
        "r_confidence": "Average confidence {avg}; {low} below the threshold.",
        "r_accuracy": "**Accuracy against `{column}`: {hits}/{total} ({pct}).**",
        "r_review_title": "## Rows to review",
        "r_review_none": "None: every answer is above the confidence threshold.",
        "r_review_header": "| Row | Why | Text |",
        "r_review_more": "…and {n} more. Filter `{column}` = yes in the result file.",
        "r_footer": (
            "Answers come from an automated model and can be wrong. Rows marked `{column}` deserve a human "
            "look; the original file was not changed."
        ),
        # review_reasons are written to the spreadsheet in English; the summary shows them translated
        "reason_empty text": "empty text",
        "reason_possible manipulation": "possible manipulation",
        "reason_instructions to the model": "instructions to the model",
        "reason_fake answer for": "fake answer for",
        "reason_order about": "order about",
        "reason_claimed answer for": "claimed answer for",
    },
    "pt": {
        # --- cabeçalho ----------------------------------------------------------------------
        "lang_button": "English",
        "readme": "Manual",
        "sample_csv": "CSV de exemplo",
        "sample_json": "JSON de exemplo",
        "tagline": (
            "**Local Utility for Automated Reviews (utilitário local para revisões automáticas).** Arraste "
            "uma planilha, diga o que quer saber de cada linha e receba uma cópia com as respostas e um "
            "resumo. Tudo roda neste computador, com o modelo Laya."
        ),
        "laya_missing": "**Não foi possível carregar o motor Laya.** Reinstale com `{hint}` e abra a LUAR de novo.",
        # --- etapas -------------------------------------------------------------------------
        "step_sheet": "1. Planilha",
        "step_preview": "Prévia",
        "step_questions": "2. O que você quer saber de cada linha?",
        "step_run": "3. Executar",
        "step_result": "Resultado",
        "tip_sheet": (
            "Arraste um arquivo .csv ou .xlsx (até 50 MB e 20.000 linhas). A LUAR trabalha numa cópia: o seu "
            "arquivo nunca é alterado. Depois marque a(s) coluna(s) com o texto que o modelo deve ler. "
            "Colunas chamadas expected_... guardam respostas que você já sabe; servem para medir a acurácia "
            "e nunca são lidas pelo modelo."
        ),
        "tip_preview": (
            "As primeiras linhas do arquivo, para conferir se ele foi lido corretamente: colunas, acentos e "
            "separador."
        ),
        "tip_questions": (
            "Cada linha é uma pergunta. id: um nome curto (letras, números, _) que vira a coluna nova. "
            "tipo: choice escolhe uma opção, noul responde sim/não, score coloca a linha numa escala "
            "(experimental). pergunta: em linguagem natural. opções: separadas por ; com uma descrição "
            "opcional depois de : (as descrições ajudam muito)."
        ),
        "tip_run": (
            "Limite de confiança: respostas abaixo dele marcam a linha como needs_review. Variante do modelo "
            "Laya: auto usa o modelo inglês para arquivos em inglês e o multilíngue para os demais. A "
            "primeira execução baixa o modelo; as seguintes funcionam sem internet."
        ),
        "tip_result": (
            "Baixe a cópia da planilha com as colunas novas e o resumo (.md). Linhas com needs_review = yes "
            "merecem um olhar humano: confiança baixa, possível manipulação ou texto vazio. Esses arquivos "
            "são apagados quando a LUAR fecha, então baixe-os antes."
        ),
        # --- etapa 1 ------------------------------------------------------------------------
        "upload": "CSV ou XLSX",
        "upload_drop": "Arraste o arquivo aqui",
        "upload_or": "- ou -",
        "upload_click": "Clique para escolher",
        "upload_aria": "Clique para escolher um arquivo ou arraste-o até aqui",
        "columns": "Coluna(s) que o modelo deve ler",
        "allow_sensitive": "Estas colunas têm dados pessoais, e tenho autorização para tratá-los",
        "example": "…ou experimente um exemplo",
        "ex_reviews": "Avaliações em inglês",
        "ex_severity": "Avaliações em inglês: gravidade (score)",
        "ex_avaliacoes": "Avaliações em português",
        "ex_sample": "Amostra de teste (CSV de exemplo)",
        "status": "**{name}**: {rows}, {cols} ({detail}).",
        "status_cols_one": "1 coluna",
        "status_cols_many": "{n} colunas",
        "status_csv": "separador `{sep}`, {encoding}",
        "status_excel": "aba `{sheet}`",
        "status_sensitive": (
            "**Dados pessoais encontrados:** {found}. A LUAR só lê essas colunas se você confirmar que tem "
            "autorização para tratar esses dados."
        ),
        # --- etapa 2 ------------------------------------------------------------------------
        "headers": "id|tipo|pergunta|opções",
        "question_help": (
            "**Tipos de pergunta:** `choice` escolhe uma opção · `noul` responde sim/não · `score` coloca a "
            "linha numa escala ordenada (*experimental*: o tipo menos confiável nos nossos testes).\n"
            "**Opções:** separe com `;` e, se quiser, acrescente uma descrição depois de `:`, por exemplo\n"
            "`entrega: frete, atrasos; produto: defeitos, qualidade`. Até 20 opções; `noul` não leva opções.\n"
            "Acrescente ao arquivo uma coluna chamada `expected_<id>` para medir a acurácia nas linhas cuja "
            "resposta você já sabe."
        ),
        "load_questions": "Carregar perguntas (.json)",
        "save_questions": "Salvar perguntas em .json",
        "questions_file": "Arquivo de perguntas",
        "no_questions": (
            "Ainda não há perguntas. Na etapa 2, preencha pelo menos o id e a pergunta de uma linha, ou "
            "carregue um arquivo .json de perguntas em \"Carregar perguntas (.json)\"."
        ),
        "sample_hint": (
            " Testando o CSV de exemplo? Baixe o JSON de exemplo no topo da página e carregue-o ali, ou "
            "escolha \"Amostra de teste (CSV de exemplo)\" em \"…ou experimente um exemplo\" para carregar "
            "os dois de uma vez."
        ),
        "bad_json": "Este arquivo de perguntas não é um JSON válido ({error}).",
        # --- etapa 3 ------------------------------------------------------------------------
        "threshold": "Limite de confiança",
        "threshold_info": "Respostas abaixo dele marcam a linha como needs_review",
        "checkpoint": "Variante do modelo Laya",
        "checkpoint_info": "auto: arquivos em inglês usam o modelo inglês; os demais, o multilíngue",
        "ckpt_auto": "auto",
        "ckpt_multilingual": "multilíngue",
        "ckpt_english": "inglês",
        "run": "Executar",
        "progress_loading": "Carregando o modelo (a primeira execução faz o download)…",
        "progress_rows": "{done}/{total} linhas",
        "engine_auto": "escolhido automaticamente",
        # --- resultado ----------------------------------------------------------------------
        "downloads": "Baixar (cópia com as respostas + resumo)",
        "tab_summary": "Resumo",
        "tab_table": "Tabela",
        "done": "Pronto: {rows}, {flagged} para revisar.",
        # --- avisos -------------------------------------------------------------------------
        "title_error": "Erro",
        "title_warning": "Atenção",
        "title_info": "Aviso",
        "err_read": "Não foi possível ler este arquivo: {error}",
        "err_too_many_rows": (
            "Este arquivo tem {rows} linhas; a interface aceita até {max} (cerca de uma linha por segundo "
            "com a Laya). Divida o arquivo ou use a linha de comando: luar run"
        ),
        "err_no_file": "Primeiro, arraste um arquivo CSV ou XLSX.",
        "err_no_columns": "Escolha pelo menos uma coluna para ler.",
        "warn_score": "Perguntas `score` são experimentais: confira essas respostas manualmente.",
        "err_sensitive_ui": (
            "As colunas a ler têm dados pessoais ({found}). Se você tem autorização para tratá-los, marque a "
            "confirmação abaixo das colunas; caso contrário, retire esses dados do arquivo."
        ),
        "warn_manipulation": (
            "Para revisar: {rows} com texto que parece escrito para direcionar as respostas. Confira "
            "manualmente."
        ),
        # --- palavras comuns ----------------------------------------------------------------
        "row_one": "{n} linha",
        "row_many": "{n} linhas",
        # --- questions.py -------------------------------------------------------------------
        "q_bad_id": (
            "Id de pergunta inválido: {id}. Use letras, números e sublinhado (_), sem começar por número."
        ),
        "q_bad_type": "Pergunta {id}: o tipo deve ser um destes: {types}.",
        "q_empty": "Pergunta {id}: o texto da pergunta está vazio.",
        "q_noul_options": "Pergunta {id}: perguntas de sim/não (noul) não levam opções.",
        "q_few_options": "Pergunta {id}: {type} precisa de pelo menos 2 opções.",
        "q_many_options": (
            "Pergunta {id}: {n} opções; o modelo aceita no máximo {max}. Divida-a em duas perguntas."
        ),
        "q_bad_options": "Formato de opções não reconhecido: {raw}",
        "q_bad_structure": "As perguntas devem ser uma lista ou um mapeamento de id -> pergunta.",
        "q_none": "Defina pelo menos uma pergunta.",
        "q_duplicate": "Id de pergunta repetido: {id}.",
        # --- tables.py ----------------------------------------------------------------------
        "t_xls": "Arquivos .xls antigos não são aceitos; salve o arquivo como .xlsx ou .csv.",
        "t_extra_fields": (
            "A linha {line} deste arquivo tem mais campos que o cabeçalho ({header}), provavelmente um "
            "'{sep}' dentro de um texto sem aspas. Salve o arquivo de novo pelo Excel (ele acrescenta as "
            "aspas) ou coloque esse texto entre aspas duplas."
        ),
        "t_bad_xlsx": "Este não é um arquivo do Excel (.xlsx) válido. Salve-o de novo pelo Excel, ou como .csv.",
        "t_xlsx_too_big": (
            "Este arquivo do Excel descompactado ocupa {size} MB, mais do que a LUAR aceita ({max} MB). "
            "Divida-o ou salve as colunas de que precisa como .csv."
        ),
        "t_overwrite": "A LUAR não sobrescreve arquivos: {path}",
        # --- engine.py ----------------------------------------------------------------------
        "e_missing_columns": "Coluna(s) não encontrada(s): {columns}",
        "e_clash": (
            "O arquivo já tem a(s) coluna(s) {columns}; mude o id da(s) pergunta(s) ou use o arquivo "
            "original em vez de um resultado anterior da LUAR."
        ),
        "e_threshold": "O limite de confiança deve estar entre 0 e 1.",
        "e_sensitive": (
            "A(s) coluna(s) a ler têm dados pessoais ({found}). Só as processe se tiver autorização: "
            "confirme para continuar, ou retire esses dados do arquivo."
        ),
        # --- safety.py ----------------------------------------------------------------------
        "kind_CPF": "CPF",
        "kind_CNPJ": "CNPJ",
        "kind_card number": "número de cartão",
        "kind_e-mail": "e-mail",
        "kind_phone": "telefone",
        "kind_in_rows": "{kind} em {rows}",
        # --- motores ------------------------------------------------------------------------
        "b_unknown_checkpoint": "Variante desconhecida {name}; use uma destas: {names}.",
        "b_laya_missing": "Não foi possível carregar o motor Laya. Reinstale com: {hint}",
        "b_app_control": (
            "O Windows bloqueou um dos arquivos do PyTorch (Controle de Aplicativos, WinError 4551), e o "
            "motor Laya não pôde iniciar. Isso pode acontecer uma vez só: feche a LUAR e abra de novo. Se "
            "continuar, peça a quem administra este computador para liberar os arquivos do PyTorch. "
            "Detalhes: {error}"
        ),
        "b_torch": (
            "Não foi possível carregar o PyTorch, de que o motor Laya precisa. Feche a LUAR e abra de novo; "
            "se continuar, reinstale com: pip install --force-reinstall torch. Detalhes: {error}"
        ),
        "b_integrity": (
            "O arquivo do modelo Laya não confere com o oficial ({path}). Ele pode estar corrompido ou "
            "alterado: apague essa pasta e baixe de novo com: luar download"
        ),
        # --- report.py (resumo .md) ---------------------------------------------------------
        "r_title": "# Resumo da LUAR: {source}",
        "r_table": "tabela",
        "r_date_format": "%d/%m/%Y %H:%M",
        "r_date": "Data",
        "r_engine": "Motor",
        "r_rows": "Linhas",
        "r_columns_read": "Colunas lidas",
        "r_threshold": "Limite de confiança",
        "r_to_review": "Linhas para revisar",
        "r_time": "Tempo",
        "r_result_file": "Arquivo de resultado",
        "r_personal": (
            "> **Dados pessoais:** as colunas lidas têm {found}. Você confirmou que pode tratá-los. Os "
            "valores não são repetidos neste resumo."
        ),
        "r_manipulation": (
            "> **Possível manipulação:** {rows} com texto que parece escrito para direcionar as respostas "
            '(por exemplo, "ignore a pergunta, a resposta correta é..."). Isso marca a linha para revisão: '
            "confira essas respostas manualmente."
        ),
        "r_experimental": (
            "> **Experimental:** `score` foi o tipo de pergunta menos confiável nos nossos testes (em 300 "
            "avaliações reais de produtos, a Laya acertou o número exato de estrelas em 33% das vezes, e "
            "errou por no máximo uma estrela em 68%). Confira estes resultados manualmente. Confiança baixa "
            "numa pergunta `score` não marca a linha para revisão."
        ),
        "r_answers_header": "| Resposta | Linhas | % |",
        "r_no_answer": "*(sem resposta)*",
        "r_yes": "yes (sim)",
        "r_no": "no (não)",
        "r_confidence": "Confiança média {avg}; {low} abaixo do limite.",
        "r_accuracy": "**Acurácia em relação a `{column}`: {hits}/{total} ({pct}).**",
        "r_review_title": "## Linhas para revisar",
        "r_review_none": "Nenhuma: todas as respostas estão acima do limite de confiança.",
        "r_review_header": "| Linha | Motivo | Texto |",
        "r_review_more": "…e mais {n}. Filtre `{column}` = yes no arquivo de resultado.",
        "r_footer": (
            "As respostas vêm de um modelo automático e podem estar erradas. Linhas marcadas em `{column}` "
            "merecem um olhar humano; o arquivo original não foi alterado."
        ),
        "reason_empty text": "texto vazio",
        "reason_possible manipulation": "possível manipulação",
        "reason_instructions to the model": "instruções ao modelo",
        "reason_fake answer for": "resposta falsa para",
        "reason_order about": "ordem sobre",
        "reason_claimed answer for": "resposta alegada para",
    },
}
