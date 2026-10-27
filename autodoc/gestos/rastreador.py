"""Rosto e corpo para o avatar 3D: os dois detectores e a pose que sai deles.

A mao ja vem da `Sessao` (camera.py), que a detecta em todo quadro para o
jogo. Aqui entram os outros dois modelos do MediaPipe, na mesma imagem crua:

    FaceLandmarker   expressoes e a matriz da cabeca (~3,7 MB)
    PoseLandmarker   ombros, cotovelos e pulsos, na versao "lite" (~5,5 MB)

Os tres juntos, mao inclusa, levam uns 21 ms por quadro num Mac com chip
Apple — 48 quadros por segundo, folga de sobra para os 30 da camera.

Os modelos sao baixados na primeira vez, como o da mao, e guardados no cache.
Sem eles (primeira vez e sem internet) o jogo abre igual, com a mascara 2D.
"""

from __future__ import annotations

import logging
import math

from autodoc.gestos import GestosIndisponiveis
from autodoc.gestos.camera import obter_modelo, pasta_cache
from autodoc.gestos.pose_avatar import PoseDoAvatar

logger = logging.getLogger(__name__)

_BASE = "https://storage.googleapis.com/mediapipe-models"
URL_ROSTO = f"{_BASE}/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
URL_CORPO = f"{_BASE}/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

# Sem rosto nem corpo por mais disto, ninguem esta jogando: a tela deixa o
# personagem respirar e piscar sozinho.
AUSENCIA = 1.0


class Rastreador:
    def __init__(self, mediapipe, BaseOptions, vision, modelo_rosto, modelo_corpo) -> None:
        self._mp = mediapipe
        modo = vision.RunningMode.VIDEO
        self._rosto = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(modelo_rosto)),
            running_mode=modo,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            num_faces=1,
        ))
        self._corpo = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(modelo_corpo)),
            running_mode=modo,
        ))
        self.pose = PoseDoAvatar()
        self._ultimo_ms = -1
        self._visto_em = -math.inf

    def calcular(self, rgb_crua, maos_mundo, agora: float) -> dict:
        """A pose do personagem neste quadro, com `presente` dizendo se ha alguem."""
        # O modo video exige carimbo de tempo estritamente crescente.
        ms = max(int(agora * 1000), self._ultimo_ms + 1)
        self._ultimo_ms = ms
        imagem = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb_crua)
        rosto = self._rosto.detect_for_video(imagem, ms)
        corpo = self._corpo.detect_for_video(imagem, ms)

        dados_rosto = None
        if rosto.face_blendshapes:
            nomes = {categoria.category_name: categoria.score for categoria in rosto.face_blendshapes[0]}
            matriz = rosto.facial_transformation_matrixes[0]
            dados_rosto = (nomes, matriz.tolist() if hasattr(matriz, "tolist") else matriz)
        dados_corpo = corpo.pose_world_landmarks[0] if corpo.pose_world_landmarks else None
        if dados_rosto or dados_corpo:
            self._visto_em = agora

        pose = self.pose.atualizar(dados_rosto, dados_corpo, maos_mundo, agora)
        pose["presente"] = agora - self._visto_em <= AUSENCIA
        return pose

    def fechar(self) -> None:
        self._rosto.close()
        self._corpo.close()


def abrir_rastreador(mediapipe, BaseOptions, vision) -> Rastreador | None:
    """O rastreador, ou None se os modelos nao puderem ser baixados."""
    try:
        rosto = obter_modelo(pasta_cache() / "face_landmarker.task", URL_ROSTO, "o modelo do rosto (3,7 MB)")
        corpo = obter_modelo(pasta_cache() / "pose_landmarker_lite.task", URL_CORPO, "o modelo do corpo (5,5 MB)")
    except GestosIndisponiveis as erro:
        logger.warning("sem o avatar 3D: %s", erro)
        return None
    return Rastreador(mediapipe, BaseOptions, vision, rosto, corpo)
