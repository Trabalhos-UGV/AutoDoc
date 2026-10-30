/* Tela do Tetris por gestos.

   Esta tela não sabe jogar Tetris. As regras moram em autodoc/gestos/tetris.py,
   onde têm teste; aqui só se desenha o retrato que o servidor manda pelo SSE,
   30 vezes por segundo, e se anima a passagem de um retrato para o outro.

   O desenho roda a 60 quadros por segundo, independente dos retratos: a peça
   desliza da posição antiga para a nova em vez de pular, a linha completa
   pisca antes de sumir, o despencar deixa rastro. Cada animação nasce de um
   evento do retrato ("linhas", "travou", "despencou"...) e tem duração fixa.

   Com a câmera ligada, a imagem dela chega por /api/camera.mjpg num <img>
   comum, e o esqueleto da mão é desenhado por cima, num canvas do mesmo
   tamanho, com os pontos que vêm no retrato. No tabuleiro, uma faixa marca a
   coluna para onde a mão aponta: a peça está indo para lá.

   Com o avatar 3D, nada da câmera chega aqui: só a pose do personagem, que
   js/avatar/no_jogo.js desenha no lugar da imagem. Esse módulo só é carregado
   quando o avatar liga; se a máquina não tiver WebGL, a tela pede ao servidor
   para voltar à máscara 2D.

   O teclado manda cada tecla para /api/tecla. É o mesmo caminho que o gesto
   usa por dentro, então jogar pelo teclado testa o jogo de verdade. */

import { animacaoReduzida, detectarModo, estadoDoServidor } from './modo.js';

const TIPOS = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];

// Duração de cada animação, em ms.
const DURACAO = { deslizar: 80, linhas: 320, brilho: 180, rastro: 240 };

const BRINDES = { 2: 'Duas linhas', 3: 'Três linhas!', 4: 'TETRIS!' };

// Teclas que o jogo usa — o navegador não deve rolar a página com elas — e as
// que não podem repetir ao ficar apertadas: segurar o espaço não pode
// despencar uma peça atrás da outra.
const TECLAS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', ' ', 'x', 'z', 'c', 'p', 'r']);
const SEM_REPETICAO = new Set(['ArrowUp', ' ', 'x', 'z', 'c', 'p', 'r']);

const el = {
  modo: document.querySelector('[data-modo]'),
  modoTexto: document.querySelector('[data-modo-texto]'),
  camera: document.querySelector('[data-camera]'),
  cameraTitulo: document.querySelector('[data-camera-titulo]'),
  palco: document.querySelector('[data-palco]'),
  video: document.querySelector('[data-camera-video]'),
  maos: document.querySelector('[data-camera-maos]'),
  cameraVazia: document.querySelector('[data-camera-vazia]'),
  comandosGestos: document.querySelector('[data-comandos-gestos]'),
  comandosTeclas: document.querySelector('[data-comandos-teclas]'),
  moldura: document.querySelector('[data-moldura]'),
  tabuleiro: document.querySelector('[data-tabuleiro]'),
  aviso: document.querySelector('[data-aviso]'),
  avisoTitulo: document.querySelector('[data-aviso-titulo]'),
  avisoNumero: document.querySelector('[data-aviso-numero]'),
  avisoTexto: document.querySelector('[data-aviso-texto]'),
  brinde: document.querySelector('[data-brinde]'),
  pontos: document.querySelector('[data-pontos]'),
  nivel: document.querySelector('[data-nivel]'),
  linhas: document.querySelector('[data-linhas]'),
  proximas: [...document.querySelectorAll('[data-proxima]')],
  guardada: document.querySelector('[data-guardada]'),
  guardadaDica: document.querySelector('[data-guardada-dica]'),
  gestoAtual: document.querySelector('[data-gesto-atual]'),
  gestoNome: document.querySelector('[data-gesto-nome]'),
  escolha: document.querySelector('[data-escolha]'),
  escolhaGrade: document.querySelector('[data-escolha-grade]'),
  trocar: document.querySelector('[data-trocar]'),
};

