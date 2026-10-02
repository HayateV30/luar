# 🌙 LUAR: Local Utility for Automated Reviews

Arraste uma planilha, diga o que quer saber sobre cada linha e receba uma cópia com as respostas
e um resumo em Markdown. Tudo roda **no seu computador**: sem nuvem, sem enviar dados a ninguém.

O LUAR tem dois motores locais:

| Motor | O que é | Velocidade* | Quando usar |
|---|---|---|---|
| **Laya** (padrão) | a [Laya](https://huggingface.co/convaiinnovations/laya), modelo de decisão aberto no estilo do Jev: responde perguntas *estruturadas* com uma probabilidade, em vez de gerar texto | ~0,6 s por linha | arquivos grandes, passadas rápidas |
| **LM Studio** | qualquer modelo de chat rodando no [LM Studio](https://lmstudio.ai) (testado com Qwen 3.5 4B) | ~5 s por linha *por pergunta* | arquivos menores, quando a precisão importa mais |

<sub>*Num notebook sem placa de vídeo dedicada. Nos dois motores, a confiança é uma probabilidade de verdade.</sub>

*[Read in English](https://github.com/HayateV30/luar/blob/main/README.md)*

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

> ⚠️ **`score` é experimental.** Foi o tipo menos confiável nos testes: 71% (Laya) e 79% (LM Studio)
> de concordância com a classificação manual no exemplo de gravidade. Prefira `choice` ou `noul`,
> ou confira os resultados de `score` à mão.

## Instalação

Requer Python 3.10+. A primeira execução baixa o modelo da Laya (algumas centenas de MB) do Hugging Face.

```bash
pip install "luar[ui]"
```

Sem o `[ui]`, instala só a linha de comando. Para ter os exemplos (e o seletor de exemplos na
interface web), instale a partir do repositório:

```bash
git clone https://github.com/HayateV30/luar.git
cd luar
pip install -e ".[ui]"
```

## Como usar

**Interface web:** `luar ui` abre `http://127.0.0.1:7860` (só local). Arraste o arquivo, marque a(s)
coluna(s), preencha as perguntas (ou carregue um `.json`, ou escolha um exemplo), escolha o motor e
clique em **Run**.

**Linha de comando:**

```bash
luar run examples/avaliacoes.csv -q examples/avaliacoes_perguntas.json -c avaliacao
```

Para usar o LM Studio, acrescente `--engine lmstudio`. O formato do arquivo de perguntas e as opções
da linha de comando estão no [README em inglês](https://github.com/HayateV30/luar/blob/main/README.md).

### Usando o LM Studio

1. Instale o [LM Studio](https://lmstudio.ai) e baixe um modelo de chat (ex.: `qwen3.5-4b`).
2. Ligue o servidor e carregue o modelo, no app (*Developer → Start Server*) ou pela linha de comando:
   ```bash
   lms server start
   lms load qwen3.5-4b
   ```
3. Rode com `--engine lmstudio` (ou escolha **LM Studio** na interface web).

O endereço padrão é `http://localhost:1234/v1` (mude com `LUAR_LMSTUDIO_URL`). Se você ativou
*Require API key* no LM Studio, coloque a chave na variável de ambiente `LMSTUDIO_API_KEY`, nunca num
arquivo versionado. O LUAR desliga o "raciocínio" do modelo (`reasoning_effort: none`): cada resposta
é um único token.

## Confira antes de confiar

1. Classifique 20 a 50 linhas à mão em colunas chamadas **`expected_<id>`** (ex.: `expected_assunto`).
   Para `noul`, valem `sim/não`, `yes/no`, `true/false` e `1/0`.
2. Rode o LUAR. O resumo mostra a **acurácia contra `expected_<id>`** de cada pergunta.
3. Ajuste o texto das perguntas, as descrições das opções ou o limite até ficar satisfeito.

As colunas `expected_*` nunca são oferecidas como entrada para o modelo.

## Dicas dos testes

- **Acerto nos exemplos:** a Laya fez 86–100% em `choice`/`noul`; o LM Studio com Qwen 3.5 4B fez
  100% em todos, mas levou mais de 20 vezes mais tempo (3 perguntas: ~14 s contra ~0,6 s por linha).
- **Idioma (Laya):** o modo `auto` usa o modelo `english` para arquivos em inglês e o `multilingual` para os demais.
- **Descreva as opções:** `"preco": "valor, custo-benefício, cobranças"` funciona melhor que só `"preco"`.
- **A ordem das opções pode mudar as respostas:** teste com `expected_*`.
- **Até cerca de 20 opções por pergunta:** divida listas maiores em duas perguntas.
- **Confiança é pista, não garantia:** use `needs_review` para decidir onde uma pessoa deve olhar.

## Licença

MIT para o código do LUAR. A Laya (pacote e pesos do modelo) é um projeto separado, com licença
própria; consulte o [model card](https://huggingface.co/convaiinnovations/laya) antes de redistribuí-la.
