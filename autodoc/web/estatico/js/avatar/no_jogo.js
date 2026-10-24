/* O personagem 3D dentro da tela do Tetris.

   A pose chega do Python 30 vezes por segundo; a tela desenha a 60. Entre uma
   pose e outra o personagem desliza (suavizar), em vez de andar aos trancos.

   Por cima da pose entram duas coisas que só a tela sabe fazer:

     - sem ninguém na câmera (`presente` falso), o personagem pisca sozinho —
       o rosto dele não pode congelar de olho aberto;
     - os eventos do jogo viram reação: linha completa, ele comemora com os
       braços para cima; "TETRIS!", pula; fim de jogo, fica cabisbaixo.

   Este módulo só é carregado quando o avatar está ligado: quem joga com a
   máscara 2D não paga o three.js. Se o WebGL faltar, `criarAvatarNoJogo`
   falha, e a tela do Tetris pede ao servidor para voltar à máscara. */

import { construirPersonagem } from './construtor.js';
import { FICHAS } from './fichas.js';
import { criarPalco } from './palco.js';

// Quanto a pose desenhada anda em direção à recebida, a cada quadro de tela.
const SUAVIDADE = 0.35;

const DURACAO = { comemorar: 0.9, tetris: 1.6 };

/* ------------------------------------------------------------ apoio */

function suavizar(atual, alvo, fator) {
  if (typeof alvo === 'number') return typeof atual === 'number' ? atual + (alvo - atual) * fator : alvo;
  if (Array.isArray(alvo)) return alvo.map((valor, i) => suavizar(atual?.[i], valor, fator));
  if (alvo && typeof alvo === 'object') {
    return Object.fromEntries(Object.entries(alvo).map(([chave, valor]) => [chave, suavizar(atual?.[chave], valor, fator)]));
  }
  return alvo;
}

function normalizar([x, y, z, w]) {
  const tamanho = Math.hypot(x, y, z, w) || 1;
  return [x / tamanho, y / tamanho, z / tamanho, w / tamanho];
}

/** q · r: a rotação r aplicada depois de q, no espaço da cabeça. */
function multiplicar([ax, ay, az, aw], [bx, by, bz, bw]) {
  return [
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
    aw * bw - ax * bx - ay * by - az * bz,
  ];
}

const misturar = (a, b, peso) => a.map((valor, i) => valor + (b[i] - valor) * peso);

/** Os braços indo para cima, levando as patas junto. */
function levantarBracos(pose, peso) {
  for (const [lado, mao, sinal] of [['esquerdo', 'esquerda', -1], ['direito', 'direita', 1]]) {
    const braco = pose.bracos[lado];
    const pulsoAntes = braco.pulso;
    braco.cotovelo = misturar(braco.cotovelo, [sinal * 0.36, 0.44, 0.06], peso);
    braco.pulso = misturar(braco.pulso, [sinal * 0.38, 0.64, 0.1], peso);
    const desvio = braco.pulso.map((valor, i) => valor - pulsoAntes[i]);
    pose.maos[mao] = pose.maos[mao]?.map((ponto) => ponto.map((valor, i) => valor + desvio[i]));
  }
}

/* --------------------------------------------------------- o avatar */

export function criarAvatarNoJogo(canvas) {
  const palco = criarPalco(canvas); // falha aqui se não houver WebGL
  let nomeAtual = null;
  let alvo = null;
  let desenhada = null;
  let reacao = null; // { tipo, inicio }
  let triste = false;

  function receber(retrato, agora) {
    if (retrato.personagem !== nomeAtual && FICHAS[retrato.personagem]) {
      nomeAtual = retrato.personagem;
      palco.definirPersonagem(construirPersonagem(FICHAS[nomeAtual]));
    }
    if (retrato.pose) alvo = retrato.pose;
    triste = retrato.situacao === 'fim';
    for (const evento of retrato.eventos) {
      if (evento.tipo === 'linhas') {
        reacao = { tipo: evento.linhas.length >= 4 ? 'tetris' : 'comemorar', inicio: agora };
      }
    }
  }

  function desenhar(agora) {
    if (!alvo) return;
    desenhada = suavizar(desenhada ?? alvo, alvo, SUAVIDADE);
    desenhada.cabeca.rotacao = normalizar(desenhada.cabeca.rotacao);
    const segundos = agora / 1000;
    const pose = structuredClone(desenhada);

    if (!pose.presente) {
      // Ninguém na câmera: pisca sozinho, a cada três segundos e pouco.
      const piscada = segundos % 3.4 < 0.15 ? 1 : 0;
      pose.expressoes.piscar_esquerdo = piscada;
      pose.expressoes.piscar_direito = piscada;
    }

    if (reacao) {
      const decorrido = (agora - reacao.inicio) / 1000;
      const duracao = DURACAO[reacao.tipo];
      if (decorrido >= duracao) {
        reacao = null;
      } else {
        const p = decorrido / duracao;
        levantarBracos(pose, Math.sin(Math.PI * p));
        pose.expressoes.sorriso = 1;
        pose.expressoes.boca = Math.max(pose.expressoes.boca, 0.55);
        pose.feliz = true;
        if (reacao.tipo === 'tetris') pose.pulo = 0.1 * Math.abs(Math.sin(p * Math.PI * 2));
      }
    }

    if (triste) {
      pose.expressoes.sorriso = 0;
      pose.expressoes.boca = 0;
      pose.expressoes.sobrancelhas = 0.9;
      // Cabisbaixo: a cabeça inclina para a frente, uns 15 graus.
      pose.cabeca.rotacao = multiplicar(pose.cabeca.rotacao, [Math.sin(0.13), 0, 0, Math.cos(0.13)]);
    }

    palco.desenhar(pose, segundos);
  }

  return { receber, desenhar };
}
