"""Cada documento na pasta certa: o criterio de pronto do AutoDoc.

Um corpus de documentos brasileiros como eles saem de verdade — o texto que o
pypdf extrai de uma conta, o que o OCR le de uma foto, com hifen quebrado, "O"
no lugar de zero e tabela com o rotulo numa linha e o valor na de baixo. Cada
um passa pelo pipeline inteiro, numa pasta temporaria, e o teste confere **onde
o arquivo foi parar no disco**.

A data de modificacao de todo arquivo e posta em 01/01/2001 de proposito: um
documento que fosse arquivado pela data do arquivo, e nao pela do texto, cai
em 2001/01 e o teste acusa. Sem data no texto, o lugar certo e `sem-data/`.

As regras de qual data vale foram decididas com o grupo:

- contas mensais (luz, agua, gas, telefone, cartao) e holerite vao para o mes
  de **referencia** ("a conta de marco"), mesmo vencendo no mes seguinte; sem
  referencia escrita (OCR ruim), vale o mes do vencimento que esta escrito;
- nota fiscal pela emissao; boleto e imposto pelo vencimento; documento
  pessoal pela expedicao, nunca pelo nascimento nem pela validade.

Todo erro achado no uso real vira um caso a mais aqui.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from autodoc.catalogo import Catalogo
from autodoc.config import Config
from autodoc.pipeline import Pipeline

# 01/01/2001 00:00 UTC — longe de qualquer data do corpus.
MODIFICACAO_FALSA = 978307200

# (nome, pasta esperada relativa a organizados/, texto)
CORPUS = [
    # ------------------------------------------------------------ conta de luz
    ("luz_copel.txt", "conta_luz/2026/03", """COPEL DISTRIBUICAO S.A. CNPJ 04.368.898/0001-06
NOTA FISCAL/CONTA DE ENERGIA ELETRICA - SERIE B
UNIDADE CONSUMIDORA 12345678  REFERENCIA MAR/2026
DATA DE EMISSAO 20/03/2026  LEITURA ANTERIOR 18/02/2026  LEITURA ATUAL 19/03/2026
CONSUMO 214 kWh  BANDEIRA TARIFARIA VERDE  ICMS 18% R$ 25,85
CHAVE DE ACESSO 4126 0304 3688 9800 0106 6600 1000 0000 0110 0000 0001
VENCIMENTO 06/04/2026  TOTAL A PAGAR R$ 187,43
Pague com Pix: use a chave pix ou o QR Code"""),
    ("luz_enel.txt", "conta_luz/2026/02", """Enel Distribuicao Sao Paulo  Conta de Energia
Nota Fiscal / Conta de Energia Eletrica N. 000123456
Cliente: FULANO DE TAL  CPF ***.456.789-**
Referencia: 02/2026  Vencimento: 10/03/2026
Consumo (kWh) 312  Valor a pagar R$ 245,10  ICMS R$ 40,22  PIS/COFINS
Codigo de barras 83600000002-4 45100162026-1"""),
    ("luz_cemig.txt", "conta_luz/2026/03", """CEMIG DISTRIBUICAO S.A.
CNPJ 06.981.180/0001-16
CONTA DE ENERGIA ELETRICA
Mes de referencia: MAR/2026
LEITURA ANTERIOR   12/02/2026    8.412 kWh
LEITURA ATUAL      12/03/2026    8.626 kWh
CONSUMO FATURADO                   214 kWh
Bandeira tarifaria: verde
TOTAL A PAGAR                    R$ 187,43
VENCIMENTO                       12/03/2026"""),
    ("luz_tabela.txt", "conta_luz/2026/03", """COPEL DISTRIBUICAO  CONTA DE ENERGIA ELETRICA  CONSUMO 214 kWh
