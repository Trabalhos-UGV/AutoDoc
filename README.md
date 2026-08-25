# AutoDoc

Sistema de organização automática de documentos — monitora uma pasta, lê o conteúdo dos arquivos, classifica, data e arquiva tudo de forma pesquisável, sem intervenção manual.

## Integrantes do Grupo

- Rafael Matheus Miers Sobrinho
- Thiago Soares
- Wellinton Slabey
- Gabriel Dos Santos

## Resumo da Automação Proposta

O AutoDoc resolve o problema da organização manual de documentos (contas, notas fiscais, comprovantes, contratos), que é lenta, repetitiva e não permite busca por conteúdo. O sistema monitora uma pasta definida pelo usuário e, ao detectar um novo arquivo, extrai o texto automaticamente — usando OCR quando o documento é uma imagem ou digitalização. Em seguida, classifica o documento por regras de palavras-chave (por exemplo, "kWh" indica conta de luz; "CNPJ" + "total" indica nota fiscal), extrai a data e armazena tudo em um banco de dados local pesquisável. Opcionalmente, o documento organizado também é copiado para uma pasta sincronizada, gerando backup automático. Com isso, basta digitar algo como "conta de luz março" para encontrar o arquivo na hora.

## Tecnologias e Ferramentas Utilizadas

- **Python** — linguagem principal do projeto
- **watchdog** — monitoramento da pasta de entrada
- **Tesseract OCR** — leitura de texto em imagens e documentos escaneados (opcional)
- **regex** — identificação e extração de datas
- **SQLite** — armazenamento e busca dos documentos processados
- **pywebview** — janela nativa do aplicativo, usando o motor do próprio sistema
- **pathlib** — compatibilidade de caminhos entre Windows, macOS e Linux

## Instruções de Instalação, Dependências e Execução

### Pré-requisitos

