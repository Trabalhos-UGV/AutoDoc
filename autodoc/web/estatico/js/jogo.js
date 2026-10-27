/* O botão do Tetris na lateral do AutoDoc.

   O jogo roda em outro programa, aberto pelo servidor do app (POST
   /api/tetris). Esta tela só mostra em que pé as coisas estão, perguntando a
   /api/tetris: os gestos estão instalados? o Tetris está aberto? está
   instalando? deu erro?

   Enquanto algo está acontecendo — instalação, jogo aberto — a tela pergunta
   de novo de tempos em tempos. Parada, não pergunta nada.

   Em demonstração não há servidor para abrir o jogo, e o botão diz isso em vez
   de fingir que funciona. */

const el = {
  bloco: document.querySelector('[data-jogo]'),
  abrir: document.querySelector('[data-jogo-abrir]'),
  titulo: document.querySelector('[data-jogo-titulo]'),
  sub: document.querySelector('[data-jogo-sub]'),
  teclado: document.querySelector('[data-jogo-teclado]'),
  recado: document.querySelector('[data-jogo-recado]'),
};

// De quanto em quanto tempo perguntar, conforme a situação.
const ESPERA = { instalando: 1000, aberto: 2000, abrindo: 800 };

let situacao = 'parado';
let proxima = null;

function situacaoDe(estado) {
  if (estado.instalando) return 'instalando';
  if (estado.aberto) return 'aberto';
  return estado.gestos ? 'pronto' : 'sem-gestos';
}

function mostrar(estado) {
  situacao = situacaoDe(estado);
  el.bloco.dataset.situacao = situacao;

  const textos = {
    instalando: ['Instalando…', estado.mensagem ?? 'começando'],
    aberto: ['Tetris aberto', 'está em outra janela'],
    pronto: ['Tetris com a mão', 'jogue com a câmera'],
    'sem-gestos': ['Instalar os gestos', 'uns 150 MB, uma vez só'],
  };
  const [titulo, sub] = textos[situacao];
  el.titulo.textContent = titulo;
  el.sub.textContent = sub;
  el.sub.title = sub;
  el.abrir.disabled = situacao === 'instalando' || situacao === 'aberto';
  el.teclado.hidden = situacao === 'aberto';

  const recado = estado.erro ?? (situacao === 'pronto' && estado.mensagem ? estado.mensagem : null);
  el.recado.hidden = !recado;
  el.recado.textContent = recado ?? '';

  agendar(ESPERA[situacao]);
}

function agendar(espera) {
  clearTimeout(proxima);
  if (espera) proxima = setTimeout(consultar, espera);
}

async function pedir(rota, corpo) {
  const opcoes = corpo === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo),
  };
  const resposta = await fetch(rota, opcoes);
  if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
  return resposta.json();
}

async function consultar() {
  try {
    mostrar(await pedir('api/tetris'));
  } catch {
    // O servidor do app caiu ou está reiniciando: tenta de novo devagar.
    agendar(5000);
  }
}

async function agir(rota, corpo) {
  el.abrir.disabled = true;
  try {
    mostrar(await pedir(rota, corpo));
    // Erro na abertura (câmera negada, por exemplo) aparece em segundos:
    // pergunta logo em seguida para mostrar o motivo.
    if (situacao === 'aberto') agendar(ESPERA.abrindo);
  } catch {
    el.recado.hidden = false;
    el.recado.textContent = 'não foi possível falar com o AutoDoc';
    el.abrir.disabled = false;
  }
}

export function iniciarJogo(modo) {
  if (modo !== 'real') return; // o botão já nasce desabilitado, dizendo onde funciona

  el.abrir.addEventListener('click', () => {
    if (situacao === 'sem-gestos') agir('api/gestos/instalar', {});
    else agir('api/tetris', {});
  });
  el.teclado.addEventListener('click', () => agir('api/tetris', { sem_camera: true }));
  consultar();
}