LEITURA ANTERIOR  LEITURA ATUAL  VENCIMENTO  TOTAL A PAGAR
18/02/2026        19/03/2026     06/04/2026  R$ 187,43"""),
    ("luz_so_referencia.txt", "conta_luz/2026/03", """CEMIG  CONTA DE ENERGIA ELETRICA  CONSUMO FATURADO 214 kWh  BANDEIRA TARIFARIA VERDE
Referencia: MAR/2026   TOTAL A PAGAR R$ 187,43"""),
    ("luz_ocr_quebrada.txt", "conta_luz/2026/03", """COPEL  Conta de ener-
gia elétrica  consu-
mo 214 kWh  Vencimento 12/03/2026"""),
    ("luz_ocr_hifen_invisivel.txt", "conta_luz/2026/03",
     "COPEL con­sumo fatu­rado 214 kWh  bandeira tari­fária  vencimento 12/03/2026"),
    ("luz_ocr_letras_trocadas.txt", "conta_luz/2026/03",
     "CEMlG  CONSUMO FATURAD0 214 kWh  Vencimento 12/O3/2026  TOTAL A PAGAR"),
    ("luz_energisa.txt", "conta_luz/2026/05", """ENERGISA MATO GROSSO DO SUL  Sua conta de energia
Mes/Ano de referencia 05/2026  Consumo 180 kWh  Vencimento 15/06/2026
Valor total R$ 160,00"""),
    # ------------------------------------------------------------ conta de agua
    ("agua_sabesp.txt", "conta_agua/2026/03", """SABESP Companhia de Saneamento Basico do Estado de Sao Paulo
CONTA DE AGUA E ESGOTO  Fornecimento: 03/2026
Hidrometro: Y12A345678  Leitura anterior 10/02/2026  Leitura atual 12/03/2026
Consumo de agua 12 m3  Esgoto R$ 48,00  Agua R$ 56,00
Total a pagar R$ 104,00  Vencimento 02/04/2026  Pague via Pix"""),
    ("agua_copasa.txt", "conta_agua/2026/02", """COPASA - Companhia de Saneamento de Minas Gerais
Matricula 1234567  Referencia 02/2026
Consumo (m3) 15   Valor da agua R$ 70,10  Valor do esgoto R$ 63,09
Vencimento 15/03/2026   TOTAL R$ 133,19"""),
    ("agua_sanepar.txt", "conta_agua/2026/04", """SANEPAR  Companhia de Saneamento do Parana
Fatura de agua e esgoto  Referencia: ABR/2026
Consumo 10 m3   Vencimento 20/05/2026   Total R$ 95,00"""),
    # ------------------------------------------------------------- gas, telefone
    ("gas_comgas.txt", "conta_gas/2026/03", """COMGAS  Conta de gas canalizado  Consumo 12 m3  Leitura anterior 10/02/2026
Vencimento 05/03/2026  Total a pagar R$ 98,00"""),
    ("internet_vivo.txt", "telefone_internet/2026/03", """VIVO  Telefonica Brasil S.A.  Fatura de servicos  Plano Fibra 500 Mega
Nota Fiscal de Servico de Telecomunicacao  Vencimento 15/03/2026  Total a pagar R$ 129,90"""),
    ("celular_claro.txt", "telefone_internet/2026/04", """Claro S.A.  Sua conta Claro  Plano Controle 25GB
Periodo de referencia: 01/04/2026 a 30/04/2026  Vencimento 10/05/2026
Total a pagar R$ 59,90  Servicos de telecomunicacao"""),
    # ----------------------------------------------------------- cartao, holerite
    ("fatura_cartao.txt", "fatura_cartao/2026/03", """Fatura do cartao de credito Nubank
Fechamento 28/03/2026   Vencimento 05/04/2026
Total da fatura R$ 1.234,56   Pagamento minimo R$ 185,18
Pague com boleto: linha digitavel 26090.12345 67890.123456 78901.234567 1 11230000123456
ou com Pix"""),
    ("holerite.txt", "holerite/2026/03", """RECIBO DE PAGAMENTO DE SALARIO  CONTRACHEQUE
