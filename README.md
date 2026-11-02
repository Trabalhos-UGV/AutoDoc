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

- Python 3.10 ou superior. Cuidado: em muitos sistemas o `python3` do sistema
  ainda é 3.9 — o instalador confere e avisa antes de fazer qualquer coisa.
- Só isso. O Tesseract (para ler fotos) e, no Linux, o motor da janela são
  instalados pelo próprio `instalar.py` — veja abaixo.

### Instalação

Um comando só, nos três sistemas:

```bash
git clone https://github.com/Trabalhos-UGV/AutoDoc.git
cd AutoDoc
python3 instalar.py        # no Windows: py instalar.py
```

O `instalar.py` descobre o sistema, vê o que falta e instala:

| Sistema | O que ele instala sozinho | Como |
| --- | --- | --- |
| macOS | Tesseract com o português | `brew install tesseract tesseract-lang` — sem Homebrew, ele pergunta se pode instalá-lo |
| Linux | Tesseract com o português e o motor da janela (PyGObject + WebKitGTK) | o gerenciador da distribuição: `pacman`, `apt-get`, `dnf` ou `zypper`, com `sudo` |
| Windows | Tesseract e o português | `winget`; o português vai para `%LOCALAPPDATA%\AutoDoc\tessdata`, sem pedir administrador |

O `sudo`, o Homebrew e o Windows podem pedir a senha — é por isso que essa
parte roda no terminal, antes de a janela abrir. O que já está instalado é
pulado; rodar de novo não reinstala nada. **Nada disso é obrigatório:** se algo
não instalar, ele diz o comando para fazer à mão e segue. Sem o Tesseract as
fotos esperam em `_Aguardando_OCR/`; sem o motor da janela as telas abrem no
navegador.

Depois disso ele cria o ambiente virtual, instala as dependências do Python e
abre o **instalador gráfico**, em janela própria. A tela primeiro mostra qual
pasta será vigiada e deixa escolher outra; a instalação só começa quando você
confirma. Aí ela executa seis etapas de verdade: confere o Python, o ambiente
virtual, as dependências e o OCR, prepara a pasta organizada e registra a pasta
monitorada. Na última etapa cria o atalho do sistema — um `AutoDoc.app` no
macOS, um atalho no menu Iniciar no Windows, um `.desktop` no Linux.

Trocar a pasta depois de instalado reexecuta as etapas, que são idempotentes: a
escolha vale de verdade, e não só na tela.

A partir daí o AutoDoc abre pelo ícone, como qualquer programa instalado.

> No macOS, o sistema bloqueia programas sem assinatura da Apple na primeira
> execução: clique com o botão direito no ícone e escolha **Abrir**.

#### Linux: a janela nativa

No macOS e no Windows a janela do AutoDoc vem pronta com o `pip install`. **No
Linux não**: lá o motor é o WebKitGTK do próprio sistema, alcançado pelo `gi`
(PyGObject), e os dois vêm do gerenciador da distribuição. O `instalar.py`
instala esses pacotes; para fazer à mão:

| Distribuição | Comando |
| --- | --- |
| Arch, Manjaro | `sudo pacman -S python-gobject webkit2gtk-4.1` |
| Debian, Ubuntu, Mint | `sudo apt install python3-gi gir1.2-webkit2-4.1` |
| Fedora, RHEL | `sudo dnf install python3-gobject webkit2gtk4.1` |
| openSUSE | `sudo zypper install python3-gobject typelib-1_0-WebKit2-4_1` |

Duas coisas que custaram tempo e ficam registradas para o próximo:

- **Não instale `pywebview[gtk]` pelo pip.** Ele tenta compilar o PyGObject do
  zero e falha com `Dependency 'girepository-2.0' not found` ou
  `Failed building wheel for pygobject` se faltarem os headers de
  desenvolvimento. O caminho certo é o pacote da distribuição.
- **O ambiente virtual precisa enxergar o sistema.** Um `venv` comum é isolado e
  não vê o `gi` que o `pacman` instalou, então o pywebview não acha motor mesmo
  com tudo certo no sistema. O AutoDoc cria o venv com `--system-site-packages`
  no Linux, e **conserta sozinho um venv antigo** que tenha nascido isolado —
  virando a chave `include-system-site-packages` no `pyvenv.cfg`, sem
  reinstalar nada. Você não precisa apagar a pasta `venv/`.