const NOMES_DOS_GESTOS = {
  'sem mao': 'mostre a mão',
  mover: 'movendo',
  'pinca indicador': 'girando',
  'pinca medio': 'guardando',
  punho: 'despencando',
  descer: 'descendo rápido',
};

let atual = null; // o último retrato recebido
let animacoes = []; // {tipo, inicio, ...}
let deslize = null; // {linhas, colunas, inicio}: de onde a peça vem deslizando
let pontosExibidos = 0;
let reduzida = animacaoReduzida();
let avatar = null; // o personagem 3D, quando ligado
let avatarCarregando = false;
const cores = {};

/* ------------------------------------------------------------- cores */

function lerCores() {
  const estilo = getComputedStyle(document.documentElement);
  for (const tipo of TIPOS) cores[tipo] = estilo.getPropertyValue(`--tt-${tipo}`).trim();
  cores.campo = estilo.getPropertyValue('--tt-campo').trim();
  cores.grade = estilo.getPropertyValue('--tt-grade').trim();
  cores.principal = estilo.getPropertyValue('--ad-verde').trim();
  cores.secundaria = estilo.getPropertyValue('--ad-fraco').trim();
  cores.mira = estilo.getPropertyValue('--tt-mira').trim();
  cores.miraLinha = estilo.getPropertyValue('--tt-mira-linha').trim();
}

/** Mistura a cor com branco (f > 0) ou preto (f < 0). Aceita #rgb e #rrggbb. */
function tingir(hex, f) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = [...h].map((c) => c + c).join('');
  const canais = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  const alvo = f > 0 ? 255 : 0;
  const [r, g, b] = canais.map((c) => Math.round(c + (alvo - c) * Math.abs(f)));
  return `rgb(${r}, ${g}, ${b})`;
}

/* ------------------------------------------------------------ canvas */

/** Ajusta a resolução do canvas ao tamanho na tela e à densidade de pixels. */
function preparar(canvas) {
  const proporcao = window.devicePixelRatio || 1;
  const largura = Math.round(canvas.clientWidth * proporcao);
  const altura = Math.round(canvas.clientHeight * proporcao);
  if (canvas.width !== largura || canvas.height !== altura) {
    canvas.width = largura;
    canvas.height = altura;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(proporcao, 0, 0, proporcao, 0, 0);
  return { ctx, largura: canvas.clientWidth, altura: canvas.clientHeight };
}

function retangulo(ctx, x, y, l, a, raio) {
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, l, a, raio);
  else ctx.rect(x, y, l, a);
}

/** Uma célula de peça: degradê de cima para baixo e um fio de luz no topo. */
function celula(ctx, x, y, t, cor, alfa = 1) {
  const margem = Math.max(1, t * 0.06);
  const raio = t * 0.16;
  const lado = t - margem * 2;
  ctx.globalAlpha = alfa;

  const degrade = ctx.createLinearGradient(0, y, 0, y + t);
  degrade.addColorStop(0, tingir(cor, 0.2));
  degrade.addColorStop(1, tingir(cor, -0.08));
  ctx.fillStyle = degrade;
  retangulo(ctx, x + margem, y + margem, lado, lado, raio);
  ctx.fill();

  ctx.fillStyle = 'rgba(255, 255, 255, 0.24)';
  retangulo(ctx, x + margem + raio * 0.7, y + margem + t * 0.06, lado - raio * 1.4, Math.max(1, t * 0.07), t * 0.04);
  ctx.fill();

  ctx.globalAlpha = 1;
}

/** A sombra: só o contorno de onde a peça vai cair. */
function contorno(ctx, x, y, t, cor) {
  const margem = Math.max(1.5, t * 0.09);
  ctx.globalAlpha = 0.55;
  ctx.strokeStyle = cor;
  ctx.lineWidth = Math.max(1.25, t * 0.05);
  retangulo(ctx, x + margem, y + margem, t - margem * 2, t - margem * 2, t * 0.14);
  ctx.stroke();
  ctx.globalAlpha = 0.07;
  ctx.fillStyle = cor;
  ctx.fill();
  ctx.globalAlpha = 1;
}

