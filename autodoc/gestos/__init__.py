"""Controle do computador por gestos da mao, pela webcam.

Recurso opcional e separado do resto do AutoDoc: nada aqui e importado pelo
organizador de documentos, e a falta das dependencias (OpenCV, MediaPipe,
PyAutoGUI) so desliga este recurso.

A ideia vem do Gesture-Controlled-Virtual-Mouse, de Viral Doshi
(https://github.com/Viral-Doshi/Gesture-Controlled-Virtual-Mouse). O codigo
nao: o original e GPL-3.0, so roda no Windows e usa a API `mp.solutions` do
MediaPipe, que nao existe mais nas versoes atuais. Isto e uma reescrita sobre a
API de tarefas (`HandLandmarker`), com o que depende do sistema isolado em
`sistema.py`. Os gestos tambem foram refeitos: os do original (V para armar o
clique, abaixar um dedo para clicar) falhavam demais na pratica — o porque
esta em `reconhecimento.py` e `cursor.py`.

    reconhecimento.py  pontos da mao -> gesto (puro, sem camera)
    cursor.py          posicao da mao -> posicao na tela, com filtro
    controle.py        gesto -> acao no mouse, rolagem, volume e brilho
    sistema.py         volume, brilho, rolagem e clique duplo por sistema
    camera.py          laco da webcam e o modelo do MediaPipe
    quadro.py          quadro de desenho para treinar os gestos
"""


class GestosIndisponiveis(RuntimeError):
    """Falta uma dependencia ou permissao para o controle por gestos."""
