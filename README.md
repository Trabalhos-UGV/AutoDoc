# AutoDoc

Sistema de organização automática de documentos — monitora uma pasta, lê o conteúdo dos arquivos, classifica, data e arquiva tudo de forma pesquisável, sem intervenção manual.

## Integrantes do Grupo

- Rafael Matheus Miers Sobrinho
- Thiago Soares
- Wellinton Slabey
- Gabriel Dos Santos

## Resumo da Automação Proposta

O AutoDoc resolve o problema da organização manual de documentos (contas, notas fiscais, comprovantes, contratos), que é lenta, repetitiva e não permite busca por conteúdo. O sistema monitora uma pasta definida pelo usuário e, ao detectar um novo arquivo, extrai o texto automaticamente — usando OCR quando o documento é uma imagem ou digitalização. Em seguida, classifica o documento por regras de palavras-chave (por exemplo, "kWh" indica conta de luz; "CNPJ" + "total" indica nota fiscal), extrai a data e arquiva o documento numa pasta organizada e pesquisável. Opcionalmente, o documento organizado também é copiado para uma pasta sincronizada, gerando backup automático. Com isso, basta digitar algo como "conta de luz março" para encontrar o arquivo na hora.

## Tecnologias e Ferramentas Utilizadas

- **Python** — linguagem principal do projeto
- **watchdog** — monitoramento da pasta de entrada
- **Tesseract OCR** — leitura de texto em imagens e documentos escaneados (opcional)
- **regex** — identificação e extração de datas
- **Biblioteca padrão do Python** — o catálogo dos documentos e o índice de busca, sem banco de dados
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

O `instalar.py` abre o **instalador gráfico**, em janela própria. A tela primeiro
mostra qual pasta será vigiada e deixa escolher outra; a instalação só começa
quando você confirma. Aí ela executa seis etapas de verdade: procura o Python da
máquina, cria o ambiente virtual, instala as dependências, procura o Tesseract,
prepara a pasta organizada e registra a pasta monitorada. Na última etapa cria o
atalho do sistema — um `AutoDoc.app` no macOS, um atalho no menu Iniciar no
Windows, um `.desktop` no Linux.

Trocar a pasta depois de instalado reexecuta as etapas, que são idempotentes: a
escolha vale de verdade, e não só na tela.

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

O instalador grava o `config.json` com a pasta que você escolher. Para ajustar à
mão, copie `config.example.json` para `config.json` na raiz do projeto:

```json
{
  "pasta_entrada": "~/Documentos/AutoDoc/entrada",
  "pasta_saida": "~/Documentos/AutoDoc/organizados",
  "pasta_backup": null,
  "extensoes": [".pdf", ".png", ".jpg", ".jpeg", ".txt"]
}
```

Sem `config.json`, o AutoDoc vigia `~/Documentos/AutoDoc/entrada` — fora do
repositório, como convém a um programa instalado. Omitir `pasta_saida` faz a
pasta organizada nascer ao lado da vigiada. Defina `pasta_backup` com uma pasta
sincronizada (Drive, OneDrive) para gerar o backup automático; deixe `null` para
desativar.

Não há caminho de banco de dados para configurar: escolher a pasta de saída já é
escolher onde ficam os dados.

### Execução

Pelo ícone, ou pela linha de comando:

```bash
python main.py app                # abre a janela do AutoDoc (padrão)
python main.py monitorar          # monitora pela linha de comando, sem janela
python main.py buscar "luz março" # busca nos documentos indexados
python main.py listar             # últimos documentos processados
```

Com o AutoDoc aberto, qualquer arquivo colocado na pasta monitorada é lido,
classificado, datado, arquivado e fichado — e aparece na tela sozinho, sem
precisar recarregar nada.

### Onde ficam os dados

Tudo dentro da pasta organizada:

```
organizados/
  conta_luz/2026/03/conta_energia_marco.txt   <- o documento, que é o que importa
  _Revisar/scan0031.txt                        <- o que não deu para classificar
  _Duplicados/                                 <- cópias do que já estava arquivado
  .autodoc/catalogo.jsonl                      <- as fichas; refazíveis a qualquer momento
```

