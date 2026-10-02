# 🌙 LUAR: Local Utility for Automated Reviews

**Classifique uma planilha de textos com as suas próprias perguntas, no seu computador.**

Você arrasta uma planilha, escreve o que quer saber sobre cada linha ("Sobre o que é esta
avaliação?", "O cliente pede reembolso?") e a LUAR devolve uma cópia da planilha com as respostas
preenchidas, mais um relatório curto. Sem nuvem, sem cadastro, sem custo por uso: os seus dados
nunca saem da sua máquina.

*[Read in English](https://github.com/HayateV30/luar/blob/main/README.md)*

---

## Sumário

1. [O que a LUAR faz](#1-o-que-a-luar-faz)
2. [Antes de começar](#2-antes-de-começar)
3. [Instalação](#3-instalação)
4. [Primeiro uso, passo a passo](#4-primeiro-uso-passo-a-passo)
5. [Como escrever boas perguntas](#5-como-escrever-boas-perguntas)
6. [Entendendo os resultados](#6-entendendo-os-resultados)
7. [Conferindo se dá para confiar nas respostas](#7-conferindo-se-dá-para-confiar-nas-respostas)
8. [Escolhendo o motor: Laya ou LM Studio](#8-escolhendo-o-motor-laya-ou-lm-studio)
9. [Usando pela linha de comando](#9-usando-pela-linha-de-comando)
10. [Problemas comuns e perguntas frequentes](#10-problemas-comuns-e-perguntas-frequentes)
11. [Projetos relacionados, como contribuir e licença](#11-projetos-relacionados-como-contribuir-e-licença)

---

## 1. O que a LUAR faz

Imagine uma planilha de avaliações de clientes:

| id | review |
|---|---|
| 1 | The package arrived two weeks late and the box was crushed. |
| 2 | The blender stopped working after three days. I want my money back. |

Você faz duas perguntas: *"Sobre o que é principalmente esta avaliação?"* (entrega, produto,
atendimento ou preço) e *"O cliente pede o dinheiro de volta?"* (sim ou não). A LUAR devolve uma
**cópia** do arquivo com colunas novas:

| id | review | topic | topic_confidence | wants_refund | wants_refund_confidence | needs_review |
|---|---|---|---|---|---|---|
| 1 | The package arrived two weeks late… | delivery | 0.62 | no | 0.71 | yes |
| 2 | The blender stopped working… | product | 0.48 | yes | 0.88 | yes |

<sub>Resultado real do motor Laya no exemplo que acompanha o projeto. As quatro respostas estão certas,
mas o modelo ficou em dúvida sobre o assunto (abaixo do limite de 0,7), então as duas linhas foram
marcadas para uma conferência rápida.</sub>

- Cada resposta vem com uma **confiança** de 0 a 1.
- As linhas em que o modelo ficou em dúvida são marcadas em **`needs_review`**, para você saber onde
  uma pessoa deve olhar.
- Um **relatório** conta as respostas e lista as linhas a revisar.
- O seu arquivo original **nunca é alterado**.

Serve para respostas de pesquisa, avaliações de produtos, mensagens de atendimento, formulários
de feedback, anotações: qualquer coluna de texto que você leria e classificaria à mão.

---

## 2. Antes de começar

Você precisa de:

- **Python 3.10 ou mais recente.** Para conferir, abra um terminal (no Windows: *PowerShell* ou
  *Prompt de Comando*) e digite `python --version`. Se não tiver, instale pelo
  [python.org](https://www.python.org/downloads/) e marque *"Add python.exe to PATH"* na instalação.
- **Uma planilha** em `.xlsx` ou `.csv`, com o texto em uma ou mais colunas.
- **Espaço em disco e um download inicial**, que dependem do motor (veja abaixo). Depois do
  primeiro uso, tudo funciona sem internet.

A LUAR tem dois motores, o "cérebro" que lê os textos. Você pode instalar um ou os dois:

| Motor | O que é | Velocidade (notebook sem placa de vídeo) | Download |
|---|---|---|---|
| **Laya** | Um modelo de decisão aberto, feito para este tipo de pergunta: responde com probabilidades em vez de escrever texto. | Rápido: cerca de 0,6 s por linha | ~1,5 GB no primeiro uso (bibliotecas + modelo) |
| **LM Studio** | Qualquer modelo de chat rodando no app gratuito [LM Studio](https://lmstudio.ai) (testado com Qwen 3.5 4B). | Mais lento: cerca de 5 s por linha *para cada pergunta* | A LUAR em si tem ~200 MB; o modelo é baixado no LM Studio (Qwen 3.5 4B: 3,4 GB) |

Na dúvida, **comece pela Laya**: não precisa de outro programa e é bem mais rápida. A seção 8
explica quando o LM Studio vale a pena.

---

## 3. Instalação

Abra um terminal e rode **um** destes comandos:

```bash
pip install "luar[all]"
```
Tudo: interface web + motor Laya. **Recomendado.**

```bash
pip install "luar[ui]"
```
Só a interface web, para quem vai usar o LM Studio como motor (download menor).

Para acrescentar a Laya depois, rode `pip install "luar[laya]"`.

> **No Linux**, instale antes a versão para CPU do PyTorch, senão o pip baixa uma versão para
> placa de vídeo com vários GB: `pip install torch --index-url https://download.pytorch.org/whl/cpu`

---

## 4. Primeiro uso, passo a passo

### Passo 1: abra a LUAR

```bash
luar ui
```

O navegador abre em `http://127.0.0.1:7860`. Essa página é servida pelo seu próprio computador e não
fica acessível pela internet. Deixe o terminal aberto enquanto usa a LUAR; feche-o (ou aperte
`Ctrl+C`) para encerrar.

> Se o comando `luar` não for reconhecido, ou o Windows bloquear, use `python -m luar ui`.

### Passo 2: carregue a planilha

Arraste o arquivo para a caixa **CSV or XLSX** (ou clique nela para escolher o arquivo).

![Carregando a planilha](https://raw.githubusercontent.com/HayateV30/luar/main/docs/images/1-spreadsheet.png)

- A LUAR mostra quantas linhas e colunas encontrou e uma **prévia** das primeiras linhas.
- CSVs exportados pelo Excel em português (separador `;` e acentos) são detectados automaticamente.
- Em arquivos do Excel, é usada a **primeira aba**.
- Em **Column(s) the model should read**, marque a coluna com o texto. A LUAR já sugere a coluna com
  os textos mais longos. Se você marcar várias (por exemplo *título* e *descrição*), elas são lidas
  juntas.

**Só quer experimentar?** Se instalou a partir do repositório (veja a
[seção 11](#11-projetos-relacionados-como-contribuir-e-licença)), escolha um exemplo em
**…or try an example**. Se não, baixe
[avaliacoes.csv](https://raw.githubusercontent.com/HayateV30/luar/main/examples/avaliacoes.csv) e
[avaliacoes_perguntas.json](https://raw.githubusercontent.com/HayateV30/luar/main/examples/avaliacoes_perguntas.json)
e carregue-os como nos passos 2 e 3.

### Passo 3: escreva as perguntas

Cada linha da tabela de perguntas é uma pergunta:

![A tabela de perguntas](https://raw.githubusercontent.com/HayateV30/luar/main/docs/images/2-questions.png)

| Coluna | O que escrever | Exemplo |
|---|---|---|
| **id** | Um nome curto para a pergunta. Vira o nome da coluna nova. Só letras, números e `_`, sem espaços. | `assunto` |
| **type** | `choice`, `noul` ou `score` (veja a [seção 5](#5-como-escrever-boas-perguntas)). | `choice` |
| **question** | A pergunta, em linguagem simples. | `Sobre o que é principalmente esta avaliação?` |
| **options** | As respostas possíveis, separadas por `;`. Se quiser, acrescente uma descrição curta depois de `:`. Deixe vazio para `noul`. | `entrega: frete, atraso; produto: defeito, qualidade; preco` |

Clique numa célula para editar e use os controles de linha da tabela para acrescentar ou remover
perguntas.

**Dica:** as perguntas podem ser salvas e reaproveitadas. **Save questions as .json** baixa a
tabela; **Load questions (.json)** carrega de volta. Escrever as perguntas uma vez num arquivo
`.json` costuma ser o jeito mais fácil de manter muitas delas (formato na
[seção 5](#formato-do-arquivo-de-perguntas)).

### Passo 4: escolha as opções e rode

![Opções de execução](https://raw.githubusercontent.com/HayateV30/luar/main/docs/images/3-run.png)

- **Confidence threshold** (limite de confiança, padrão `0,7`): toda resposta abaixo dele é marcada
  em `needs_review`. Aumente para revisar mais linhas, diminua para revisar menos.
- **Engine** (motor): Laya ou LM Studio (veja a [seção 8](#8-escolhendo-o-motor-laya-ou-lm-studio)).
- **Laya model variant** (variante do modelo): deixe em `auto`. Ele usa o modelo inglês para
  arquivos em inglês e o multilíngue para os demais.

Clique em **Run**. Na primeira vez a Laya baixa o modelo, o que leva alguns minutos; depois, as
execuções começam em segundos.

### Passo 5: baixe os resultados

![Resultados](https://raw.githubusercontent.com/HayateV30/luar/main/docs/images/4-result.png)

Em **Result** aparecem dois arquivos para baixar:

- **`<seu arquivo>_luar.csv` ou `.xlsx`**: a sua planilha com as colunas novas.
- **`<seu arquivo>_luar_summary.md`**: o relatório (também aparece na página, na aba **Summary**).
  `.md` é texto simples e abre em qualquer editor de texto.

A aba **Table** mostra a planilha resultante na própria página.

---

## 5. Como escrever boas perguntas

A qualidade das respostas depende principalmente de como as perguntas são escritas.

### Os três tipos de pergunta

| Tipo | Use quando… | Resposta | Exemplo |
|---|---|---|---|
| `choice` | a resposta é **uma de uma lista** (de 2 a 20 opções) | uma das suas opções | *Sobre o que é a avaliação?* entrega / produto / atendimento / preço |
| `noul` | a resposta é **sim ou não** | `yes` ou `no` | *O cliente pede o dinheiro de volta?* |
| `score` ⚠️ | a resposta é **um nível numa escala** | um dos seus níveis, do mais baixo ao mais alto | *Qual a gravidade do problema?* nenhuma / leve / grave |

> ⚠️ **`score` é experimental.** Foi o tipo menos confiável nos testes: 71% (Laya) e 79%
> (LM Studio) de concordância com respostas dadas à mão. Prefira `choice` ou `noul` quando puder e
> confira os resultados de `score` você mesmo.

### Dicas

1. **Descreva as opções.** `preco: valor, custo-benefício, cobranças` funciona bem melhor que só
   `preco`. A descrição diz ao modelo o que pertence a cada opção.
2. **Faça as opções cobrirem tudo, sem se sobrepor.** Se algumas linhas podem não caber em nenhuma,
   acrescente uma opção `outro`. Se duas opções significam quase a mesma coisa, junte-as.
3. **Uma coisa por pergunta.** Em vez de *"O cliente está bravo e pede reembolso?"*, faça duas
   perguntas `noul`.
4. **Seja específico.** *"O cliente pede **explicitamente** o dinheiro de volta?"* rende respostas
   melhores que *"Reembolso?"*.
5. **Até cerca de 20 opções.** Para listas maiores, divida numa pergunta geral e outra detalhada.
6. **A ordem das opções pode mudar algumas respostas.** Se os resultados parecerem puxar para uma
   opção, troque a ordem e compare (a seção 7 mostra como medir).
7. **Escreva no idioma dos seus dados.** Perguntas e opções podem estar em qualquer idioma que o
   motor entenda.

### Formato do arquivo de perguntas

Um arquivo de perguntas é uma lista em formato JSON. Este é o arquivo do exemplo em português:

```json
[
  {
    "id": "assunto",
    "type": "choice",
    "question": "Sobre o que é principalmente esta avaliação?",
    "options": {
      "entrega": "frete, atraso, transportadora, estado do pacote",
      "produto": "qualidade, defeito, funcionamento do item",
      "atendimento": "suporte, trocas, como a loja tratou o pedido",
      "preco": "valor, custo-benefício, cobranças"
    }
  },
  {
    "id": "quer_reembolso",
    "type": "noul",
    "question": "O cliente pede explicitamente o dinheiro de volta?"
  }
]
```

`options` pode ser uma lista simples (`["positivo", "neutro", "negativo"]`) ou uma lista com
descrições (`{"entrega": "frete, atraso", …}`). Em `score`, liste os níveis do mais baixo ao mais
alto.

---

## 6. Entendendo os resultados

### Colunas novas na planilha

Para cada pergunta (aqui, uma pergunta com id `assunto`):

| Coluna | Significado |
|---|---|
| `assunto` | A resposta: uma das suas opções, ou `yes`/`no` nas perguntas `noul`. |
| `assunto_confidence` | O quanto o motor tem certeza, de 0 a 1. `0.95` = muita certeza; `0.40` = chutando entre opções. |

E duas colunas para a linha inteira:

| Coluna | Significado |
|---|---|
| `needs_review` | `yes` se alguma resposta da linha ficou abaixo do limite de confiança. Filtre por ela para achar as linhas que uma pessoa deve conferir. |
| `review_reasons` | Quais perguntas ficaram em dúvida (por exemplo `assunto, quer_reembolso`), ou `empty text` se a linha não tinha texto. |

Linhas sem texto não são enviadas ao motor; elas ficam marcadas em `needs_review` com o motivo `empty text`.

### O relatório

O arquivo `_summary.md` traz:

- **A execução:** data, motor, número de linhas, colunas lidas, limite de confiança e tempo gasto.
- **Uma seção por pergunta:** quantas linhas receberam cada resposta (quantidade e %), a confiança
  média e quantas respostas ficaram abaixo do limite.
- **O acerto**, se o seu arquivo tiver colunas de gabarito (próxima seção).
- **Linhas a revisar:** número da linha (como no Excel, contando o cabeçalho como linha 1), quais
  perguntas ficaram em dúvida e o começo do texto. São listadas até 50 linhas; para as demais,
  filtre `needs_review` no arquivo de resultado.

### Quanto confiar na confiança

A confiança é uma probabilidade de verdade calculada pelo motor, não um número inventado pelo modelo.
Ela é um bom **guia** de onde os erros são mais prováveis, mas o modelo ainda pode errar com
convicção. Por isso a próxima seção é importante.

---

## 7. Conferindo se dá para confiar nas respostas

Antes de usar a LUAR num arquivo grande, meça o acerto numa amostra cujas respostas você já conhece:

1. **Separe de 20 a 50 linhas** e responda as perguntas você mesmo.
2. **Acrescente uma coluna por pergunta** com o nome `expected_` + o id da pergunta. Para a pergunta
   `assunto`, a coluna é `expected_assunto`. Preencha com as suas respostas.
   - Nas perguntas `noul`, valem `sim`/`não`, `yes`/`no`, `true`/`false` e `1`/`0`.
   - Linhas deixadas em branco na coluna `expected_` simplesmente não entram na conta.
3. **Rode a LUAR** nesse arquivo. O relatório passa a mostrar, para cada pergunta, uma linha como
   **Accuracy against `expected_assunto`: 9/10 (90%)**.
4. Se o acerto estiver baixo, **melhore as perguntas** (seção 5), experimente o **outro motor** e
   rode de novo até ficar satisfeito. Depois, rode o arquivo completo.

As colunas `expected_` nunca são mostradas ao modelo, então não "entregam" as respostas.

---

## 8. Escolhendo o motor: Laya ou LM Studio

| | Laya | LM Studio (Qwen 3.5 4B) |
|---|---|---|
| Acerto nos nossos exemplos `choice`/`noul` | 86–100% | 100% |
| Acerto no nosso exemplo `score` | 71% | 79% |
| Tempo por linha, 3 perguntas (notebook sem placa de vídeo) | ~0,6 s | ~14 s |
| Precisa de outro programa | Não | Sim, o LM Studio |
| Melhor para | arquivos grandes, passadas rápidas | arquivos menores, quando a precisão importa mais |

Uma boa rotina: **teste os dois na sua amostra com colunas `expected_`** (seção 7) e fique com o que
acertar o suficiente numa velocidade aceitável para você.

### Configurando o LM Studio

1. Instale o [LM Studio](https://lmstudio.ai) e baixe nele um modelo de chat (por exemplo
   `qwen3.5-4b`). Modelos maiores costumam acertar mais, mas são mais lentos.
2. Carregue o modelo e ligue o servidor local, no app (aba *Developer* → *Start Server*) ou num
   terminal:
   ```bash
   lms server start
   lms load qwen3.5-4b
   ```
3. Na LUAR, escolha **LM Studio** como motor. Clique em **List LM Studio models** para escolher um
   modelo, ou deixe vazio para usar o que já está carregado.

Bom saber:

- A LUAR se conecta em `http://localhost:1234/v1`. Se o seu servidor do LM Studio usa outro
  endereço, defina a variável de ambiente `LUAR_LMSTUDIO_URL`.
- Se você ativou **Require API key** no LM Studio, coloque a chave numa variável de ambiente chamada
  `LMSTUDIO_API_KEY` (nunca num arquivo que você compartilha).
- A LUAR desliga o "raciocínio" do modelo e pede uma resposta de uma letra só, então cada pergunta
  é rápida e a confiança vem das próprias probabilidades do modelo.
- A LUAR lê as probabilidades dos tokens do modelo, então mantenha o LM Studio atualizado (testado
  com a versão de outubro de 2026).

---

## 9. Usando pela linha de comando

Tudo o que a interface web faz também pode ser feito num terminal, o que ajuda a repetir o mesmo
trabalho ou automatizá-lo.

```bash
luar columns minha_planilha.xlsx
```
Lista as colunas de um arquivo, com um valor de exemplo de cada.

```bash
luar run minha_planilha.xlsx -q perguntas.json -c avaliacao
```
Classifica o arquivo. O resultado e o relatório são salvos **ao lado do arquivo original**, como
`minha_planilha_luar.xlsx` e `minha_planilha_luar_summary.md`. Se esses nomes já existirem, a LUAR
acrescenta `_2`, `_3`… em vez de sobrescrever.

| Opção | O que faz |
|---|---|
| `-q`, `--questions` | O arquivo de perguntas (`.json`). Obrigatório. |
| `-c`, `--columns` | A(s) coluna(s) a ler. Pode ser mais de uma: `-c titulo descricao`. Obrigatório. |
| `-t`, `--threshold` | Limite de confiança, de 0 a 1 (padrão `0.7`). |
| `-o`, `--out-dir` | Salva os resultados em outra pasta. |
| `--sheet` | Aba do Excel a ler (padrão: a primeira). |
| `-e`, `--engine` | `laya` ou `lmstudio` (padrão: Laya se estiver instalada, senão LM Studio). |
| `--checkpoint` | Laya: `auto` (padrão), `multilingual` ou `english`. |
| `--device` | Laya: `cpu` ou `cuda` (padrão: automático). |
| `--model` | LM Studio: id do modelo (padrão: o modelo carregado). |
| `--lmstudio-url` | LM Studio: endereço do servidor. |

Usando a LUAR pelo Python:

```python
from luar import load_questions, run_file
from luar.backends import make_backend

backend = make_backend("laya")   # ou make_backend("lmstudio")
result = run_file("dados.csv", load_questions("perguntas.json"), ["texto"], backend)
print(result.table_path, result.summary_path)
```

---

## 10. Problemas comuns e perguntas frequentes

**Os meus dados saem do computador?**
Não. Os dois motores rodam localmente. Os únicos downloads são os programas e os modelos, na
primeira vez.

**O comando `luar` não é reconhecido, ou o Windows diz "acesso negado".**
Use `python -m luar ui` (ou `python -m luar run …`). Algumas configurações de segurança do Windows
bloqueiam os pequenos executáveis que o pip cria; passar pelo `python` evita isso.

**"Old .xls files are not supported".**
Abra o arquivo no Excel e salve como `.xlsx` (ou `.csv`).

**Os acentos aparecem errados no resultado.**
O CSV de resultado é salvo em UTF-8, que o Excel lê corretamente quando você abre o arquivo com dois
cliques. Se importar manualmente (*Dados → De Texto/CSV*), escolha *UTF-8*.

**"The file already has column(s) …".**
Provavelmente você está rodando a LUAR num arquivo que já é um resultado da LUAR. Use o arquivo
original, ou mude os ids das perguntas.

**"The Laya engine is not installed".**
Rode `pip install "luar[laya]"`, ou troque o motor para LM Studio.

**"Could not reach LM Studio".**
Ligue o servidor no LM Studio (*Developer → Start Server*, ou `lms server start`) e carregue um modelo.

**"LM Studio did not return token probabilities".**
Atualize o LM Studio para uma versão recente.

**Está lento.**
A Laya leva de 30 a 60 segundos para carregar no início de cada sessão; depois disso é rápida. O
LM Studio leva alguns segundos por pergunta em cada linha: use menos perguntas, um arquivo menor ou
a Laya.

**Muitas linhas ficam marcadas em `needs_review`.**
Melhore as descrições das opções (seção 5), meça o acerto com colunas `expected_` (seção 7), ou
diminua o limite de confiança se o acerto já estiver bom.

**Quais idiomas funcionam?**
O modelo multilíngue da Laya entende muitos idiomas (aqui foi testado em português e inglês). No
LM Studio, depende do modelo escolhido.

---

## 11. Projetos relacionados, como contribuir e licença

**Projetos relacionados.** Outras ferramentas abertas em torno da Laya, caso alguma sirva melhor
para você:

- [laya-studio](https://github.com/felix-homelab/laya-studio): plataforma web completa (Docker +
  PostgreSQL) com avaliação em lote, monitor de calibração, fila de revisão e automações. Boa para
  montar um sistema de decisão para uma equipe; a LUAR é para quem só quer a planilha classificada.
- [vgi-laya](https://github.com/lmangani/vgi-laya): a Laya como funções SQL dentro do DuckDB. Boa se
  os seus dados já estão num banco e você usa SQL.
- Mais no diretório [laya.tools](https://laya.tools).

**Instalando a partir do repositório** (inclui os exemplos e o seletor de exemplos):

```bash
git clone https://github.com/HayateV30/luar.git
cd luar
pip install -e ".[all]"
```

**Como contribuir.** Como a LUAR funciona por dentro, como rodar os testes e como acrescentar um
motor: [CONTRIBUTING.md](https://github.com/HayateV30/luar/blob/main/CONTRIBUTING.md) (em inglês).
Bugs e ideias: [issues](https://github.com/HayateV30/luar/issues).

**Licença.** MIT para o código da LUAR. A Laya (pacote e pesos do modelo) é um projeto separado, com
licença própria; consulte o [model card](https://huggingface.co/convaiinnovations/laya) antes de
redistribuí-la.