const suave = (p) => 1 - (1 - p) ** 3;

/* ---------------------------------------------------------- tabuleiro */

function desenharTabuleiro(agora) {
  const { ctx, largura, altura } = preparar(el.tabuleiro);
  const t = largura / atual.largura;

  ctx.fillStyle = cores.campo;
  ctx.fillRect(0, 0, largura, altura);

  // Grade discreta: só para o olho medir a coluna.
  ctx.strokeStyle = cores.grade;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let c = 1; c < atual.largura; c++) {
    ctx.moveTo(Math.round(c * t) + 0.5, 0);
    ctx.lineTo(Math.round(c * t) + 0.5, altura);
  }
  for (let l = 1; l < atual.altura; l++) {
    ctx.moveTo(0, Math.round(l * t) + 0.5);
    ctx.lineTo(largura, Math.round(l * t) + 0.5);
  }
  ctx.stroke();

  // A mira: a coluna para onde a mão está apontando.
  const alvo = atual.controle.alvo;
  if (atual.camera && alvo !== null && atual.situacao === 'jogando') {
    ctx.fillStyle = cores.mira;
    ctx.fillRect(alvo * t, 0, t, altura);
    ctx.fillStyle = cores.miraLinha;
    ctx.fillRect(alvo * t, altura - 3, t, 3);
  }

  // Enquanto a linha completa pisca, o tabuleiro mostrado é o de antes dela sumir.
  const piscando = animacoes.find((a) => a.tipo === 'linhas');
  const quadro = piscando ? piscando.quadro : atual.tabuleiro;
  quadro.forEach((linha, l) => {
    [...linha].forEach((tipo, c) => {
      if (tipo !== '.') celula(ctx, c * t, l * t, t, cores[tipo]);
    });
  });

  if (piscando) {
    const p = Math.min((agora - piscando.inicio) / DURACAO.linhas, 1);
    ctx.fillStyle = `rgba(255, 250, 235, ${p < 0.45 ? p / 0.45 : (1 - p) / 0.55})`;
    for (const l of piscando.linhas) ctx.fillRect(0, l * t, largura, t);
  }

  if (atual.situacao !== 'fim' && !piscando) {
    const cor = cores[atual.peca.tipo];
    const ocupadas = new Set(atual.peca.celulas.map(([l, c]) => `${l},${c}`));
    for (const [l, c] of atual.sombra) {
      if (l >= 0 && !ocupadas.has(`${l},${c}`)) contorno(ctx, c * t, l * t, t, cor);
    }

    let dl = 0;
    let dc = 0;
    if (deslize) {
      const p = (agora - deslize.inicio) / DURACAO.deslizar;
      if (p >= 1) deslize = null;
      else {
        dl = deslize.linhas * (1 - suave(p));
        dc = deslize.colunas * (1 - suave(p));
      }
    }
    for (const [l, c] of atual.peca.celulas) {
      if (l + dl > -1) celula(ctx, (c + dc) * t, (l + dl) * t, t, cor);
    }
  }

  for (const animacao of animacoes) {
    const p = Math.min((agora - animacao.inicio) / DURACAO[animacao.tipo], 1);
    if (animacao.tipo === 'brilho') {
      ctx.fillStyle = `rgba(255, 255, 255, ${0.45 * (1 - p)})`;
      for (const [l, c] of animacao.celulas) {
        if (l >= 0) {
          retangulo(ctx, c * t + 1, l * t + 1, t - 2, t - 2, t * 0.16);
          ctx.fill();
        }
      }
    } else if (animacao.tipo === 'rastro') {
      for (const coluna of animacao.colunas) {
        const degrade = ctx.createLinearGradient(0, animacao.de * t, 0, animacao.ate * t);
        degrade.addColorStop(0, 'rgba(0, 0, 0, 0)');
        degrade.addColorStop(1, animacao.cor);
        ctx.globalAlpha = 0.35 * (1 - p);
        ctx.fillStyle = degrade;
        ctx.fillRect(coluna * t + t * 0.2, animacao.de * t, t * 0.6, (animacao.ate - animacao.de) * t);
        ctx.globalAlpha = 1;
      }
    }
  }
  animacoes = animacoes.filter((a) => agora - a.inicio < DURACAO[a.tipo]);
}