Não há banco de dados. A pasta é a verdade e o catálogo é só um caderno de
fichas sobre ela: apagar `.autodoc/` não perde nada, porque na abertura seguinte
o AutoDoc varre as pastas e refaz as fichas. Apagar a pasta apaga tudo — que é o
comportamento esperado de um programa que não guarda nada em outro lugar.

Para experimentar sem usar documentos seus:

```bash
cp exemplos/*.txt entrada/
```

São cinco documentos fictícios, descritos em [exemplos/LEIA-ME.md](exemplos/LEIA-ME.md).
Um deles é ilegível de propósito, para mostrar o que o sistema faz quando não
tem confiança suficiente para classificar.

### Testes

```bash
python -m unittest discover -s testes     # 357 testes, ~8 segundos
python3 ferramentas/cobertura.py          # a cobertura, módulo a módulo
```

Usam só a biblioteca padrão — rodar os testes não pede nada além do que o
AutoDoc já pede, e cada um trabalha numa pasta temporária própria.

| Arquivo | O que cobre |
| --- | --- |
| `test_classificador.py` | categorias, confiança, limiar, empate e duplo sentido |
| `test_datas.py` | os três formatos, data inválida e a escolha pelo rótulo |
| `test_catalogo.py` | fichas, dedupe por conteúdo, busca por prefixo e sem acento |
| `test_reconciliacao.py` | a pasta como verdade: catálogo apagado, arquivo apagado, arquivo posto à mão |
| `test_pipeline.py` | o caminho completo do documento, dedupe, correção manual e documento ilegível |
| `test_extrator.py` | texto, PDF, OCR de digitalizado e as dependências opcionais ausentes |
| `test_monitor.py` | arquivos ignorados, espera pela cópia e os eventos da pasta |
| `test_servidor.py` | a API das telas, o fluxo de eventos e a porta ocupada |
| `test_instalacao.py` | as seis etapas e a pasta escolhida chegando ao `config.json` |
| `test_instalador_servidor.py` | o estado do instalador gráfico e as rotas dele |
| `test_atalho.py` | o `.app`, o `.desktop` e o `.lnk` gerados |
| `test_janela.py` | a janela nativa e a queda para o navegador |
| `test_config.py` | padrões, pasta de saída e a gravação da escolha |
| `test_main.py` | a linha de comando inteira |

**A cobertura é de 100% das linhas** (1800 de 1807). As sete que faltam ficam de
fora por motivo, e não por esquecimento:

