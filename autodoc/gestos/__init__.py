"""Controle do computador por gestos da mao, pela webcam.

Recurso opcional e separado do resto do AutoDoc: nada aqui e importado pelo
organizador de documentos, e a falta das dependencias (OpenCV, MediaPipe,
PyAutoGUI) so desliga este recurso.

A ideia e o conjunto de gestos vem do Gesture-Controlled-Virtual-Mouse, de
Viral Doshi (https://github.com/Viral-Doshi/Gesture-Controlled-Virtual-Mouse).
O codigo nao: o original e GPL-3.0, so roda no Windows e usa a API
`mp.solutions` do MediaPipe, que nao existe mais nas versoes atuais. Isto e uma
reescrita sobre a API de tarefas (`HandLandmarker`), com o que depende do
sistema isolado em `sistema.py`.

    reconhecimento.py  pontos da mao -> gesto (puro, sem camera)
    controle.py        gesto -> acao no mouse, rolagem, volume e brilho
    sistema.py         volume, brilho e rolagem por sistema operacional
    camera.py          laco da webcam e o modelo do MediaPipe
"""


class GestosIndisponiveis(RuntimeError):
    """Falta uma dependencia ou permissao para o controle por gestos."""