/** O esqueleto das mãos por cima da imagem da câmera. */
function desenharMaos() {
  const { ctx, largura, altura } = preparar(el.maos);
  ctx.clearRect(0, 0, largura, altura);
  if (!atual.camera) return;

  // A linha da descida rápida: daqui para baixo, a peça cai depressa.
  const zona = atual.controle.zona_descida * altura;
  if (atual.controle.descendo) {
    ctx.fillStyle = 'rgba(240, 193, 42, 0.14)';
    ctx.fillRect(0, zona, largura, altura - zona);
  }
  ctx.save();
  ctx.setLineDash([6, 5]);
  ctx.strokeStyle = 'rgba(240, 193, 42, 0.7)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, zona);
  ctx.lineTo(largura, zona);
  ctx.stroke();
  ctx.restore();
  // A etiqueta com fundo escuro: direto sobre a imagem da câmera não se lia.
  const etiqueta = '↓ desce rápido';
  ctx.font = '600 11px "Space Grotesk", sans-serif';
  const larguraEtiqueta = ctx.measureText(etiqueta).width + 12;
  ctx.fillStyle = 'rgba(12, 10, 7, 0.75)';
  retangulo(ctx, 6, zona + 4, larguraEtiqueta, 18, 5);
  ctx.fill();
  ctx.fillStyle = 'rgba(240, 193, 42, 0.95)';
  ctx.fillText(etiqueta, 12, zona + 17);

  for (const mao of atual.maos) {
    const pontos = mao.pontos.map(([x, y]) => [x * largura, y * altura]);
    ctx.strokeStyle = 'rgba(245, 242, 233, 0.7)';
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (const [a, b] of atual.conexoes) {
      ctx.moveTo(...pontos[a]);
      ctx.lineTo(...pontos[b]);
    }
    ctx.stroke();

    ctx.fillStyle = mao.principal ? cores.principal : cores.secundaria;
    for (const [x, y] of pontos) {
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

/** Uma peça sozinha, centralizada no canvas: a fila e a guardada. */
function desenharPeca(canvas, tipo) {
  // Quem usa leitor de tela ouve qual é a peça, e não só "próxima peça".
  canvas.dataset.rotulo ??= canvas.getAttribute('aria-label') ?? '';
  canvas.setAttribute('aria-label', `${canvas.dataset.rotulo}: ${tipo ? `peça ${tipo}` : 'nenhuma'}`);
  const { ctx, largura, altura } = preparar(canvas);
  ctx.clearRect(0, 0, largura, altura);
  if (!tipo || !atual.formas) return;

  const forma = atual.formas[tipo];
  const linhas = forma.map(([l]) => l);
  const colunas = forma.map(([, c]) => c);
  const alto = Math.max(...linhas) - Math.min(...linhas) + 1;
  const largo = Math.max(...colunas) - Math.min(...colunas) + 1;
  const t = Math.min(altura / (alto + 0.6), largura / (largo + 1), 20);
  const x0 = (largura - largo * t) / 2 - Math.min(...colunas) * t;
  const y0 = (altura - alto * t) / 2 - Math.min(...linhas) * t;
  for (const [l, c] of forma) celula(ctx, x0 + c * t, y0 + l * t, t, cores[tipo]);
}

/* ------------------------------------------------------------ painel */

function brindar(texto) {
  el.brinde.textContent = texto;
  el.brinde.classList.remove('ativo');
  void el.brinde.offsetWidth; // reinicia a animação mesmo com o mesmo texto
  el.brinde.classList.add('ativo');
}

function atualizarPainel(retrato) {
  el.nivel.textContent = retrato.nivel;
  el.linhas.textContent = retrato.linhas;

  const chave = `${retrato.proximas.join('')}|${retrato.guardada}`;
  if (chave !== atualizarPainel.chave) {
    atualizarPainel.chave = chave;
    el.proximas.forEach((canvas, i) => desenharPeca(canvas, retrato.proximas[i]));
    desenharPeca(el.guardada, retrato.guardada);
  }
  el.guardada.toggleAttribute('data-usada', !retrato.pode_guardar);
  // O quadro sozinho não ensina que dá para trazer a peça de volta.
  const gestoGuardar = retrato.camera ? 'polegar no médio' : 'tecla C';
  el.guardadaDica.textContent = !retrato.guardada
    ? `${gestoGuardar} guarda a peça`
    : retrato.pode_guardar
      ? `${gestoGuardar} troca`
      : 'troca de novo na próxima peça';

  const comCamera = retrato.camera;
  const comAvatar = comCamera && retrato.avatar;
  // A imagem só é pedida com a câmera ligada e sem o avatar, e é largada se
  // ela cair: sem o src, o navegador fecha a conexão do MJPEG.
  const querVideo = comCamera && !comAvatar;
  if (querVideo && !el.video.getAttribute('src')) el.video.src = 'api/camera.mjpg';
  if (!querVideo && el.video.getAttribute('src')) el.video.removeAttribute('src');
  el.video.hidden = !querVideo;
  el.maos.hidden = comAvatar;
  el.palco.hidden = !comAvatar;
  el.camera.toggleAttribute('data-avatar', comAvatar);
  el.cameraTitulo.textContent = comAvatar ? 'Você' : 'Sua mão';
  if (comAvatar) {
    el.camera.style.aspectRatio = '';
  } else if (retrato.camera_tamanho) {
    const [larguraCamera, alturaCamera] = retrato.camera_tamanho;
    el.camera.style.aspectRatio = `${larguraCamera} / ${alturaCamera}`;
  }

  el.modo.dataset.estado = comCamera ? 'camera' : 'teclado';
  el.modoTexto.textContent = comCamera ? 'câmera ligada' : 'jogando pelo teclado';
  el.comandosGestos.hidden = !comCamera;
  el.comandosTeclas.hidden = comCamera;
  el.cameraVazia.hidden = comCamera;
  el.gestoAtual.hidden = !comCamera;

  // Descer rápido não é um gesto próprio: é a mão aberta, só que baixa.
  const gesto = retrato.controle.descendo ? 'descer' : retrato.controle.gesto;
  el.gestoNome.textContent = NOMES_DOS_GESTOS[gesto] ?? gesto;
  for (const item of el.comandosGestos.children) {
    item.toggleAttribute('data-ativo', comCamera && item.dataset.gesto === gesto);
  }

  // Trocar só faz sentido havendo mais de um para escolher.
  el.trocar.hidden = !comCamera || retrato.escolhendo || retrato.personagens.length < 2;
  mostrarEscolha(retrato);
  avisar(retrato);
}

/* ------------------------------------------------- escolha do personagem */

function mostrarEscolha(retrato) {
  const abrindo = retrato.escolhendo && el.escolha.hidden;
  el.escolha.hidden = !retrato.escolhendo;
  if (!retrato.escolhendo) return;

  if (!el.escolhaGrade.children.length) {
    for (const personagem of retrato.personagens) {
      const botao = document.createElement('button');
      botao.type = 'button';
      botao.className = 'personagem';
      botao.dataset.nome = personagem.nome;
      const imagem = document.createElement('img');
      imagem.src = personagem.imagem;
      imagem.alt = '';
      botao.append(imagem, personagem.rotulo);
      botao.addEventListener('click', () => escolher(personagem.nome));
      el.escolhaGrade.append(botao);
    }
  }
  for (const botao of el.escolhaGrade.children) {
    botao.setAttribute('aria-pressed', String(botao.dataset.nome === retrato.personagem));
  }
  // Ao abrir, o foco vai para o personagem atual: Enter já escolhe, e o Tab
  // anda pela grade.
  if (abrindo) el.escolhaGrade.querySelector('[aria-pressed="true"]')?.focus();
}

function escolher(nome) {
  fetch('api/personagem', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nome }),
  }).catch(() => {});
}