**Nada disso é obrigatório.** Sem o motor gráfico o AutoDoc instala e funciona
igual; as telas abrem no navegador padrão em vez de em janela própria, e o
programa diz isso com todas as letras, junto com o comando da sua distribuição.

#### Instalação à mão

Sem o instalador — o Tesseract fica por sua conta (`brew install tesseract
tesseract-lang`, `sudo apt install tesseract-ocr tesseract-ocr-por`, ou o
instalador do UB Mannheim no Windows, marcando *Portuguese*):

```bash
python3 -m venv venv                       # no Linux: --system-site-packages
source venv/bin/activate                   # Windows: venv\Scripts\activate
pip install -r requirements-essenciais.txt # o que o AutoDoc não dispensa
pip install -r requirements.txt            # + janela nativa e OCR (opcionais)
python main.py app
```

As dependências vêm em dois arquivos de propósito. O
`requirements-essenciais.txt` tem o que o AutoDoc precisa para organizar
documentos; o `requirements.txt` acrescenta a janela nativa e o OCR, que são
recursos. O instalador trata o segundo como "o melhor que der": se a parte
gráfica não instalar — o que acontece no Linux sem os pacotes acima — ele avisa
e continua, em vez de abortar a instalação inteira.

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

Por padrão são aceitos `.pdf`, `.txt`, `.md`, `.csv` e as imagens `.png`,
`.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp`, `.heic` e `.heif`. As
`extensoes` do arquivo **somam** a essas, não as substituem — um `config.json`
gravado quando só havia cinco formatos deixaria a foto do iPhone parada.

