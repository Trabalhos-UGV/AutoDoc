"""O personagem que cobre o rosto de quem joga.

O detector de rosto do MediaPipe acha cada rosto do quadro — a caixa e seis
pontos: olhos, nariz, boca e orelhas. O personagem escolhido e desenhado por
cima, do tamanho da cabeca e inclinado pela linha dos olhos.

**A mascara entra antes de a imagem sair do programa.** O rosto e coberto aqui,
no quadro, antes do JPEG; o que chega a tela ja esta coberto. Desenhar por cima
na pagina deixaria a mascara um quadro atrasada em relacao ao video — e o
rosto apareceria justo quando a pessoa mexe a cabeca.

**Todo rosto do quadro e coberto**, nao so o de quem joga: quem passa atras
numa apresentacao tambem nao pediu para aparecer.

**Rosto perdido por um instante continua coberto.** Virar a cabeca, passar a
mao na frente: o detector perde o rosto por alguns quadros. A mascara fica no
ultimo lugar por meio segundo em vez de sumir e mostrar quem estava ali.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from autodoc.gestos.personagens import arquivo

URL_MODELO_ROSTO = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)

# O lado do personagem, em larguras da caixa do rosto. A caixa vai da testa ao
# queixo; o bicho tem orelha e juba, e precisa sobrar para cobrir o cabelo.
TAMANHO = 1.7

# Onde fica o centro do personagem, em alturas da caixa a partir do topo. Um
# pouco acima do meio: as orelhas do bicho sobem, o queixo dele nao desce.
CENTRO = 0.42

# Segundos que a mascara fica no ultimo lugar quando o rosto some.
MEMORIA = 0.5

# Quanto cada quadro novo pesa na posicao da mascara. Sem suavizar, a caixa do
# detector treme alguns pixels e o bicho tremia junto.
SUAVIZACAO = 0.5

# Acima deste deslocamento (em lados da mascara) nao se suaviza: a cabeca se
# mexeu de verdade, e misturar com a posicao velha deixaria a mascara para tras,
# com um pedaco do rosto aparecendo. Para tremida, suaviza; para movimento, pula.
SALTO = 0.25


@dataclass(frozen=True)
class Rosto:
    """Onde desenhar o personagem, em pixels do quadro."""

    x: float
    y: float
    lado: float
    angulo: float  # graus, positivo e a cabeca inclinada para o ombro direito da imagem


def rosto_da_deteccao(deteccao, largura: int, altura: int) -> Rosto:
    """Uma deteccao do MediaPipe vira um `Rosto`.

    A caixa vem em pixels e os pontos de 0 a 1; a inclinacao precisa dos olhos
    em pixels, por isso o tamanho do quadro.
    """
    caixa = deteccao.bounding_box
    olho_a, olho_b = deteccao.keypoints[0], deteccao.keypoints[1]
    angulo = math.degrees(math.atan2((olho_b.y - olho_a.y) * altura, (olho_b.x - olho_a.x) * largura))
    return Rosto(
        x=caixa.origin_x + caixa.width / 2,
        y=caixa.origin_y + caixa.height * CENTRO,
        lado=caixa.width * TAMANHO,
        angulo=angulo,
    )


def suavizar(anterior: Rosto | None, novo: Rosto, peso: float = SUAVIZACAO) -> Rosto:
    if anterior is None or math.dist((anterior.x, anterior.y), (novo.x, novo.y)) > novo.lado * SALTO:
        return novo
    return Rosto(*(a + (n - a) * peso for a, n in zip(
        (anterior.x, anterior.y, anterior.lado, anterior.angulo),
        (novo.x, novo.y, novo.lado, novo.angulo),
    )))


class Memoria:
    """Os rostos do ultimo quadro em que apareceram, por `MEMORIA` segundos."""

    def __init__(self, duracao: float = MEMORIA) -> None:
        self.duracao = duracao
        self._rostos: list[Rosto] = []
        self._visto_em = -math.inf

    def atualizar(self, rostos: list[Rosto], agora: float) -> list[Rosto]:
        if rostos:
            # Com um rosto so — o caso de quem joga —, suaviza contra o anterior.
            if len(rostos) == 1 and len(self._rostos) == 1:
                rostos = [suavizar(self._rostos[0], rostos[0])]
            self._rostos, self._visto_em = rostos, agora
            return rostos
        if agora - self._visto_em <= self.duracao:
            return self._rostos
        self._rostos = []
        return []


def sobrepor(cv2, numpy, imagem, png, rosto: Rosto) -> None:
    """Desenha o PNG (com transparencia) por cima de `imagem`, no lugar do rosto.

    Corta o que passar da borda do quadro: rosto no canto da camera e comum, e
    a fatia do numpy fora da imagem simplesmente nao existe.
    """
    lado = max(int(rosto.lado), 2)
    figura = cv2.resize(png, (lado, lado), interpolation=cv2.INTER_AREA)
    # No OpenCV o angulo positivo gira no sentido anti-horario; o dos olhos,
    # medido com o y para baixo, cresce no horario. Dai o sinal trocado.
    giro = cv2.getRotationMatrix2D((lado / 2, lado / 2), -rosto.angulo, 1.0)
    figura = cv2.warpAffine(figura, giro, (lado, lado), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))

    altura, largura = imagem.shape[:2]
    x0, y0 = int(rosto.x - lado / 2), int(rosto.y - lado / 2)
    esquerda, topo = max(x0, 0), max(y0, 0)
    direita, base = min(x0 + lado, largura), min(y0 + lado, altura)
    if direita <= esquerda or base <= topo:
        return
    recorte = figura[topo - y0:base - y0, esquerda - x0:direita - x0]
    alfa = recorte[:, :, 3:].astype(numpy.float32) / 255.0
    area = imagem[topo:base, esquerda:direita]
    area[:] = (recorte[:, :, :3] * alfa + area * (1.0 - alfa)).astype(numpy.uint8)


class DetectorDeRosto:
    """O `FaceDetector` do MediaPipe em modo video."""

    def __init__(self, mediapipe, BaseOptions, vision, modelo) -> None:
        self._mp = mediapipe
        opcoes = vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(modelo)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.5,
        )
        self._detector = vision.FaceDetector.create_from_options(opcoes)
        self._ultimo_ms = -1

    def detectar(self, quadro_rgb, agora: float) -> list[Rosto]:
        # O modo video exige carimbo de tempo estritamente crescente.
        ms = max(int(agora * 1000), self._ultimo_ms + 1)
        self._ultimo_ms = ms
        imagem = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=quadro_rgb)
        altura, largura = quadro_rgb.shape[:2]
        resultado = self._detector.detect_for_video(imagem, ms)
        return [rosto_da_deteccao(deteccao, largura, altura) for deteccao in resultado.detections]

    def fechar(self) -> None:
        self._detector.close()


class Mascara:
    """Cobre os rostos de cada quadro com o personagem escolhido."""

    def __init__(self, cv2, numpy, detector: DetectorDeRosto) -> None:
        self.cv2 = cv2
        self.numpy = numpy
        self.detector = detector
        self.memoria = Memoria()
        self._figuras: dict[str, object] = {}

    def aplicar(self, imagem, personagem: str | None, agora: float):
        """O quadro com os rostos cobertos. Sem personagem escolhido, nao mexe."""
        if personagem is None:
            return imagem
        rgb = self.cv2.cvtColor(imagem, self.cv2.COLOR_BGR2RGB)
        rostos = self.memoria.atualizar(self.detector.detectar(rgb, agora), agora)
        for rosto in rostos:
            sobrepor(self.cv2, self.numpy, imagem, self._figura(personagem), rosto)
        return imagem

    def _figura(self, personagem: str):
        if personagem not in self._figuras:
            self._figuras[personagem] = self.cv2.imread(str(arquivo(personagem)), self.cv2.IMREAD_UNCHANGED)
        return self._figuras[personagem]

    def fechar(self) -> None:
        self.detector.fechar()
