/* Dados de demonstracao — os mesmos seis documentos, seis categorias e seis
   etapas do prototipo. Servem para os tres front-ends ficarem clicaveis antes
   do backend existir; quando a API responde, sao descartados.

   Gerado por ferramentas/gerar_dados_demo.py a partir do _build.py original. */

export const ETAPAS = [
  {
    "titulo": "Verificando ambiente",
    "detalhe": "Python 3.12.1 encontrado em C:\\Python312",
    "logs": [
      "python --version → 3.12.1",
      "espaço em disco: 214 GB livres"
    ]
  },
  {
    "titulo": "Criando ambiente virtual",
    "detalhe": "venv\\ criado no diretório do projeto",
    "logs": [
      "python -m venv venv",
      "venv ativado"
    ]
  },
  {
    "titulo": "Instalando dependências",
    "detalhe": "watchdog, pypdf, pytesseract, dateparser",
    "logs": [
      "pip install -r requirements.txt",
      "watchdog 4.0.1 ok",
      "pypdf 4.2.0 ok"
    ]
  },
  {
    "titulo": "Configurando motor de OCR",
    "detalhe": "Tesseract — opcional, só para ler imagens",
    "logs": [
      "procurando tesseract no PATH",
      "Tesseract 5.3.4 encontrado"
    ]
  },
  {
    "titulo": "Criando banco de dados",
    "detalhe": "autodoc.db + índice FTS5",
    "logs": [
      "sqlite3 autodoc.db",
      "CREATE VIRTUAL TABLE docs USING fts5(...)"
    ]
  },
  {
    "titulo": "Definindo pasta monitorada",
    "detalhe": "C:\\Users\\rafael\\AutoDoc\\Entrada",
    "logs": [
      "pasta de entrada registrada",
      "watchdog observer iniciado"
    ]
  }
];