function avisar(retrato) {
  const comCamera = retrato.camera;
  let titulo = null;
  let numero = '';
  let texto = '';

  if (retrato.situacao === 'fim') {
    titulo = 'Fim de jogo';
    numero = retrato.pontos.toLocaleString('pt-BR');
    texto = comCamera
      ? 'Encoste o polegar no indicador para jogar de novo.'
      : 'Aperte R para jogar de novo.';
  } else if (retrato.situacao === 'pausado') {
    const voltando = retrato.controle.contagem !== null;
    titulo = voltando ? 'Voltando…' : 'Pausado';
    texto = voltando
      ? 'Segure a mão onde está.'
      : comCamera
        ? 'Mostre a mão para a câmera para continuar.'
        : 'Aperte P para continuar.';
  }

  el.aviso.hidden = titulo === null;
  if (titulo !== null) {
    el.avisoTitulo.textContent = titulo;
    el.avisoNumero.textContent = numero;
    el.avisoTexto.textContent = texto;
  }
}

function semConexao() {
  el.modo.dataset.estado = '';
  el.modoTexto.textContent = 'sem conexão';
  el.aviso.hidden = false;
  el.avisoTitulo.textContent = 'O jogo não está rodando';
  el.avisoNumero.textContent = '';
  el.avisoTexto.textContent = 'Esta tela é aberta pelo AutoDoc: python main.py gestos --tetris';
}

