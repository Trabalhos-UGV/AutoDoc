# Documentos de exemplo

A demonstração do AutoDoc. São documentos fictícios — nenhuma pessoa, empresa,
CPF ou endereço aqui existe —, mas no formato em que chegam de verdade: PDF
baixado do site, papel escaneado, foto de celular, print de tela.

A instalação copia esta pasta para a pasta vigiada, e o AutoDoc já abre
organizando. Para apresentar de novo: `python main.py exemplos`.

## Contas e boletos

| Arquivo | Formato | Vai para |
| --- | --- | --- |
| `conta_luz_marco_2026.pdf` | PDF com texto | `conta_luz/2026/03` — o mês de referência, não o do vencimento |
| `conta_agua_fevereiro_2026_escaneada.pdf` | PDF escaneado (OCR) | `conta_agua/2026/02` |
| `conta_gas_janeiro_2026.pdf` | PDF com texto | `conta_gas/2026/01` |
| `internet_fibra_marco_2026.pdf` | PDF com texto | `telefone_internet/2026/03` |
| `boleto_mensalidade_abril_2026.pdf` | PDF com texto | `boleto/2026/04` — pelo vencimento |
| `fatura_cartao_marco_2026.pdf` | PDF com texto | `fatura_cartao/2026/03` |
| `iptu_2026.pdf` | PDF com texto | `impostos/2026/02` — a linha digitável não o transforma em boleto |

## Documentos pessoais

| Arquivo | Formato | Vai para |
| --- | --- | --- |
| `rg_foto_celular.jpg` | foto torta, sobre a mesa (OCR) | `documento_pessoal/2018/07` — pela expedição, não pelo nascimento |
| `cnh_digitalizada.png` | imagem escaneada (OCR) | `documento_pessoal/2024/02` — pela emissão, não pela validade |
| `holerite_marco_2026.pdf` | PDF com texto | `holerite/2026/03` — pela competência |
| `comprovante_pix_print.png` | print de tela (OCR) | `comprovante/2026/03` |

## Estudos e trabalho

| Arquivo | Formato | Vai para |
| --- | --- | --- |
| `certificado_python.pdf` | PDF com texto | `certificado/2026/03` |
| `lista_exercicios_calculo.pdf` | PDF com texto | `estudos/sem-data` — não há data no texto, e não se inventa uma |
| `contrato_aluguel_assinado.pdf` | 1 página digitada + 1 escaneada | `contrato/2026/01` — a data está na página escaneada |
| `nota_fiscal_fone.pdf` | PDF com texto | `nota_fiscal/2026/03` |
| `manual_cafeteira_deitado.jpg` | foto gravada deitada, girada pelo EXIF | `manual_tecnico/sem-data` |

## O que não é documento

| Arquivo | Vai para |
| --- | --- |
| `foto_praia.jpg` | `imagens/2025/12` — pela data de captura da câmera |
| `icone_app.png` | `imagens/sem-data` |
| `projeto_site/` | **fica onde está**: o AutoDoc não entra em subpastas |
| `fotos_viagem.zip` | **fica onde está**: não é formato que ele lê |

## Os primeiros exemplos, em texto puro

| Arquivo | Vai para |
| --- | --- |
| `conta_energia_marco.txt` | `conta_luz/2026/03` |
| `nota_fiscal_1234.txt` | `nota_fiscal/2026/03` |
| `comprovante_pix.txt` | `comprovante/2026/03` |
| `contrato_aluguel.txt` | `contrato/2026/03` |
| `scan0031_ilegivel.txt` | `_Revisar/` — de propósito |

O último imita uma digitalização ruim. Um classificador que só é mostrado
acertando não diz nada sobre o que faz quando não tem certeza: este arquivo vai
para revisão manual em vez de virar um chute.

## De onde vêm

Os arquivos saem de `ferramentas/gerar_exemplos.py`; para mudar um, mude o
texto lá e rode o script de novo. O lugar certo de cada um é conferido em
`testes/test_exemplos.py`, com OCR de verdade. Sem o Tesseract instalado, as
fotos e os scans esperam em `_Aguardando_OCR/`.
