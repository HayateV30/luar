# 🌙 LUAR: Local Utility for Automated Reviews

Arraste uma planilha, diga o que quer saber sobre cada linha e receba uma cópia com as respostas
e um resumo em Markdown. Tudo roda **no seu computador**: sem chave de API, sem enviar dados a ninguém.

O LUAR é uma camada simples sobre a [Laya](https://huggingface.co/convaiinnovations/laya), um modelo
de decisão aberto e local no estilo do Jev. Em vez de gerar texto, a Laya responde perguntas
*estruturadas* sobre um texto, com uma confiança para cada resposta.

*[Read in English](README.md)*

## O que faz

| Você fornece | Você recebe |
|---|---|
| Um arquivo `.csv` ou `.xlsx` | `<nome>_luar.csv/.xlsx`: uma **cópia** com colunas novas (o original nunca é alterado) |
| A(s) coluna(s) a ler | Para cada pergunta: `<id>` (a resposta) e `<id>_confidence` (0–1) |
| Suas perguntas | `needs_review` = `yes` quando alguma resposta fica abaixo do limite de confiança, e `review_reasons` |
| | `<nome>_luar_summary.md`: contagem por resposta, linhas a revisar, acurácia (veja abaixo) |

CSVs exportados pelo Excel em português (separador `;`, acentos em Windows-1252) são detectados
automaticamente, e a cópia mantém o mesmo separador.

### Tipos de pergunta

| Tipo | Responde | Exemplo |
|---|---|---|
| `choice` | uma das suas opções (2 a 20) | *Sobre o que é a avaliação?* entrega / produto / atendimento / preço |
| `noul` | `yes` ou `no` | *O cliente pede o dinheiro de volta?* |
| `score` ⚠️ | um nível numa escala ordenada | *Qual a gravidade?* baixa / média / alta |

> ⚠️ **`score` é experimental.** Nos nossos testes ele não foi confiável sem fine-tuning: as respostas
> pendiam para uma ponta da escala. Prefira `choice` ou `noul`, ou confira os resultados de `score` à mão.

## Instalação

Requer Python 3.10+. A primeira execução baixa o modelo da Laya (algumas centenas de MB) do Hugging Face.

```bash
git clone https://github.com/HayateV30/luar.git
cd luar
pip install -e ".[ui]"
```

## Como usar

**Interface web:** `luar ui` abre `http://127.0.0.1:7860` (só local). Arraste o arquivo, marque a(s)
coluna(s), preencha as perguntas (ou carregue um `.json`, ou escolha um exemplo) e clique em **Run**.

**Linha de comando:**

```bash
luar run examples/avaliacoes.csv -q examples/avaliacoes_perguntas.json -c avaliacao
```

O formato do arquivo de perguntas e as opções da linha de comando estão no [README em inglês](README.md).

## Confira antes de confiar

1. Classifique 20 a 50 linhas à mão em colunas chamadas **`expected_<id>`** (ex.: `expected_assunto`).
   Para `noul`, valem `sim/não`, `yes/no`, `true/false` e `1/0`.
2. Rode o LUAR. O resumo mostra a **acurácia contra `expected_<id>`** de cada pergunta.
3. Ajuste o texto das perguntas, as descrições das opções ou o limite até ficar satisfeito.

As colunas `expected_*` nunca são oferecidas como entrada para o modelo.

## Dicas dos testes

- **Idioma:** o modo `auto` usa o modelo `english` para arquivos em inglês e o `multilingual` para os demais.
- **Descreva as opções:** `"preco": "valor, custo-benefício, cobranças"` funciona melhor que só `"preco"`.
- **A ordem das opções pode mudar as respostas:** teste com `expected_*`.
- **Até cerca de 20 opções por pergunta:** divida listas maiores em duas perguntas.
- **Confiança é pista, não garantia:** use `needs_review` para decidir onde uma pessoa deve olhar.

## Licença

MIT para o código do LUAR. A Laya (pacote e pesos do modelo) é um projeto separado, com licença
própria; consulte o [model card](https://huggingface.co/convaiinnovations/laya) antes de redistribuí-la.