EMPRESA X LTDA CNPJ 12.345.678/0001-90
Competencia: 03/2026   Funcionario: FULANO DE TAL  CPF 123.456.789-00
Salario base 3.000,00  INSS 270,00  IRRF 50,00  FGTS 240,00
Liquido a receber 2.680,00   Data de pagamento 05/04/2026"""),
    ("holerite_ano_curto.txt", "holerite/2026/03", "CONTRACHEQUE  Competencia 03/26  Pagamento 05/04/26"),
    # ------------------------------------------------------------ boleto, imposto
    ("boleto_escola.txt", "boleto/2026/05", """Banco Itau S.A.  341-7  34191.09008 63521.234560 61234.560009 8 11230000015000
Local de pagamento: Pagavel em qualquer banco ate o vencimento
Beneficiario: ESCOLA ABC LTDA CNPJ 12.345.678/0001-90
Pagador: FULANO DE TAL CPF 123.456.789-00
Data do documento 20/04/2026  Nosso numero 109/00635212-3
Vencimento 10/05/2026  Valor do documento 150,00
Ficha de Compensacao  Autenticacao mecanica"""),
    ("boleto_instrucoes.txt", "boleto/2026/05", """Boleto bancario  Linha digitavel 34191.09008  Beneficiario ESCOLA ABC  Nosso numero 109
Instrucoes: nao receber apos 30 dias do vencimento. Juros de 1% a.m. a partir de 11/05/2026
Data do documento 20/04/2026   Vencimento 10/05/2026"""),
    ("iptu.txt", "impostos/2026/02", """PREFEITURA MUNICIPAL DE PONTA GROSSA  IPTU 2026  Imposto Predial e Territorial Urbano
Inscricao imobiliaria 01.02.003  Parcela unica  Vencimento 10/02/2026  Linha digitavel 81600000"""),
    ("das_mei.txt", "impostos/2026/04", """Documento de Arrecadacao do Simples Nacional  DAS MEI
CNPJ 12.345.678/0001-90  Periodo de apuracao: Marco/2026
Pagar este documento ate 20/04/2026   Valor total R$ 75,90"""),
    # ---------------------------------------------------------------- nota fiscal
    ("danfe.txt", "nota_fiscal/2026/02", """DANFE Documento Auxiliar da Nota Fiscal Eletronica
0 - ENTRADA 1 - SAIDA   N. 000.012.345  SERIE 1
CHAVE DE ACESSO 3526 0212 3456 7800 0190 5500 1000 0123 4510 0012 3456
NATUREZA DA OPERACAO VENDA DE MERCADORIA
DATA DA EMISSAO 14/02/2026   DATA DA SAIDA 14/02/2026
CNPJ 12.345.678/0001-90  BASE DE CALCULO DO ICMS 1.000,00
VALOR TOTAL DA NOTA 1.180,00
FATURA/DUPLICATA 001 VENC 16/03/2026 590,00  002 VENC 15/04/2026 590,00"""),
    ("danfe_duplicata_antes.txt", "nota_fiscal/2026/02", """DANFE  CHAVE DE ACESSO 3526  NATUREZA DA OPERACAO VENDA
FATURA DUPLICATA VENC 16/03/2026
DATA DA EMISSAO 14/02/2026  VALOR TOTAL DA NOTA 1.180,00"""),
    ("nfce_mercado.txt", "nota_fiscal/2026/03", """SUPERMERCADO BOM PRECO LTDA CNPJ 11.222.333/0001-44
DOCUMENTO AUXILIAR DA NOTA FISCAL DE CONSUMIDOR ELETRONICA
Qtde total de itens 12   Valor total R$ 245,30
FORMA DE PAGAMENTO Cartao de Debito
NFC-e n 123456 Serie 1 Emissao 08/03/2026 18:42:10
Consulte pela Chave de Acesso em www.fazenda.sp.gov.br"""),
    ("nfe_ocr_hifen.txt", "nota_fiscal/2026/02", "NF-e  Nota Fiscal Eletrônica  Emissão: 14/02/2026  Valor total R$ 300,00"),
    # ---------------------------------------------------------------- comprovante
    ("pix.txt", "comprovante/2026/04", """Comprovante de transferencia
