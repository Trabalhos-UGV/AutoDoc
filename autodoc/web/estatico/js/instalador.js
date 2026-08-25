/* Tela de instalação do AutoDoc — frames 02 a 05 do protótipo.

   Os quatro frames eram capturas de 0, 35, 70 e 100%. Aqui existe um estado só,
   que caminha entre eles. Quem empurra esse estado é um "motor": em modo real,
   os eventos que o instalador de verdade emite enquanto executa as seis etapas;
   em demonstração, um roteiro com os mesmos textos do protótipo. */

import { ETAPAS, PASTA_MONITORADA } from './dados-demo.js';
import { detectarModo, esperar, estadoDoServidor } from './modo.js';

// Mantenha em passo com __version__ em autodoc/__init__.py.
const VERSAO = '0.3.0';

const MARCAS = { pronto: '✓', agora: '•', espera: '' };
const LINHAS_VISIVEIS = 6;

// Horários fixos do protótipo — um por etapa.
const HORARIOS = ['04:12', '04:14', '04:17', '04:19', '04:22', '04:25'];

const el = {
  tituloJanela: document.querySelector('[data-titulo-janela]'),
  fase: document.querySelector('[data-fase]'),
  etapaAtual: document.querySelector('[data-etapa-atual]'),
  percentual: document.querySelector('[data-percentual]'),
  barra: document.querySelector('[data-barra]'),
  preenchimento: document.querySelector('[data-barra-preenchimento]'),
  etapas: document.querySelector('[data-etapas]'),
  log: document.querySelector('[data-log]'),
  nota: document.querySelector('[data-nota]'),
  alterar: document.querySelector('[data-alterar]'),
  reiniciar: document.querySelector('[data-reiniciar]'),
  concluir: document.querySelector('[data-concluir]'),
};

const estado = {
  etapas: ETAPAS,
  indice: 0,
  progresso: 0,
  concluido: false,
  log: [],
  pasta: PASTA_MONITORADA,
};

let modo = 'demo';
let execucao = 0; // invalida o roteiro anterior quando alguém reinicia

/* ------------------------------------------------------------ desenho */

/** Monta as seis células de etapa uma única vez. */
function montarEtapas() {
  el.etapas.replaceChildren(
    ...estado.etapas.map((etapa) => {
      const item = document.createElement('li');
      item.className = 'etapa';
      item.dataset.estado = 'espera';
      item.innerHTML = `
        <span class="etapa__marca" aria-hidden="true"></span>
        <span class="etapa__texto">
          <span class="etapa__titulo"></span>
          <span class="etapa__detalhe"></span>
        </span>`;
      item.querySelector('.etapa__titulo').textContent = etapa.titulo;
      item.querySelector('.etapa__detalhe').textContent = etapa.detalhe;
      return item;
    })
  );
}

function estadoDaEtapa(indice) {
  if (estado.concluido || indice < estado.indice) return 'pronto';
  return indice === estado.indice ? 'agora' : 'espera';
}

function desenhar() {
  const total = estado.etapas.length;

  el.fase.textContent = estado.concluido
    ? 'Instalação concluída'
    : 'Instalando · não feche esta janela';

  el.etapaAtual.textContent = estado.concluido
    ? 'AutoDoc está pronto para usar'
    : estado.etapas[estado.indice].titulo;

  const percentual = Math.round(estado.progresso);
  el.percentual.textContent = `${percentual}%`;
  el.preenchimento.style.width = `${percentual}%`;
  el.barra.setAttribute('aria-valuenow', String(percentual));

  [...el.etapas.children].forEach((item, indice) => {
    const situacao = estadoDaEtapa(indice);
    item.dataset.estado = situacao;
    item.querySelector('.etapa__marca').textContent = MARCAS[situacao];

    // Os textos também são redesenhados: em modo real o detalhe de cada etapa
    // só existe depois que ela roda ("Python 3.13.12 encontrado"), e sem isto
    // a tela ficaria mostrando o texto de demonstração para sempre.
    const etapa = estado.etapas[indice];
    if (etapa) {
      item.querySelector('.etapa__titulo').textContent = etapa.titulo;
      item.querySelector('.etapa__detalhe').textContent = etapa.detalhe ?? '';
    }
  });

  el.log.replaceChildren(
    ...estado.log.slice(-LINHAS_VISIVEIS).map(({ hora, mensagem }) => {
      const linha = document.createElement('div');
      linha.className = 'log__linha';
      const h = document.createElement('span');
      h.className = 'log__hora';
      h.textContent = hora;
      const m = document.createElement('span');
      m.className = 'log__mensagem';
      m.textContent = mensagem;
      linha.append(h, m);
      return linha;
    })
  );

  el.nota.textContent = estado.concluido
    ? `Pasta monitorada: ${estado.pasta}`
    : `Etapa ${estado.indice + 1} de ${total}`;

  el.alterar.hidden = !estado.concluido;
  el.concluir.disabled = !estado.concluido;
  el.concluir.textContent = estado.concluido ? 'Abrir o AutoDoc' : 'Aguarde…';
}