A pasta vigiada não pode ser a do próprio AutoDoc, a pasta pessoal inteira nem
a pasta Documentos inteira: o AutoDoc leva embora tudo o que aparece na pasta
vigiada, subpastas inclusive. O instalador recusa essas escolhas, e um
`config.json` antigo que aponte para uma delas faz o programa voltar ao padrão.

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
python main.py gestos             # controla o mouse com a mão, pela webcam
python main.py gestos --tetris    # Tetris comandado pela mão (--sem-camera: pelo teclado)
```

Com o AutoDoc aberto, qualquer arquivo colocado na pasta monitorada é lido,
classificado, datado, arquivado e fichado — e aparece na tela sozinho, sem
precisar recarregar nada.

### Onde ficam os dados

Tudo dentro da pasta organizada:

```
organizados/
  conta_luz/2026/03/conta_energia_marco.txt   <- o documento, que é o que importa
  contrato/sem-data/contrato.pdf               <- classificado, mas sem data no texto
  _Revisar/scan0031.txt                        <- o que não deu para classificar
  _Aguardando_OCR/foto.jpg                     <- foto lida numa máquina sem OCR
  _Nao_suportados/planilha.xlsx                <- formato que o AutoDoc não lê
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
python -m unittest discover -s testes     # 853 testes, ~23 segundos
python3 ferramentas/cobertura.py          # a cobertura, módulo a módulo
```

Usam só a biblioteca padrão — rodar os testes não pede nada além do que o
AutoDoc já pede, e cada um trabalha numa pasta temporária própria.

| Arquivo | O que cobre |
| --- | --- |
| `test_documentos_reais.py` | **o critério de pronto**: 53 documentos como saem de verdade (PDF, OCR com hífen e letra trocada, tabela), cada um conferido na pasta onde foi parar no disco |
| `test_classificador.py` | categorias, confiança, limiar, empate, termos fracos e normalização de OCR |
| `test_datas.py` | os formatos, ano plausível, mês de referência, dono da data, tabela e a regra de cada tipo |
| `test_catalogo.py` | fichas, dedupe por conteúdo, busca por prefixo e sem acento |
| `test_reconciliacao.py` | a pasta como verdade: catálogo apagado, arquivo apagado, arquivo posto à mão |
| `test_pipeline.py` | o caminho completo do documento, dedupe, correção manual e documento ilegível |
| `test_extrator.py` | texto, PDF, OCR de digitalizado e as dependências opcionais ausentes |
| `test_monitor.py` | arquivos ignorados, espera pela cópia, subpastas, varredura periódica e a espera pelo OCR |
| `test_servidor.py` | a API das telas, o fluxo de eventos e a porta ocupada |
| `test_instalacao.py` | as seis etapas e a pasta escolhida chegando ao `config.json` |
| `test_instalador_servidor.py` | o estado do instalador gráfico e as rotas dele |
| `test_atalho.py` | o `.app`, o `.desktop` e o `.lnk` gerados |
| `test_janela.py` | a janela nativa e a queda para o navegador |
| `test_config.py` | padrões, pasta de saída e a gravação da escolha |
| `test_main.py` | a linha de comando inteira |
| `test_registro.py` | o registro em arquivo, no lugar de cada sistema |

**A cobertura é de 100% das linhas** (4529 de 4536). As sete que faltam ficam de
fora por motivo, e não por esquecimento:

- quatro caminhos **só do Windows** (`%APPDATA%`, `venv\Scripts\`) — não dá
  para exercitá-los no macOS, e fingir que dá seria pior;
- os três `if __name__ == "__main__"`.

O medidor é `ferramentas/cobertura.py`, escrito com o `trace` da biblioteca
padrão. Ele registra o rastreador também para as threads novas
(`threading.settrace`), sem o que o servidor e o monitoramento ficam invisíveis
e o `servidor.py` aparece com 35% quando na verdade tem 100%.

### Testes de usabilidade (UX)

Cinco testes que rodam sozinhos pelo terminal e terminam com um parecer —
**APROVADO**, **APROVADO COM RESSALVAS** ou **REPROVADO** —, dizendo o que
passou, o que falhou e o que fazer a respeito. Saem com código 0 se nada
falhou, 1 se algo falhou, então servem também num pipeline.

```bash
python3 ferramentas/ux.py contraste          # as cores do texto se leem?
python3 ferramentas/ux.py acessibilidade     # leitor de tela e teclado encontram tudo?
python3 ferramentas/ux.py responsivo         # as telas cabem em monitor, tablet e celular?
venv/bin/python ferramentas/ux.py tempo      # a tela responde rápido?
venv/bin/python ferramentas/ux.py tarefa     # dá para fazer as tarefas de ponta a ponta?
venv/bin/python ferramentas/ux.py todos      # os cinco, com um resumo no fim
```

| Comando | Para que serve | Como mede |
| --- | --- | --- |
| `contraste` | Legibilidade para quem tem a vista cansada ou usa o notebook no sol | Razão de contraste de cada cor de texto sobre o fundo dela, contra o mínimo da WCAG 2.1 AA (4,5:1); sugere a cor que passaria. Também acusa texto pintado com a cor só decorativa |
| `acessibilidade` | Quem usa leitor de tela ou só o teclado | Lê o HTML de cada tela como o leitor de tela leria: idioma, título, botões e links com nome, imagens com `alt`, desenhos (`canvas`) descritos, campos com rótulo |
| `responsivo` | Telas usáveis em monitor, notebook, tablet e celular | Abre cada tela num Chrome sem janela em várias larguras e mede rolagem lateral, texto menor que 10,5 px e alvo de clique menor que 24×24 px (WCAG 2.5.8), dizendo qual elemento |
| `tempo` | A sensação de o programa responder na hora | Sobe o AutoDoc numa pasta temporária e cronometra abrir, listar, buscar, filtrar e a tecla do Tetris, contra os limites de Nielsen (0,1 s instantâneo; 1 s sem perder o fio) |
| `tarefa` | Se dá para fazer o que se veio fazer, sem ajuda | Cumpre quatro tarefas como uma pessoa: guardar uma conta de luz e achá-la (aparece sozinha, categoria, data, explicação, busca com acento), corrigir um documento ilegível, largar dez documentos variados de uma vez e conferir que cada um foi para a pasta certa, e jogar Tetris pelo teclado |

`tempo` e `tarefa` sobem o AutoDoc de verdade, por isso pedem o Python do
`venv`; nenhum dos cinco toca nos seus documentos. `responsivo` precisa de um
Chrome ou Chromium instalado — sem ele o teste é pulado e diz isso.

Na primeira rodada eles acharam quatro problemas, todos corrigidos:

- **dica da busca, hora do log e comentários em contraste de 3:1** — o texto
  passou para `--ad-fraco` (4,6:1), e a cor mais fraca ficou só para ícones e
  botão desabilitado;
- **cinco desenhos do Tetris sem descrição** para leitor de tela — agora a fila
  e a peça guardada dizem qual peça mostram;
- **a caixa de busca só respondia ao clique no miolo de 16 px** — a folga foi
  para dentro do campo, e a caixa inteira é clicável;
- **a busca com acento**, que o teste antes não provava de verdade, agora é
  conferida buscando "elétrica" num documento escrito sem acento.

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

### Controle por gestos (opcional)

Mexe no mouse do computador com a mão, pela webcam. É um recurso à parte: não
faz parte da organização de documentos, não é instalado pelo instalador e a
falta dele não muda nada no resto do programa.

```bash
venv/bin/python -m pip install -r requirements-gestos.txt   # OpenCV, MediaPipe, PyAutoGUI (~150 MB)
python main.py gestos --quadro           # quadro de desenho, para treinar sem mexer no mouse
python main.py gestos                    # controla o mouse; --canhoto troca as mãos, --camera 1 escolhe outra webcam
```

Use o Python do `venv` para instalar (no Windows, `venv\Scripts\python`): um
`pip` sozinho é o do sistema, que instala fora do ambiente do AutoDoc — ou é
recusado, no Linux — e o jogo continua sem achar os pacotes. No Linux o OpenCV
também precisa da `libGL` do sistema (`libgl1` no Debian/Ubuntu, `mesa` no Arch).
O botão do Tetris no aplicativo já instala do jeito certo.

Na primeira vez baixa o modelo da mão (7,8 MB) para o cache do usuário. Abre uma
janela com a imagem da câmera, o gesto reconhecido e as medidas da pinça;
**Esc** fecha, e levar o mouse de verdade a um canto da tela é o freio de
emergência.

| Gesto | Mouse | Quadro de desenho |
| --- | --- | --- |
| Mão aberta, sem pinça | Move o cursor | Move o cursor |
| Pinça polegar + indicador | Rápida: clique. Duas seguidas: clique duplo. Segurada: arrasta | Desenha |
| Pinça polegar + médio | Clique direito | Apaga a região do cursor |
| Punho fechado | Rola a tela, como um joystick: quanto mais longe de onde fechou, mais rápido | — |
| Pinça polegar + indicador, mão secundária | Para cima/baixo: volume. Para os lados: brilho | — |

Com uma mão só na frente da câmera, ela é sempre a principal. O cursor segue o
centro da palma — e não a ponta do dedo, que se mexe ao fazer a pinça — dentro
de uma área central da câmera, para os cantos da tela serem alcançáveis sem a
mão sair do quadro.

**macOS:** o sistema pede duas permissões para o aplicativo de onde o AutoDoc é
aberto (Terminal, VS Code...): **Câmera**, que ele pede sozinho na primeira vez,
e **Acessibilidade**, sem a qual os cliques são descartados em silêncio. Se ela
faltar, o AutoDoc avisa e abre a tela certa dos Ajustes do Sistema. O brilho só
responde na tela embutida; num monitor externo o resto continua funcionando.

Cada sistema tem seu caminho para o que o PyAutoGUI não cobre:

| | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Volume | pycaw (API de áudio) | AppleScript | `pactl` |
| Brilho | screen-brightness-control | DisplayServices | screen-brightness-control |
| Rolagem horizontal | API do Windows (`MOUSEEVENTF_HWHEEL`) | PyAutoGUI | PyAutoGUI |

A ideia vem do
[Gesture-Controlled-Virtual-Mouse](https://github.com/Viral-Doshi/Gesture-Controlled-Virtual-Mouse),
de Viral Doshi. O código não: o original é GPL-3.0, roda só no Windows e usa a
API `mp.solutions` do MediaPipe, que não existe mais nas versões atuais — ele
não instala num Python recente. Esta é uma reescrita sobre a API de tarefas
(`HandLandmarker`), com o que depende do sistema isolado em
`autodoc/gestos/sistema.py`.

A primeira versão seguia os gestos do original e falhava na prática. O que foi
corrigido, para quem for mexer nisto:

- **Mão trocada.** A imagem era espelhada *antes* da detecção, e o MediaPipe
  inverte o rótulo direita/esquerda numa imagem espelhada: a mão direita virava
  a secundária, que não move o cursor. Agora detecta na imagem crua e espelha
  só os pontos.
- **Pinça em fração do quadro.** Longe da câmera, a mão aberta inteira cabia no
  limiar e virava pinça; perto, a pinça nunca fechava. Agora tudo é medido em
  palmas, com histerese para o traço não picotar.
- **Dedos medidos pela altura.** Inclinar a mão bastava para errar. Agora o dedo
  está aberto se a ponta está mais longe do pulso que a junta do meio.
- **Movimento lento descartado.** O cursor andava pelo deslocamento entre dois
  quadros e ignorava os pequenos — e num movimento lento todos são pequenos.
  Agora a posição é absoluta, suavizada por um filtro One Euro.
- **Arrasto e clique duplo no macOS.** O PyAutoGUI move sem marcar o botão como
  apertado e manda todo clique como primeiro clique; o sistema ignorava os dois.

### Tetris por gestos

O botão **"Tetris com a mão"**, na lateral do AutoDoc, abre o jogo numa janela
própria. Se os gestos ainda não estiverem instalados, o mesmo botão instala
(uns 150 MB, uma vez só), mostrando o progresso — nada de terminal. O link
"ou jogar pelo teclado" abre o jogo sem câmera.

| Gesto | No jogo |
| --- | --- |
| Mão para os lados | A peça vai para a coluna para onde a mão aponta |
| Polegar no indicador, encostar e soltar | Gira a peça |
| Baixar a mão (abaixo da linha tracejada) | Desce mais rápido |
| Fechar a mão | A peça despenca |
| Polegar no médio | Guarda a peça; de novo, troca pela guardada |
| Tirar a mão da câmera | Pausa (volta com contagem) |

Pelo teclado: setas, `Z`/`X` giram, espaço despenca, `C` guarda, `P` pausa, `R`
recomeça. As regras (rotação oficial SRS, sorteio em "saco de 7", trava com
atraso) ficam em `autodoc/gestos/tetris.py`, com testes; a tela só desenha.

**Você vira um personagem 3D.** Com a câmera ligada, a imagem dela não aparece:
um vira-lata caramelo em 3D copia a sua cabeça, o rosto (piscar, boca, sorriso,
sobrancelhas), os braços e as mãos. Ele comemora quando você fecha uma linha,
pula num "TETRIS!" e fica cabisbaixo no fim de jogo. O rosto, o corpo e as mãos
viram só números de pose — **nenhuma imagem sua sai do programa**. O personagem
é construído em código com o three.js, sem modelo 3D de terceiros.

Se a máquina não desenhar 3D, o jogo volta para a imagem da câmera com o rosto
coberto por um emoji escolhido entre 15 animais (Fluent Emoji, da Microsoft,
licença MIT, em `autodoc/web/estatico/personagens/`).

Na primeira vez são baixados os modelos do MediaPipe para o rosto (3,7 MB) e o
corpo (5,5 MB). No Mac com chip Apple, o AutoDoc aberto pelo ícone pede a
permissão da câmera em nome próprio: o pacote tem um executável dele (gerado
pelo `osacompile`), em vez de um script que virava o Python — com o script, o
macOS recusava a câmera em silêncio e ainda abria o app emulando Intel.

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
  gestos/           # gestos pela webcam: mouse, quadro de desenho, Tetris e avatar 3D (opcional)
site/               # landing page, publicável sozinha
exemplos/           # documentos fictícios para experimentar
recursos/           # ícone do aplicativo em cada formato
ferramentas/        # scripts de apoio ao desenvolvimento
instalar.py         # instalador gráfico
main.py             # interface de linha de comando
```