- Python 3.10 ou superior
- Tesseract OCR — **opcional**, necessário apenas para ler imagens e digitalizações. Sem ele o AutoDoc instala e funciona normalmente, apenas sem OCR:
  - **Windows:** baixar o instalador em https://github.com/UB-Mannheim/tesseract/wiki
  - **macOS:** `brew install tesseract`
  - **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr`

### Instalação

```bash
git clone https://github.com/Trabalhos-UGV/AutoDoc.git
cd AutoDoc
python3 instalar.py
```

O `instalar.py` abre o **instalador gráfico**, em janela própria, e executa seis
etapas de verdade: procura o Python da máquina, cria o ambiente virtual, instala
as dependências, procura o Tesseract, cria o banco com o índice de busca e
registra a pasta que será monitorada. Na última etapa ele cria o atalho do
sistema — um `AutoDoc.app` no macOS, um atalho no menu Iniciar no Windows, um
`.desktop` no Linux.

A partir daí o AutoDoc abre pelo ícone, como qualquer programa instalado.

> No macOS, o sistema bloqueia programas sem assinatura da Apple na primeira
> execução: clique com o botão direito no ícone e escolha **Abrir**.

Para instalar à mão, sem o instalador:

```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py app
```

### Configuração

Copie `config.example.json` para `config.json` na raiz do projeto e ajuste os caminhos:

```json
{
  "pasta_entrada": "~/Documentos/AutoDoc/entrada",
  "pasta_saida": "~/Documentos/AutoDoc/organizados",
  "pasta_backup": null,
  "banco": "autodoc.db",
  "extensoes": [".pdf", ".png", ".jpg", ".jpeg", ".txt"]
}
```

Se `config.json` não existir, o AutoDoc usa pastas padrão dentro do próprio projeto (`entrada/` e `organizados/`). Defina `pasta_backup` com uma pasta sincronizada (Drive, OneDrive) para gerar o backup automático; deixe `null` para desativar.

### Execução

Pelo ícone, ou pela linha de comando:

```bash
python main.py app                # abre a janela do AutoDoc (padrão)
python main.py monitorar          # monitora pela linha de comando, sem janela
python main.py buscar "luz março" # busca nos documentos indexados
python main.py listar             # últimos documentos processados
```

Com o AutoDoc aberto, qualquer arquivo colocado na pasta monitorada é lido,
classificado, datado, arquivado e indexado — e aparece na tela sozinho, sem
precisar recarregar nada.

Para experimentar sem usar documentos seus:

```bash
cp exemplos/*.txt entrada/
```

São cinco documentos fictícios, descritos em [exemplos/LEIA-ME.md](exemplos/LEIA-ME.md).
Um deles é ilegível de propósito, para mostrar o que o sistema faz quando não
tem confiança suficiente para classificar.

### Interface gráfica

O AutoDoc tem três telas, todas em HTML/CSS/JavaScript puro — sem framework, sem
etapa de build e sem nada vindo de CDN, porque o programa roda offline.

A **landing** é uma página web, como convém a uma página pública. As outras duas
são o programa em si e abrem em **janela do sistema**, sem barra de endereço e
sem aba — o mesmo arranjo do VS Code e do Spotify, que também são HTML desenhado
dentro da janela do próprio programa.

| Tela | Onde vive | O que faz |
| --- | --- | --- |
| Landing | [site/index.html](site/index.html) | Página pública. Detecta o sistema do visitante e oferece o download correspondente |
| Instalação | janela do sistema | Executa as seis etapas da instalação com barra de progresso e log ao vivo |
| Gerenciamento | janela do sistema | Lista os documentos, filtra por categoria, busca no conteúdo e explica cada classificação |

**Modo demonstração.** As telas também funcionam abertas soltas, sem o programa
rodando — aí usam dados de exemplo e **se identificam como tal**: a barra lateral
mostra "modo demonstração" em vez de "watchdog ativo". Serve para apresentar o
sistema sem instalá-lo. Para ver as três em sequência:

```bash
python3 ferramentas/servir_demo.py
```

## Estrutura do Projeto

```
autodoc/
  config.py         # leitura do config.json e criação das pastas
  db.py             # banco SQLite: indexação e busca
  extrator.py       # extração de texto (txt, PDF e OCR de imagens)
  classificador.py  # classificação por palavras-chave com pesos
  datas.py          # identificação da data do documento
  pipeline.py       # orquestra leitura, arquivamento e backup
  monitor.py        # monitoramento da pasta com watchdog
  instalacao/       # as seis etapas da instalação e o atalho no sistema
  web/servidor.py   # servidor local: API e eventos que alimentam a tela
  web/janela.py     # janela nativa do sistema
  web/estatico/     # as telas (HTML, CSS, JS, fontes)
site/               # landing page, publicável sozinha
exemplos/           # documentos fictícios para experimentar
recursos/           # ícone do aplicativo em cada formato
ferramentas/        # scripts de apoio ao desenvolvimento
instalar.py         # instalador gráfico
main.py             # interface de linha de comando
```

### Como o documento é processado

1. **Detecção** — o `monitor` percebe o arquivo novo e espera a cópia terminar.
2. **Deduplicação** — o hash SHA-256 do arquivo é comparado com o banco; se já foi indexado, é ignorado.
3. **Extração** — o texto é lido direto (`.txt`), da camada de texto do PDF, ou via OCR (imagens).
4. **Classificação** — cada categoria pontua conforme as palavras-chave encontradas, e o resultado vira uma **confiança de 0 a 1**. Abaixo de 0,60 o documento não é classificado.
5. **Data** — procura a data que estiver perto de um rótulo conhecido ("vencimento", "data de emissão"); sem rótulo, usa a primeira data do texto; sem data nenhuma, a modificação do arquivo.
6. **Arquivamento** — o arquivo vai para `organizados/<categoria>/<ano>/<mês>/`, sem sobrescrever homônimos. O que ficou abaixo do limiar vai para `organizados/_Revisar/`.
7. **Indexação e backup** — metadados, texto e a explicação da classificação vão para o SQLite, indexados com FTS5; se configurado, uma cópia vai para a pasta de backup.

### Categorias reconhecidas

`conta_luz`, `conta_agua`, `nota_fiscal`, `boleto`, `contrato`, `comprovante` e
`documento_pessoal`. O que não atinge o limiar de confiança vira
`nao_classificado` e vai para revisão manual.

As regras ficam em [autodoc/classificador.py](autodoc/classificador.py) e são
escritas com os termos que documentos reais trazem, e não com os que descrevem a
categoria: uma conta de luz não escreve "distribuidora", escreve "CEMIG" e
"total a pagar". A confiança combina duas coisas — quanta evidência da regra
apareceu e o quanto a categoria vencedora se destacou da segunda colocada.

### Funcionalidades adicionais implementadas

Além do escopo original da proposta, esta base inclui:

- **CLI com subcomandos** (`monitorar`, `buscar`, `listar`) em vez de apenas execução direta.
- **Busca por conteúdo, categoria, data ou nome do arquivo** em um único termo.
- **Deduplicação por hash**, evitando reprocessar o mesmo documento.
- **Processamento de pendentes**: arquivos já presentes na pasta quando o monitor sobe também são processados.
- **Arquivamento por categoria, ano e mês**, com renomeação automática em caso de nome repetido.
- **Confiança na classificação**, com limiar: o que fica abaixo vai para revisão em vez de ser chutado numa categoria.
- **Explicação de cada decisão**: regra acionada, palavras-chave encontradas, trajeto do arquivo e trecho lido.
- **Data escolhida por rótulo** — uma conta de luz tem três datas, e arquivar pela primeira erraria o mês.
- **Busca por conteúdo com FTS5**, o índice de texto do próprio SQLite.
- **Instalador gráfico** que executa etapas reais e cria o atalho no sistema.
- **Janela nativa**, sem navegador: o programa tem a própria janela e o próprio ícone.
- **Atualização ao vivo**: documentos novos aparecem na tela sozinhos, sem recarregar.
- **Três telas gráficas**, responsivas e navegáveis por teclado.
- **Funcionamento offline**: as fontes ficam versionadas no projeto, então nada depende de internet.
- **Modo demonstração** em todas as telas, para apresentar o sistema sem instalá-lo.
- **Detecção de sistema operacional** na landing, oferecendo o download correspondente.

## O que ainda não está pronto

Registrado aqui porque um projeto que só lista o que funciona não ajuda quem vai
continuá-lo:

- **O pacote para baixar pela landing.** Hoje a instalação é feita a partir do
  repositório, com `python3 instalar.py`. Falta empacotar isso num arquivo que a
  landing possa entregar — a página detecta que o pacote não existe e avisa, em
  vez de oferecer um link quebrado.
- **OCR de PDFs digitalizados.** A função existe em `extrator.py`, mas ainda não
  é acionada quando um PDF não tem camada de texto.
- **Calibragem das regras.** Estão ajustadas contra os documentos de `exemplos/`
  e ainda não foram testadas com contas e notas reais, que variam bastante de
  emissor para emissor.
- **Testes automatizados.** A verificação até aqui foi manual.
- **Windows e Linux.** O código é escrito para os três sistemas, mas só foi
  testado no macOS.