function registrar(mensagem, indiceEtapa) {
  estado.log.push({ hora: HORARIOS[indiceEtapa] ?? HORARIOS.at(-1), mensagem });
}

/* ------------------------------------------------------------ motores */

/** Roteiro de demonstração: percorre as seis etapas com os logs do protótipo. */
async function motorDemonstracao() {
  const minha = ++execucao;
  const total = estado.etapas.length;

  for (let i = 0; i < total; i += 1) {
    if (minha !== execucao) return; // reiniciaram no meio
    estado.indice = i;
    desenhar();

    for (const mensagem of estado.etapas[i].logs) {
      await esperar(340);
      if (minha !== execucao) return;
      registrar(mensagem, i);
      estado.progresso = ((i + 0.5) / total) * 100;
      desenhar();
    }

    await esperar(260);
    if (minha !== execucao) return;
    estado.progresso = ((i + 1) / total) * 100;
    desenhar();
  }

  estado.concluido = true;
  estado.progresso = 100;
  desenhar();
}

/** Motor real: consome os eventos que o instalador emite enquanto trabalha. */
function motorReal() {
  const fonte = new EventSource('api/eventos');

  fonte.onmessage = (evento) => {
    const dados = JSON.parse(evento.data);

    if (dados.etapas) estado.etapas = dados.etapas;
    if (dados.pasta) estado.pasta = dados.pasta;
    if (typeof dados.indice === 'number') estado.indice = dados.indice;
    if (typeof dados.progresso === 'number') estado.progresso = dados.progresso;
    if (Array.isArray(dados.log)) estado.log = dados.log;

    estado.concluido = Boolean(dados.concluido) || estado.progresso >= 100;
    desenhar();

    if (dados.erro) {
      el.fase.textContent = 'A instalação parou';
      el.etapaAtual.textContent = dados.erro;
      fonte.close();
      return;
    }

    if (estado.concluido) fonte.close();
  };

  fonte.onerror = () => {
    registrar('conexão com o instalador perdida', estado.indice);
    desenhar();
    fonte.close();
  };

  fetch('api/instalar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pasta_entrada: estado.pasta }),
  }).catch(() => {});
}

function iniciarMotor() {
  return modo === 'real' ? motorReal() : motorDemonstracao();
}

/* ---------------------------------------------------------- interação */

el.reiniciar.addEventListener('click', () => {
  Object.assign(estado, { indice: 0, progresso: 0, concluido: false, log: [] });
  desenhar();
  iniciarMotor();
});

el.concluir.addEventListener('click', async () => {
  if (modo !== 'real') {
    window.location.href = 'app.html';
    return;
  }
  try {
    const resposta = await fetch('api/concluir', { method: 'POST' });
    const { url } = await resposta.json();
    window.location.href = url;
  } catch {
    registrar('não foi possível abrir o AutoDoc', estado.indice);
    desenhar();
  }
});

el.alterar.addEventListener('click', async () => {
  if (modo !== 'real') {
    const escolhida = window.prompt('Pasta a monitorar:', estado.pasta);
    if (escolhida) {
      estado.pasta = escolhida;
      desenhar();
    }
    return;
  }
  try {
    const resposta = await fetch('api/escolher-pasta', { method: 'POST' });
    const { caminho } = await resposta.json();
    if (caminho) {
      estado.pasta = caminho;
      desenhar();
    }
  } catch {
    /* o seletor nativo não abriu; a pasta atual continua valendo */
  }
});

/* ------------------------------------------------------------- início */

modo = await detectarModo();

if (modo === 'real') {
  // A pasta precisa vir do servidor. Sem isto o instalador mandaria de volta a
  // pasta de demonstração — um caminho do Windows que não existe nesta máquina
  // — e gravaria isso no config.json como se fosse a pasta a monitorar.
  const servidor = estadoDoServidor() ?? {};
  if (servidor.pasta) estado.pasta = servidor.pasta;
  if (servidor.versao) el.tituloJanela.textContent = `Instalador AutoDoc — ${servidor.versao}`;
}

if (modo !== 'real') el.tituloJanela.textContent = `Instalador AutoDoc — ${VERSAO}`;
montarEtapas();
desenhar();
iniciarMotor();
