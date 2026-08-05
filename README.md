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
- **Tesseract OCR** ou **EasyOCR** — leitura de texto em imagens e documentos escaneados
- **regex** + **dateparser** — identificação e extração de datas
- **SQLite** — armazenamento e busca dos documentos processados
- **pathlib** — compatibilidade de caminhos entre Windows e macOS

## Instruções de Instalação, Dependências e Execução

### Pré-requisitos

- Python 3.10 ou superior
- Tesseract OCR instalado no sistema operacional (necessário apenas se for usar Tesseract em vez de EasyOCR):
  - **Windows:** baixar o instalador em https://github.com/UB-Mannheim/tesseract/wiki
  - **macOS:** `brew install tesseract`
  - **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr`

### Instalação

```bash
# Clonar o repositório
git clone https://github.com/<usuario>/autodoc.git
cd autodoc

# Criar e ativar um ambiente virtual
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Instalar as dependências
pip install -r requirements.txt
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

```bash
python main.py monitorar          # observa a pasta de entrada (padrão)
python main.py buscar "luz março" # busca nos documentos indexados
python main.py listar             # últimos documentos processados
```

Após iniciado, o AutoDoc passa a monitorar a pasta configurada. Qualquer arquivo novo colocado nela será lido, classificado, datado e armazenado automaticamente no banco de dados pesquisável.

### Interface gráfica

O AutoDoc tem três telas, todas em HTML/CSS/JavaScript puro — sem framework, sem
etapa de build e sem nada vindo de CDN, porque o programa roda offline. Para vê-las
funcionando:

```bash
python3 ferramentas/servir_demo.py
```

O comando serve a raiz do projeto e abre a landing no navegador; a barra no topo
alterna entre as três telas.

| Tela | Arquivo | O que faz |
| --- | --- | --- |
| Landing / download | [site/index.html](site/index.html) | Página pública. Detecta o sistema do visitante, promove o download certo e mostra o tamanho real do pacote |
| Instalação | [autodoc/web/estatico/instalador.html](autodoc/web/estatico/instalador.html) | Acompanha as seis etapas da instalação com barra de progresso e log ao vivo |
| Gerenciamento | [autodoc/web/estatico/app.html](autodoc/web/estatico/app.html) | Lista os documentos processados, filtra por categoria, busca no conteúdo e explica cada classificação |

**Modo demonstração.** Sem o servidor do AutoDoc no ar, as telas usam dados de
exemplo e se identificam como tal — a barra lateral mostra "modo demonstração"
em vez de "watchdog ativo", e a landing avisa quando o pacote ainda não foi
gerado. Quando o backend responde, elas passam a usar os dados reais sozinhas.

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
  web/estatico/     # telas de instalação e gerenciamento (HTML, CSS, JS, fontes)
site/               # landing page, publicável sozinha
ferramentas/        # scripts de apoio ao desenvolvimento
main.py             # interface de linha de comando
```

### Como o documento é processado

1. **Detecção** — o `monitor` percebe o arquivo novo e espera a cópia terminar.
2. **Deduplicação** — o hash SHA-256 do arquivo é comparado com o banco; se já foi indexado, é ignorado.
3. **Extração** — o texto é lido direto (`.txt`), da camada de texto do PDF, ou via OCR (imagens).
4. **Classificação** — cada categoria pontua conforme as palavras-chave encontradas; vence a de maior pontuação.
5. **Data** — busca por `dd/mm/aaaa`, `aaaa-mm-dd` e "12 de março de 2026"; sem data no texto, usa a data de modificação do arquivo.
6. **Arquivamento** — o arquivo é movido para `organizados/<categoria>/<ano>/`, sem sobrescrever homônimos.
7. **Indexação e backup** — metadados e texto vão para o SQLite e, se configurado, uma cópia vai para a pasta de backup.

### Categorias reconhecidas

`conta_luz`, `conta_agua`, `nota_fiscal`, `boleto`, `contrato`, `comprovante`, `documento_pessoal` e `outros` (quando nenhuma regra pontua). As regras ficam em `autodoc/classificador.py` e podem ser estendidas livremente.

### Funcionalidades adicionais implementadas

Além do escopo original da proposta, esta base inclui:

- **CLI com subcomandos** (`monitorar`, `buscar`, `listar`) em vez de apenas execução direta.
- **Busca por conteúdo, categoria, data ou nome do arquivo** em um único termo.
- **Deduplicação por hash**, evitando reprocessar o mesmo documento.
- **Processamento de pendentes**: arquivos já presentes na pasta quando o monitor sobe também são processados.
- **Arquivamento por categoria e ano**, com renomeação automática em caso de nome repetido.
- **Três telas gráficas** (landing, instalador e gerenciamento), responsivas e navegáveis por teclado.
- **Funcionamento offline**: as fontes ficam versionadas no projeto, então nenhuma tela depende de internet.
- **Modo demonstração** em todas as telas, para apresentar o sistema sem precisar instalá-lo.
- **Detecção de sistema operacional** na landing, promovendo o download certo para quem visita.

### Instalação pela landing page

O plano é que o AutoDoc seja instalado a partir da própria landing, e não por
linha de comando. O caminho:

1. A landing entrega um **bootstrapper** de uns 60 KB — não um executável gigante.
   Por isso o Python 3.10+ é pré-requisito, e por isso a primeira etapa do
   instalador é literalmente procurar o Python na máquina.
2. Executado, o bootstrapper sobe um servidor local e abre a tela de instalação
   no navegador.
3. As seis etapas ali são **operações reais** — criar o `venv`, rodar o
   `pip install`, localizar o Tesseract, criar o `autodoc.db`, registrar a pasta
   monitorada —, com o log saindo na tela conforme acontecem.
4. Ao terminar, "Abrir o AutoDoc" leva à tela de gerenciamento, já lendo o banco.

Cada sistema recebe um invólucro diferente, porque um `.pyz` não é clicável em
todo lugar: `.pyz` no Windows, um `.command` dentro de um `.zip` no macOS, e
linha de comando no Linux. No macOS, o Gatekeeper bloqueia programas sem
assinatura da Apple na primeira execução — o caminho é clicar com o botão direito
e escolher **Abrir**.

> **Status atual:** núcleo funcional e as três telas construídas (v0.2.0). O
> bootstrapper e o servidor local que ligam as telas ao núcleo são a próxima
> etapa; até lá as telas rodam em modo demonstração. Depois disso vêm o OCR como
> fallback para PDFs digitalizados, o índice FTS5 e os testes automatizados.
