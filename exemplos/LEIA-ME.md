# Documentos de exemplo

Cinco documentos fictícios para experimentar o AutoDoc sem precisar usar contas
de verdade. Nenhum dado aqui é de pessoa real.

| Arquivo | Deve ser classificado como |
| --- | --- |
| `conta_energia_marco.txt` | Conta de energia — data vem do rótulo **VENCIMENTO** |
| `nota_fiscal_1234.txt` | Nota fiscal — data vem de **Data de emissão** |
| `comprovante_pix.txt` | Comprovante |
| `contrato_aluguel.txt` | Contrato |
| `scan0031_ilegivel.txt` | **Nada** — cai em `_Revisar/` |

O último existe de propósito. Um sistema de classificação que só é mostrado
acertando não diz nada sobre o que faz quando não tem certeza; este arquivo
imita uma digitalização ruim, e o AutoDoc prefere mandá-lo para revisão manual
a chutar uma categoria.

## Como usar

Os arquivos **não** ficam na pasta monitorada: o AutoDoc move o que processa
para fora dela, então usá-los direto daqui gastaria os exemplos na primeira vez.
Copie para a pasta monitorada:

```bash
cp exemplos/*.txt entrada/
```

Com o AutoDoc aberto, as linhas aparecem sozinhas na tela, sem recarregar nada.