### Como o documento é processado

1. **Detecção** — o `monitor` percebe o arquivo novo, inclusive dentro de subpastas, e espera a cópia terminar: tamanho e data de modificação parados e o arquivo abrindo para leitura. O que não ficou pronto a tempo, ou não pôde ser movido, fica na entrada e é tentado de novo pela varredura que roda a cada 30 segundos.
2. **Deduplicação** — o hash SHA-256 do conteúdo é comparado com o catálogo; se aquele documento já foi arquivado, a cópia vai para `organizados/_Duplicados/` em vez de ser processada de novo.
3. **Extração** — o texto é lido direto (`.txt`), da camada de texto do PDF, ou via OCR. No PDF a decisão é **por página**: a página com pouco texto passa pelo OCR, e um contrato digitado com a página assinada escaneada é lido inteiro. Antes do OCR a foto é endireitada pelo EXIF, passada para tons de cinza e ampliada se for pequena.
4. **Classificação** — cada categoria pontua conforme as palavras-chave encontradas, e o resultado vira uma **confiança de 0 a 1**. Abaixo de 0,60 o documento não é classificado. Também não é classificado o que só tem termos fracos — "Pix", "CPF", "vencimento" aparecem em quase tudo e, sozinhos, não dizem o tipo.
5. **Data** — a data que define a pasta depende do tipo de documento (tabela abaixo). Cada data é atribuída ao rótulo mais próximo antes dela, e uma tabela com os rótulos numa linha e as datas na de baixo é pareada pela ordem. Sem data no texto, o documento vai para `sem-data/` — **nunca** para o mês em que o arquivo foi baixado.
6. **Arquivamento** — o arquivo vai para `organizados/<categoria>/<ano>/<mês>/`, sem sobrescrever homônimos. O que ficou abaixo do limiar vai para `organizados/_Revisar/`.
7. **Ficha e backup** — metadados, texto e a explicação da classificação viram uma ficha em `organizados/.autodoc/catalogo.jsonl`; se configurado, uma cópia vai para a pasta de backup.