/* ----------------------------------------------------------- retratos */

/** Se duas listas de células são a mesma forma, só deslocada. */
function mesmaForma(a, b) {
  if (a.length !== b.length) return false;
  const [l0, c0] = a[0];
  const [m0, d0] = b[0];
  return a.every(([l, c], i) => l - l0 === b[i][0] - m0 && c - c0 === b[i][1] - d0);
}

function receber(retrato) {
  const antes = atual;
  atual = retrato;
  const agora = performance.now();
  const travou = retrato.eventos.find((e) => e.tipo === 'travou');

  for (const evento of retrato.eventos) {
    if (evento.tipo === 'linhas' && antes) {
      // O tabuleiro de antes, com a peça que acabou de travar: é ele que pisca.
      const quadro = antes.tabuleiro.map((linha) => [...linha]);
      for (const [l, c] of travou?.celulas ?? []) {
        if (l >= 0) quadro[l][c] = antes.peca.tipo;
      }
      animacoes.push({ tipo: 'linhas', inicio: agora, linhas: evento.linhas, quadro: quadro.map((l) => l.join('')) });
      if (BRINDES[evento.linhas.length]) brindar(BRINDES[evento.linhas.length]);
    } else if (evento.tipo === 'travou' && !reduzida) {
      animacoes.push({ tipo: 'brilho', inicio: agora, celulas: evento.celulas });
    } else if (evento.tipo === 'despencou' && antes && travou && !reduzida) {
      const linhasDe = antes.peca.celulas.map(([l]) => l);
      const linhasAte = travou.celulas.map(([l]) => l);
      animacoes.push({
        tipo: 'rastro',
        inicio: agora,
        colunas: [...new Set(travou.celulas.map(([, c]) => c))],
        de: Math.max(Math.min(...linhasDe), 0),
        ate: Math.max(...linhasAte) + 1,
        cor: cores[antes.peca.tipo],
      });
      el.moldura.classList.remove('soco');
      void el.moldura.offsetWidth;
      el.moldura.classList.add('soco');
    } else if (evento.tipo === 'subiu_nivel') {
      el.nivel.classList.remove('subiu');
      void el.nivel.offsetWidth;
      el.nivel.classList.add('subiu');
      brindar(`Nível ${evento.nivel}`);
    }
  }

  // A peça desliza da posição anterior quando só andou; girou ou é outra, pula.
  if (!reduzida && antes && !travou && antes.peca.tipo === retrato.peca.tipo && mesmaForma(antes.peca.celulas, retrato.peca.celulas)) {
    const linhas = antes.peca.celulas[0][0] - retrato.peca.celulas[0][0];
    const colunas = antes.peca.celulas[0][1] - retrato.peca.celulas[0][1];
    if ((linhas || colunas) && Math.abs(linhas) + Math.abs(colunas) <= 3) {
      deslize = { linhas, colunas, inicio: agora };
    }
  }

  atualizarPainel(retrato);
  if (retrato.camera && retrato.avatar) ligarAvatar();
  avatar?.receber(retrato, agora);
}