export const DOCUMENTOS = [
  {
    "id": 1,
    "arquivo": "fatura_energia_marco.pdf",
    "origem": "PDF com texto embutido",
    "tipo": "Conta de energia",
    "confianca": "96%",
    "data": "12/03/2026",
    "destino": "/AutoDoc/Contas/2026/03/",
    "regra": "regra \"conta_energia\": (kWh | consumo) + (vencimento) + distribuidora conhecida → 3 de 3 termos",
    "chaves": [
      "kWh",
      "Consumo faturado",
      "Vencimento",
      "CEMIG"
    ],
    "trecho": "CONSUMO FATURADO 214 kWh · VENCIMENTO 12/03/2026 · TOTAL A PAGAR R$ 187,43",
    "etapas": [
      {
        "titulo": "Detecção",
        "detalhe": "watchdog on_created — 11:04:22, 1,2 MB"
      },
      {
        "titulo": "Extração de texto",
        "detalhe": "pypdf: 3.418 caracteres, OCR não necessário"
      },
      {
        "titulo": "Classificação",
        "detalhe": "score 0,96 · limiar 0,60 · nenhuma regra concorrente acima de 0,3"
      },
      {
        "titulo": "Data",
        "detalhe": "regex dd/mm/aaaa + dateparser → 2026-03-12 (rótulo \"VENCIMENTO\")"
      },
      {
        "titulo": "Arquivamento",
        "detalhe": "copiado para Contas/2026/03/ e indexado no FTS5 (id 1281)"
      }
    ]
  },
  {
    "id": 2,
    "arquivo": "IMG_4821.jpg",
    "origem": "Foto de celular — OCR",
    "tipo": "Nota fiscal",
    "confianca": "91%",
    "data": "08/03/2026",
    "destino": "/AutoDoc/Notas Fiscais/2026/03/",
    "regra": "regra \"nota_fiscal\": CNPJ válido + (valor total | total) → 2 de 2 termos",
    "chaves": [
      "CNPJ 12.345.678/0001-90",
      "VALOR TOTAL",
      "DANFE"
    ],
    "trecho": "DANFE · CNPJ 12.345.678/0001-90 · VALOR TOTAL R$ 92,70 · 08/03/2026 14:31",
    "etapas": [
      {
        "titulo": "Detecção",
        "detalhe": "watchdog on_created — 14:52:10, 3,8 MB"
      },
      {
        "titulo": "Extração de texto",
        "detalhe": "EasyOCR pt · 1,9 s · confiança média do OCR 0,88"
      },
      {
        "titulo": "Classificação",
        "detalhe": "CNPJ validado por dígito verificador — peso alto na regra"
      },
      {
        "titulo": "Data",
        "detalhe": "dateparser sobre 08/03/2026 14:31 → 2026-03-08"
      },
      {
        "titulo": "Arquivamento",
        "detalhe": "renomeado 2026-03-08_nota-fiscal_92-70.jpg"
      }
    ]
  },
  {
    "id": 3,
    "arquivo": "comprovante_pix.png",
    "origem": "Captura de tela — OCR",
    "tipo": "Comprovante",
    "confianca": "88%",
    "data": "02/03/2026",
    "destino": "/AutoDoc/Comprovantes/2026/03/",
    "regra": "regra \"comprovante\": (comprovante | recibo) + (pix | transferência) + id de transação",
    "chaves": [
      "Comprovante",
      "Pix enviado",
      "ID da transação"
    ],
    "trecho": "Comprovante · Pix enviado R$ 340,00 · 02/03/2026 · ID E1234567820260302",
    "etapas": [
      {
        "titulo": "Detecção",
        "detalhe": "watchdog on_created — 09:18:44, 420 KB"
      },
      {
        "titulo": "Extração de texto",
        "detalhe": "EasyOCR pt · 0,7 s"
      },
      {
        "titulo": "Classificação",
        "detalhe": "score 0,88 · desempate contra nota_fiscal por ausência de CNPJ"
      },
      {
        "titulo": "Data",
        "detalhe": "data única encontrada no texto → 2026-03-02"
      },
      {
        "titulo": "Arquivamento",
        "detalhe": "copiado também para a pasta sincronizada (backup)"
      }
    ]
  },
  {
    "id": 4,
    "arquivo": "contrato_aluguel_assinado.pdf",
    "origem": "PDF digitalizado — OCR",
    "tipo": "Contrato",
    "confianca": "74%",
    "data": "28/02/2026",
    "destino": "/AutoDoc/Contratos/2026/02/",
    "regra": "regra \"contrato\": (contrato | locação) + (cláusula) — 2 de 3 termos, sem valor total",
    "chaves": [
      "CONTRATO DE LOCAÇÃO",
      "cláusula",
      "das partes"
    ],
    "trecho": "CONTRATO DE LOCAÇÃO RESIDENCIAL · CLÁUSULA PRIMEIRA — DO OBJETO · 28 de fevereiro de 2026",
    "etapas": [
      {
        "titulo": "Detecção",
        "detalhe": "watchdog on_created — 16:40:03, 6,1 MB · 8 páginas"
      },
      {
        "titulo": "Extração de texto",
        "detalhe": "sem camada de texto → OCR em 8 páginas · 11,4 s"
      },
      {
        "titulo": "Classificação",
        "detalhe": "score 0,74 — abaixo de 0,80, marcado para conferência opcional"
      },
      {
        "titulo": "Data",
        "detalhe": "dateparser em português: \"28 de fevereiro de 2026\" → 2026-02-28"
      },
      {
        "titulo": "Arquivamento",
        "detalhe": "Contratos/2026/02/ · texto completo indexado (14.902 caracteres)"
      }
    ]
  },
  {
    "id": 5,
    "arquivo": "boleto_internet_abril.pdf",
    "origem": "PDF com texto embutido",
    "tipo": "Conta de internet",
    "confianca": "93%",
    "data": "05/04/2026",
    "destino": "/AutoDoc/Contas/2026/04/",
    "regra": "regra \"conta_servico\": linha digitável + vencimento + prestadora conhecida",
    "chaves": [
      "Linha digitável",
      "Vencimento",
      "Fibra 500 Mbps"
    ],
    "trecho": "34191.79001 01043.510047 91020.150008 9 87650000012999 · VENCIMENTO 05/04/2026",
    "etapas": [
      {
        "titulo": "Detecção",
        "detalhe": "watchdog on_created — 08:02:55, 780 KB"
      },
      {
        "titulo": "Extração de texto",
        "detalhe": "pypdf · 1.204 caracteres"
      },
      {
        "titulo": "Classificação",
        "detalhe": "linha digitável de 47 dígitos validada por módulo 10"
      },
      {
        "titulo": "Data",
        "detalhe": "vencimento 05/04/2026 · competência 04/2026"
      },
      {
        "titulo": "Arquivamento",
        "detalhe": "Contas/2026/04/ · lembrete de vencimento gravado"
      }
    ]
  },
  {
    "id": 6,
    "arquivo": "scan0031.pdf",
    "origem": "Digitalização ilegível",
    "tipo": "Não classificado",
    "confianca": "31%",
    "data": "—",
    "destino": "/AutoDoc/_Revisar/",
    "regra": "nenhuma regra atingiu o limiar de 0,60 — arquivo enviado para revisão manual",
    "chaves": [
      "texto insuficiente",
      "12 caracteres"
    ],
    "trecho": "l  m  ..  R$ ?  (saída do OCR ilegível — provável digitalização em baixa resolução)",
    "etapas": [
      {
        "titulo": "Detecção",
        "detalhe": "watchdog on_created — 17:22:09, 240 KB"
      },
      {
        "titulo": "Extração de texto",
        "detalhe": "EasyOCR retornou 12 caracteres aproveitáveis · confiança 0,22"
      },
      {
        "titulo": "Classificação",
        "detalhe": "melhor score 0,31 (conta_energia) — abaixo do limiar"
      },
      {
        "titulo": "Data",
        "detalhe": "nenhuma data reconhecida no texto"
      },
      {
        "titulo": "Arquivamento",
        "detalhe": "movido para _Revisar/ · aguardando confirmação do usuário"
      }
    ]
  }
];

export const CATEGORIAS = [
  {
    "nome": "Todos",
    "contagem": "1.284"
  },
  {
    "nome": "Contas",
    "contagem": "612"
  },
  {
    "nome": "Notas fiscais",
    "contagem": "341"
  },
  {
    "nome": "Comprovantes",
    "contagem": "228"
  },
  {
    "nome": "Contratos",
    "contagem": "61"
  },
  {
    "nome": "A revisar",
    "contagem": "2"
  }
];

export const ESTATISTICAS = { arquivados: "1.284", hoje: "18", ocr: "7", revisar: "2" };
export const PASTA_MONITORADA = "C:\\Users\\rafael\\AutoDoc\\Entrada";