O que não pôde ser lido — PDF corrompido, imagem ilegível — também sai da pasta de entrada e vai para `_Revisar/`, com o motivo escrito no trajeto. Uma foto boa numa máquina **sem OCR** não é ilegível: vai para `_Aguardando_OCR/` e volta ao processamento sozinha quando o OCR existir. Formato que o AutoDoc não lê vai para `_Nao_suportados/`. A tela avisa quantos arquivos estão em cada uma dessas pastas — um arquivo deixado para trás sem aviso é um arquivo que ninguém acha.

| Tipo | Data que define a pasta, em ordem |
| --- | --- |
| Contas mensais (luz, água, gás, telefone e internet, fatura do cartão) | mês de **referência** → leitura atual → fechamento → vencimento → emissão |
| Holerite | **competência** → pagamento |
| Nota fiscal | **emissão** |
| Boleto, impostos | **vencimento** |
| Comprovante | data da operação ou do pagamento |
| Contrato | assinatura, ou a data por extenso do fecho |
| Documento pessoal | **expedição** — nunca nascimento nem validade |

A conta de março vai para `2026/03` mesmo vencendo em abril, porque é como as
pessoas procuram ("a conta de março"). O ano de dois dígitos vira 20xx só até o
ano que vem; acima disso é 19xx ("15/08/98" é 1998, não 2098).