- os caminhos **só do Windows** (`%APPDATA%`, `venv\Scripts\`) — não dá para
  exercitá-los no macOS, e fingir que dá seria pior;
- o **ping de 15 segundos** que mantém o fluxo de eventos vivo — cobri-lo
  exigiria um teste que espera quinze segundos;
- os dois `if __name__ == "__main__"`.

O medidor é `ferramentas/cobertura.py`, escrito com o `trace` da biblioteca
padrão. Ele registra o rastreador também para as threads novas
(`threading.settrace`), sem o que o servidor e o monitoramento ficam invisíveis
e o `servidor.py` aparece com 35% quando na verdade tem 100%.

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
  catalogo.py       # fichas dos documentos e busca — sem banco de dados
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
2. **Deduplicação** — o hash SHA-256 do conteúdo é comparado com o catálogo; se aquele documento já foi arquivado, a cópia vai para `organizados/_Duplicados/` em vez de ser processada de novo.
3. **Extração** — o texto é lido direto (`.txt`), da camada de texto do PDF, ou via OCR — de imagens e também de PDFs digitalizados, que não têm camada de texto.
4. **Classificação** — cada categoria pontua conforme as palavras-chave encontradas, e o resultado vira uma **confiança de 0 a 1**. Abaixo de 0,60 o documento não é classificado.
5. **Data** — procura a data que estiver perto de um rótulo conhecido ("vencimento", "data de emissão"); sem rótulo, usa a primeira data do texto; sem data nenhuma, a modificação do arquivo.
6. **Arquivamento** — o arquivo vai para `organizados/<categoria>/<ano>/<mês>/`, sem sobrescrever homônimos. O que ficou abaixo do limiar vai para `organizados/_Revisar/`.
7. **Ficha e backup** — metadados, texto e a explicação da classificação viram uma ficha em `organizados/.autodoc/catalogo.jsonl`; se configurado, uma cópia vai para a pasta de backup.

O que não pôde ser lido — PDF corrompido, imagem ilegível, OCR indisponível — também sai da pasta de entrada e vai para `_Revisar/`, com o motivo escrito no trajeto. Um arquivo deixado para trás seria reexaminado a cada abertura e ninguém saberia que ele existe.

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
- **Catálogo em pasta, sem banco de dados.** O que o AutoDoc sabe fica em `organizados/.autodoc/catalogo.jsonl`, uma ficha por linha em texto puro. É um cache, não a verdade: apagar o arquivo não perde nada, porque na abertura seguinte o programa varre as pastas e o remonta.
- **A pasta organizada é a fonte da verdade.** Apagar um documento no Finder o faz sumir da tela; arrastar um arquivo para `contrato/2026/03/` o inclui no catálogo, e a pasta escolhida por uma pessoa vence a opinião do classificador.
- **Índice invertido próprio** para a busca — palavra por palavra, com prefixo e sem acento. Procurar "marc" acha "março" sem trazer "demarcado", que era o defeito de buscar com `LIKE`.
- **Correção manual da categoria**: quem discorda da classificação escolhe a categoria certa na tela, e o arquivo se move junto. O trajeto registra que a decisão foi humana.
- **Abrir e revelar o documento** pelo painel de detalhe, no leitor e no gerenciador de arquivos do próprio sistema.
- **Duplicatas vão para `_Duplicados/`** em vez de ficarem presas na pasta de entrada. Nada é apagado — o arquivo é de quem usa.
- **Porta livre automática**: abrir o AutoDoc com uma janela já aberta escolhe a próxima porta em vez de derrubar o programa.
- **OCR de PDFs digitalizados**, extraindo as imagens embutidas com o próprio pypdf — sem depender de poppler ou pdf2image.
- **Suíte de testes automatizados** com `unittest`, sem nenhuma dependência nova, cobrindo 100% das linhas.
- **Medidor de cobertura próprio** (`ferramentas/cobertura.py`), feito com o `trace` da biblioteca padrão — inclusive das threads do servidor e do monitoramento, que as ferramentas costumam deixar passar.
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
- **Calibragem das regras.** Estão ajustadas contra os documentos de `exemplos/`
  e ainda não foram testadas com contas e notas reais, que variam bastante de
  emissor para emissor.
- **Windows e Linux.** O código é escrito para os três sistemas e os testes
  cobrem as três variações de atalho, mas a execução de verdade só foi feita no
  macOS.
- **Testes das telas.** O JavaScript (~700 linhas) não tem teste unitário: o
  `node` da máquina de desenvolvimento está quebrado e consertá-lo mexeria no
  sistema de quem está trabalhando. O que existe hoje é a checagem de sintaxe
  pelo JavaScriptCore do próprio macOS e a conferência de que todo seletor usado
  no JavaScript existe no HTML — que foi o que pegou erro de verdade.
- **Hífen invisível.** Um PDF com texto justificado às vezes traz `U+00AD` no
  meio da palavra, e o `normalizar` não o remove: "con­sumo" não casa com
  "consumo". Aparece pouco e o conserto mexe na classificação, então fica
  registrado em vez de mudado às pressas.
- **Escala do catálogo.** Ele é lido inteiro para a memória ao abrir o programa,
  o que é imediato para as centenas de documentos que uma pessoa acumula. Para
  dezenas de milhares o texto completo na memória passaria a incomodar, e aí
  valeria guardar o texto fora da ficha.
- **Data por rótulo em texto muito corrido.** A distância entre o rótulo e a data
  é medida depois de juntar os espaços, então um rótulo seguido de muitas
  palavras ainda pode alcançar uma data que não é dele.