Pix enviado   04/04/2026 - 14:32
Valor R$ 250,00
Para: MARIA DA SILVA  Chave Pix: maria@email.com
Instituicao: Nubank
ID da transacao: E00000000202604041432abc123"""),
    ("pagamento_boleto.txt", "comprovante/2026/04", """Comprovante de pagamento
Pagamento de boleto efetuado em 10/04/2026
Codigo de barras 34191.09008 63521.234560 61234.560009 8 11230000015000
Beneficiario ESCOLA ABC LTDA  Valor pago R$ 150,00
Autenticacao A1B2C3D4E5F6"""),
    ("comprovante_1998.txt", "comprovante/1998/08", "COMPROVANTE DE PAGAMENTO  ID da transacao 7781  Pix  15/08/98"),
    # ------------------------------------------------------------------- contrato
    ("contrato_aluguel.txt", "contrato/2026/01", """CONTRATO DE LOCACAO RESIDENCIAL
Pelo presente instrumento, de um lado o LOCADOR JOAO PEREIRA, CPF 111.222.333-44,
e de outro o LOCATARIO FULANO DE TAL, CPF 123.456.789-00, tem entre si justo e contratado:
CLAUSULA PRIMEIRA - DO OBJETO ... CLAUSULA SEGUNDA - DO PRAZO de 30 meses
Fica eleito o foro da comarca de Ponta Grossa.
Ponta Grossa, 15 de janeiro de 2026."""),
    ("contrato_servico.txt", "contrato/2026/02", """CONTRATO DE PRESTACAO DE SERVICOS
CONTRATANTE: EMPRESA X LTDA   CONTRATADA: FULANO DE TAL ME
CLAUSULA 1a - DO OBJETO  CLAUSULA 2a - DO PAGAMENTO via Pix ou transferencia
Data de assinatura: 03/02/2026"""),
    ("contrato_versao_rodape.txt", "contrato/2026/01", """CONTRATO DE LOCACAO  LOCADOR  LOCATARIO  CLAUSULA PRIMEIRA
Ponta Grossa, 15 de janeiro de 2026.
Modelo v1.2.26 gerado pelo sistema"""),
    ("contrato_sem_data.txt", "contrato/sem-data", """CONTRATO DE LOCACAO  LOCADOR  LOCATARIO
CLAUSULA PRIMEIRA - DO OBJETO  Fica eleito o foro da comarca de Ponta Grossa."""),
    # ---------------------------------------------------------- documento pessoal
    ("rg.txt", "documento_pessoal/2018/07", """REPUBLICA FEDERATIVA DO BRASIL  CARTEIRA DE IDENTIDADE
REGISTRO GERAL 12.345.678-9   DATA DE EXPEDICAO 10/07/2018
NOME FULANO DE TAL  FILIACAO JOAO DE TAL  MARIA DE TAL
NATURALIDADE PONTA GROSSA-PR   DATA DE NASCIMENTO 05/09/1995
CPF 123.456.789-00   ORGAO EXPEDIDOR SSP/PR"""),
    ("rg_nascimento_antes.txt", "documento_pessoal/2018/07", """CARTEIRA DE IDENTIDADE  REGISTRO GERAL 12.345.678-9
DATA DE NASCIMENTO 05/09/1995  FILIACAO JOAO DE TAL  NATURALIDADE PONTA GROSSA
DATA DE EXPEDICAO 10/07/2018  ORGAO EXPEDIDOR SSP/PR"""),
    ("cnh.txt", "documento_pessoal/2024/02", """REPUBLICA FEDERATIVA DO BRASIL  MINISTERIO DA INFRAESTRUTURA