### Categorias reconhecidas

`conta_luz`, `conta_agua`, `conta_gas`, `telefone_internet`, `fatura_cartao`,
`holerite`, `impostos`, `nota_fiscal`, `boleto`, `contrato`, `comprovante` e
`documento_pessoal`. O que não atinge o limiar de confiança vira
`nao_classificado` e vai para revisão manual.

Fatura do cartão, imposto e conta de consumo também trazem linha digitável;
quando um desses tipos tem um termo forte, ele ganha de `boleto`.

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
- **Controle do mouse por gestos**, pela webcam, no Windows, no macOS e no Linux — mover, clicar, arrastar, rolar, volume e brilho. Opcional, com dependências à parte.
- **Quadro de desenho por gestos**, para treinar e calibrar os gestos sem entregar o mouse do sistema a eles.
- **Tetris comandado pela mão**, aberto por um botão no próprio AutoDoc, com instalação dos gestos pelo app.
- **Avatar 3D** que substitui a pessoa na tela e copia cabeça, rosto, braços e mãos — sem nenhuma imagem da câmera sair do programa.
- **Máscara de emoji sobre o rosto**, como reserva para máquinas sem 3D, cobrindo todo rosto que aparecer na câmera.
- **Testes de usabilidade automáticos** (`ferramentas/ux.py`): contraste, acessibilidade, telas em vários tamanhos, tempo de resposta e tarefas de ponta a ponta, cada um com parecer no terminal.
- **Permissão de câmera do próprio AutoDoc no macOS**, e o app rodando nativo no chip Apple em vez de emulado.
- **Cinco categorias além das da proposta**: holerite, fatura do cartão, impostos (IPTU, IPVA, DAS, DARF), telefone e internet, e conta de gás.
- **Data da pasta pelo tipo de documento**, com mês de referência para as contas mensais, ano de dois dígitos plausível, leitura de tabela e tolerância às trocas do OCR (`O`↔`0`, `l`↔`1`).
- **Leitura tolerante ao OCR** no classificador: hífen de fim de linha, hífen invisível e letras trocadas ("CEMlG" é CEMIG).
- **Corpus de 53 documentos reais** como critério de pronto, cada um conferido na pasta onde foi parar no disco.
- **O arquivo sempre chega**: espera pela cópia terminar sem processar pela metade, nova tentativa para o arquivo travado e varredura da entrada a cada 30 segundos.
- **Subpastas e mais formatos**: `.tif`, `.webp` e `.heic` do iPhone; o que não for lido vai para `_Nao_suportados/` em vez de ficar parado.
- **Diagnóstico do OCR na tela**, com o comando de instalação de cada sistema, e fotos esperando o OCR em vez de irem para a revisão.
- **OCR por página**, com a foto endireitada pelo EXIF e ampliada antes de ler.
- **Instalação num comando só**: o `instalar.py` descobre o sistema e instala o Tesseract com o português (Homebrew, gerenciador da distribuição ou winget) e, no Linux, o motor da janela.
- **Registro em arquivo por usuário** (`~/Library/Logs/AutoDoc`, `%LOCALAPPDATA%\AutoDoc\logs`, `~/.local/state/autodoc`), para quem abre pelo atalho e não tem terminal.

