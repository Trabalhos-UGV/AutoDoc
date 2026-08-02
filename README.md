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

Defina a pasta que será monitorada (e, opcionalmente, a pasta de backup sincronizado) no arquivo de configuração do projeto antes de executar.

### Execução

```bash
python main.py
```

Após iniciado, o AutoDoc passa a monitorar a pasta configurada. Qualquer arquivo novo colocado nela será lido, classificado, datado e armazenado automaticamente no banco de dados pesquisável.

> **Status atual:** projeto em desenvolvimento — esta seção será atualizada conforme novas funcionalidades forem implementadas.