CARTEIRA NACIONAL DE HABILITACAO
NOME FULANO DE TAL  DOC. IDENTIDADE/ORG. EMISSOR/UF 123456789 SSP PR
CPF 123.456.789-00  DATA NASCIMENTO 05/09/1995  FILIACAO JOAO DE TAL
VALIDADE 20/02/2034  1a HABILITACAO 10/01/2014  CAT. HAB. B
DATA EMISSAO 20/02/2024"""),
    # ---------- achados na validacao com documentos ineditos (viraram corpus)
    ("luz_equatorial_ocr.txt", "conta_luz/2026/05", """EQUATORlAL ENERGIA  fatura de energia  consumo 300 kWh
REFERENCIA: MAl/2026  VENCIMENTO 10/O6/2026"""),
    ("agua_embasa.txt", "conta_agua/2026/02", """EMBASA Empresa Baiana de Aguas e Saneamento
Mes/Ano 02/2026  Consumo 9 m3  Vencimento 20/03/2026"""),
    ("ipva.txt", "impostos/2026/01", """Secretaria da Fazenda  IPVA 2026  Placa ABC1D23  Cota unica
Vencimento 20/01/2026  Valor R$ 1.200,00"""),
    ("fatura_nubank_ocr.txt", "fatura_cartao/2026/06", """Fatura do cartao  N0BANK  Fechament0 25/06/2026  Total da fatura R$ 300,00
Pagamento minimo R$ 45,00  Vencimento 02/07/2026"""),
    # Armadilhas: o documento cita outra categoria, ou e conversa comum.
    ("contrato_cita_conta_de_luz.txt", "contrato/2026/02", """CONTRATO DE LOCACAO  LOCADOR Joao  LOCATARIO Maria
CLAUSULA QUINTA - O LOCATARIO pagara a conta de luz e a conta de agua (Copel e Sanepar).
Fica eleito o foro da comarca. Data de assinatura: 10/02/2026"""),
    ("mensagem_claro.txt", "_Revisar", "Oi, claro que sim! Te mando o arquivo amanha. Abracos, 12/03/2026"),
    ("extrato_bancario.txt", "_Revisar", """Extrato da conta corrente  Banco do Brasil  Periodo 01/03/2026 a 31/03/2026
Saldo anterior 1.000,00  Pagamento fatura do cartao -500,00  Pix recebido 200,00"""),
    ("luz_celesc_ano_curto.txt", "conta_luz/2019/08", """CELESC DISTRIBUICAO  Conta de energia eletrica  Referencia 08/19
Consumo 150 kWh  Vencimento 10/09/19"""),
    ("comprovante_pix_conta.txt", "comprovante/2026/03", """Comprovante de pagamento  Pagamento efetuado em 12/03/2026
Conta COPEL  Valor R$ 187,43  Autenticacao 0A1B  via Pix"""),
    ("rg_antigo.txt", "documento_pessoal/2009/03", """Carteira de identidade  Registro Geral 9.876.543-2  Filiacao
Data de expedicao 15/03/09  Naturalidade Curitiba  Nascimento 20/10/1985"""),
    ("agua_cedae_ocr.txt", "conta_agua/2026/01", """CEDAE  C0NTA DE AGUA  Hidr0metr0 A1234  Referencia: JAN/2026
Vencimento 05/02/2026"""),
    ("holerite_ocr.txt", "holerite/2026/02", "C0NTRACHEQUE  Empresa Z  C0mpetencia 02/2026  Liquid0 a receber 1.900,00"),
    ("receita_medica.txt", "_Revisar", "Receituario  Paciente Fulano  Amoxicilina 500mg 1 comprimido de 8/8h  15/03/2026"),
    ("rodape_so_pix.txt", "_Revisar", "Pague com Pix usando a chave pix CNPJ 12.345.678/0001-90"),
    # ----------------------- o que chega numa pasta de Downloads (uso real, 02/11)
    ("certificado-1234567.txt", "certificado/sem-data", """Aluno(a): Fulano de Tal  Curso ministrado por: Ciclano