## O que ainda não está pronto

Registrado aqui porque um projeto que só lista o que funciona não ajuda quem vai
continuá-lo:

- **Avatar 3D ao vivo.** Foi conferido com fotos (a pose calculada de uma foto,
  desenhada no personagem), não com uma pessoa jogando na frente da câmera. Os
  limites das expressões e a suavização ainda precisam desse teste.
- **Mais personagens 3D.** Só o vira-lata caramelo existe; os próximos
  planejados são capivara, onça-pintada, mico-leão-dourado, tucano, arara-azul,
  preguiça, boto-cor-de-rosa, tamanduá, lobo-guará, sapo e Saci. Pessoas reais
  ficam de fora de propósito, por causa do direito de imagem.

- **O pacote para baixar pela landing.** Hoje a instalação é feita a partir do
  repositório, com `python3 instalar.py`. Falta empacotar isso num arquivo que a
  landing possa entregar — a página detecta que o pacote não existe e avisa, em
  vez de oferecer um link quebrado.
- **Calibragem das regras.** Estão ajustadas contra um corpus de 53 textos
  escritos como os documentos reais saem (`testes/test_documentos_reais.py`),
  e não contra arquivos de verdade de cada emissor. Cada erro achado no uso real
  deve virar um caso a mais ali.
- **OCR de verdade.** O caminho do OCR (por página, EXIF, ampliação, espera em
  `_Aguardando_OCR/`) é testado com o Tesseract dublado: a máquina de
  desenvolvimento não tem o Tesseract instalado. Falta passar uma foto de conta
  e um PDF escaneado de verdade com ele instalado.
- **Windows e Linux.** O código é escrito para os três sistemas e os testes
  cobrem as três variações de atalho e a instalação sem parte gráfica, mas a
  execução de verdade só foi feita no macOS. O caminho do Linux foi corrigido a
  partir de um relato real (Arch) e verificado por simulação, não numa máquina
  Linux de verdade.
- **Testes das telas.** O JavaScript (~700 linhas) não tem teste unitário: o
  `node` da máquina de desenvolvimento está quebrado e consertá-lo mexeria no
  sistema de quem está trabalhando. O que existe hoje é a checagem de sintaxe
  pelo JavaScriptCore do próprio macOS e a conferência de que todo seletor usado
  no JavaScript existe no HTML — que foi o que pegou erro de verdade.
- **Escala do catálogo.** Ele é lido inteiro para a memória ao abrir o programa,
  o que é imediato para as centenas de documentos que uma pessoa acumula. Para
  dezenas de milhares o texto completo na memória passaria a incomodar, e aí
  valeria guardar o texto fora da ficha.
- **Controle por gestos.** No Mac foi verificado com as bibliotecas reais —
  detecção numa foto, desenho do quadro, leitura e escrita de volume e brilho —,
  mas não com a webcam ao vivo. Windows e Linux estão cobertos por testes com o
  sistema simulado, não numa máquina de verdade. Os limiares da pinça
  (`PINCA_FECHA`, `PINCA_ABRE`) e a área da câmera (`AREA`) são estimativas a
  calibrar no quadro de desenho, que mostra as medidas ao vivo.
- **Data por rótulo em texto muito corrido.** Uma data pertence ao rótulo mais
  próximo antes dela, até 40 caracteres e sem outra data no meio. Num texto em
  que o rótulo e a data ficam longe um do outro, a data fica sem dono e vale a
  primeira data solta do documento.