/** Carrega o three.js e o personagem, uma vez só. Sem WebGL, volta à máscara. */
function ligarAvatar() {
  if (avatar || avatarCarregando) return;
  avatarCarregando = true;
  import('./avatar/no_jogo.js')
    .then(({ criarAvatarNoJogo }) => {
      avatar = criarAvatarNoJogo(el.palco);
      avatar.receber(atual, performance.now());
    })
    .catch(() => {
      fetch('api/avatar/desligar', { method: 'POST', body: '{}' }).catch(() => {});
    })
    .finally(() => {
      avatarCarregando = false;
    });
}

function quadro(agora) {
  if (atual) {
    desenharTabuleiro(agora);
    if (avatar && atual.avatar) avatar.desenhar(agora);
    else desenharMaos();
    // O placar conta até o valor novo em vez de saltar.
    const alvo = atual.pontos;
    pontosExibidos = Math.abs(alvo - pontosExibidos) < 1 ? alvo : pontosExibidos + (alvo - pontosExibidos) * 0.2;
    el.pontos.textContent = Math.round(pontosExibidos).toLocaleString('pt-BR');
  }
  requestAnimationFrame(quadro);
}

/* ------------------------------------------------------------ teclado */

function teclar(evento) {
  if (!el.escolha.hidden) return; // na escolha, as teclas são dos botões
  const tecla = evento.key.length === 1 ? evento.key.toLowerCase() : evento.key;
  if (!TECLAS.has(tecla)) return;
  evento.preventDefault();
  if (evento.repeat && SEM_REPETICAO.has(tecla)) return;
  fetch('api/tecla', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tecla }),
  }).catch(() => {});
}

/* ------------------------------------------------------------- início */

async function iniciar() {
  lerCores();
  window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', () => {
    reduzida = animacaoReduzida();
  });

  if ((await detectarModo()) !== 'real') {
    semConexao();
    return;
  }
  receber(estadoDoServidor());
  requestAnimationFrame(quadro);
  document.addEventListener('keydown', teclar);
  el.trocar.addEventListener('click', () => {
    fetch('api/personagem/trocar', { method: 'POST', body: '{}' }).catch(() => {});
  });
  // A fila e a guardada são redesenhadas quando a janela muda de tamanho.
  window.addEventListener('resize', () => {
    atualizarPainel.chave = null;
    if (atual) atualizarPainel(atual);
  });

  // Sem close() no onerror: o EventSource reconecta sozinho, e fechar na
  // primeira falha deixaria a tela morta até alguém recarregar.
  const fluxo = new EventSource('api/eventos');
  fluxo.onmessage = (mensagem) => {
    receber(JSON.parse(mensagem.data));
  };
  fluxo.onerror = () => {
    el.modoTexto.textContent = 'reconectando…';
  };
}

iniciar();