Carga horaria: 10  Conteudo Programatico:
E com grande satisfacao que certificamos que o aluno concluiu com exito o curso de Logica de Programacao."""),
    ("exercicios_aula_3.txt", "estudos/sem-data", """Exercicios em sala · Aula 3 — Padroes de Projeto
Como rodar: javac *.java  java Main  Exercicio 1 · Quem e de quem"""),
    ("plano_marketing.txt", "estudos/sem-data", """VERDEBOX Mini Plano de Marketing | Os 4 Ps aplicados  Atividade em Grupo • Marketing
Preco: tres planos. Pix, cartao de credito, boleto e plano anual com 15% off.
VerdeBox atividade dos 4 Ps do marketing"""),
    ("montagem_robo.txt", "manual_tecnico/sem-data", """NM ROBOTICS EYEMECH 3.2 PARTS, TOOLS AND REQUIREMENTS
The design can be entirely 3D printed. Assembly is relatively easy."""),
    ("posicoes_pcb.txt", "manual_tecnico/sem-data", "Designator\tDevice\tFootprint\tMid X\tMid Y\n\"D1\"\t\"MBR120\"\t\"SOD-123\""),
    ("License.txt", "licenca/sem-data", "This work is licensed under https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    ("folder_lgpd.txt", "informativo/sem-data", """CAMPANHA DE CONSCIENTIZACAO  LGPD · LEI N 13.709/2018
SEUS DADOS, SUAS REGRAS.  COMO SE PROTEGER  Senha longa vence senha complicada"""),
    ("LEIAME.txt", "documentacao/sem-data", """PACOTE DE INSTALACAO  CONTEUDO DESTE ZIP
COMO IMPORTAR — escolha um dos caminhos  Instalacao manual: copie a pasta"""),
    ("mono-version.txt", "textos/sem-data", "8.0.29"),
    # ------------------------------------------------------- nao e de ninguem
    ("carta_banco_pix.txt", "_Revisar", """Prezado cliente, informamos que sua conta foi atualizada.
Para receber valores, cadastre sua chave Pix no aplicativo. Atenciosamente, Banco X. 10/03/2026"""),
    ("scan_ilegivel.txt", "_Revisar", "l  m   ..  R$ ?\n   |||  ~~~   __\n rn  ci   1O   0O\n      .,,."),
    ("lista_compras.txt", "_Revisar", "arroz, feijao, cafe, pao, leite, ovos, banana"),
]


class TestDocumentosReais(unittest.TestCase):
    """Cada documento do corpus, um subteste: o relatorio diz quais erram."""

    def test_cada_documento_vai_para_a_pasta_certa(self):
        with tempfile.TemporaryDirectory() as temporaria:
            base = Path(temporaria)
            config = Config(pasta_entrada=base / "entrada", pasta_saida=base / "organizados")
            config.preparar_pastas()
            pipeline = Pipeline(config, Catalogo(config.pasta_saida))

            erros = []
            for nome, esperada, texto in CORPUS:
                arquivo = config.pasta_entrada / nome
                arquivo.write_text(texto, encoding="utf-8")
                os.utime(arquivo, (MODIFICACAO_FALSA, MODIFICACAO_FALSA))
                resultado = pipeline.processar(arquivo)
                obtida = resultado.destino.parent.relative_to(config.pasta_saida).as_posix()
                with self.subTest(documento=nome):
                    self.assertEqual(obtida, esperada)
                if obtida != esperada:
                    erros.append(f"{nome}: foi para {obtida}, era {esperada}")

            certos = len(CORPUS) - len(erros)
            print(f"\n  {certos}/{len(CORPUS)} documentos na pasta certa")
            for erro in erros:
                print(f"    errado: {erro}")


if __name__ == "__main__":
    unittest.main()
