/* Tela de gerenciamento do AutoDoc — frames 06 a 17 do protótipo.

   Os doze frames eram estados da mesma tela. Aqui o estado é um só objeto:
   qual categoria está filtrando, o que foi digitado na busca e qual documento
   está selecionado. Tudo o mais é consequência disso.

   Em demonstração a filtragem acontece aqui, sobre os seis documentos do
   protótipo. Em modo real quem filtra é o servidor, que tem o índice do
   catálogo — por isso `carregar()` tem os dois caminhos. */

import {
  CATEGORIAS,
  DOCUMENTOS,
  ESTATISTICAS,
  PASTA_MONITORADA,
} from './dados-demo.js';
import { detectarModo, estadoDoServidor } from './modo.js';

const ESPERA_BUSCA = 180; // ms de silêncio antes de consultar

const el = {
  pasta: document.querySelector('[data-pasta]'),
  vigia: document.querySelector('[data-vigia]'),
  categorias: document.querySelector('[data-categorias]'),
  resumo: document.querySelector('[data-resumo]'),
  busca: document.querySelector('[data-busca]'),
  numeros: document.querySelector('[data-numeros]'),
  linhas: document.querySelector('[data-linhas]'),
  vazio: document.querySelector('[data-vazio]'),
  vazioTexto: document.querySelector('[data-vazio-texto]'),
  abrirPasta: document.querySelector('[data-abrir-pasta]'),
  aviso: document.querySelector('[data-aviso]'),
  detalhe: document.querySelector('[data-detalhe]'),
  indice: document.querySelector('[data-indice]'),
  dados: document.querySelector('[data-dados]'),
  backup: document.querySelector('[data-backup]'),
  detArquivo: document.querySelector('[data-det-arquivo]'),
  detEtiqueta: document.querySelector('[data-det-etiqueta]'),
  detConfianca: document.querySelector('[data-det-confianca]'),
  detRegra: document.querySelector('[data-det-regra]'),
  detChaves: document.querySelector('[data-det-chaves]'),
  detTrajeto: document.querySelector('[data-det-trajeto]'),
  detTrecho: document.querySelector('[data-det-trecho]'),
  acoes: document.querySelector('[data-acoes]'),
  abrirDoc: document.querySelector('[data-abrir-doc]'),
  revelarDoc: document.querySelector('[data-revelar-doc]'),
  corrigir: document.querySelector('[data-corrigir]'),
  categoriaNova: document.querySelector('[data-categoria-nova]'),
};

const estado = {
  documentos: DOCUMENTOS,
  categorias: CATEGORIAS,
  estatisticas: ESTATISTICAS,
  pasta: PASTA_MONITORADA,
  categoria: 'Todos',
  busca: '',
  categoriasPossiveis: [],
  selecionado: DOCUMENTOS[0]?.id ?? null,
  visiveis: DOCUMENTOS,
};

let modo = 'demo';

/* ------------------------------------------------------------- aviso */

/** Mostra (ou apaga) a faixa de aviso no topo da lista. */
function avisar(mensagem) {
  el.aviso.textContent = mensagem ?? '';
  el.aviso.hidden = !mensagem;
}

/* ------------------------------------------------------------ filtro */

/** Mesma correspondência de categorias do protótipo. */
function categoriaCombina(categoria, tipo) {
  switch (categoria) {
    case 'Todos': return true;
    case 'A revisar': return tipo === 'Não classificado';
    case 'Contas': return tipo.startsWith('Conta');
    case 'Notas fiscais': return tipo === 'Nota fiscal';
    case 'Comprovantes': return tipo === 'Comprovante';
    case 'Contratos': return tipo === 'Contrato';
    default: return true;
  }
}

/** Busca no nome, no tipo, no trecho lido, na data e nas palavras-chave. */
function buscaCombina(termo, documento) {
  if (!termo) return true;
  const feno = [
    documento.arquivo,
    documento.tipo,
    documento.trecho,
    documento.data,
    ...documento.chaves,
  ].join(' ').toLowerCase();
  return feno.includes(termo);
}

function filtrarLocalmente() {
  const termo = estado.busca.trim().toLowerCase();
  return estado.documentos.filter(
    (doc) => categoriaCombina(estado.categoria, doc.tipo) && buscaCombina(termo, doc)
  );
}

/* ------------------------------------------------------------ desenho */

const ehRevisar = (tipo) => tipo === 'Não classificado';

function desenharCategorias() {
  el.categorias.replaceChildren(
    ...estado.categorias.map((categoria) => {
      const botao = document.createElement('button');
      botao.type = 'button';
      botao.className = 'categoria';
      botao.setAttribute('aria-pressed', String(categoria.nome === estado.categoria));
      botao.innerHTML =
        '<span class="categoria__nome"></span><span class="categoria__contagem"></span>';
      botao.querySelector('.categoria__nome').textContent = categoria.nome;
      botao.querySelector('.categoria__contagem').textContent = categoria.contagem;
      botao.addEventListener('click', () => {
        estado.categoria = categoria.nome;
        carregar();
      });
      return botao;
    })
  );
}

function desenharNumeros() {
  const { arquivados, hoje, ocr, revisar } = estado.estatisticas;
  const celulas = [
    ['Arquivados', arquivados, false],
    ['Hoje', hoje, false],
    ['Via OCR', ocr, false],
    ['A revisar', revisar, true],
  ];

  el.numeros.replaceChildren(
    ...celulas.map(([rotulo, valor, atencao]) => {
      const item = document.createElement('li');
      item.innerHTML =
        '<span class="ad-rotulo"></span><span class="numeros__valor"></span>';
      item.querySelector('.ad-rotulo').textContent = rotulo;
      const alvo = item.querySelector('.numeros__valor');
      alvo.textContent = valor;
      if (atencao) alvo.classList.add('numeros__valor--atencao');
      return item;
    })
  );
}

function montarLinha(documento) {
  const linha = document.createElement('div');
  linha.className = 'linha';
  linha.setAttribute('role', 'row');
  linha.tabIndex = 0;
  linha.dataset.id = String(documento.id);
  linha.setAttribute('aria-selected', String(documento.id === estado.selecionado));

  linha.innerHTML = `
    <span role="gridcell">
      <span class="linha__arquivo"></span>
      <span class="linha__origem"></span>
    </span>
    <span role="gridcell"><span class="ad-etiqueta"></span></span>
    <span role="gridcell" class="linha__conf"><span class="linha__rotulo">conf.</span><span data-valor></span></span>
    <span role="gridcell" class="linha__data"><span class="linha__rotulo">data</span><span data-valor></span></span>
    <span role="gridcell" class="linha__destino"></span>`;

  linha.querySelector('.linha__arquivo').textContent = documento.arquivo;
  linha.querySelector('.linha__origem').textContent = documento.origem;

  const etiqueta = linha.querySelector('.ad-etiqueta');
  etiqueta.textContent = documento.tipo;
  etiqueta.classList.toggle('ad-etiqueta--revisar', ehRevisar(documento.tipo));

  const conf = linha.querySelector('.linha__conf');
  conf.querySelector('[data-valor]').textContent = documento.confianca;
  conf.classList.toggle('linha__conf--baixa', ehRevisar(documento.tipo));

  linha.querySelector('.linha__data [data-valor]').textContent = documento.data;
  linha.querySelector('.linha__destino').textContent = documento.destino;

  linha.addEventListener('click', () => selecionar(documento.id));
  linha.addEventListener('keydown', (evento) => {
    if (evento.key === 'Enter' || evento.key === ' ') {
      evento.preventDefault();
      selecionar(documento.id);
    }
    if (evento.key === 'ArrowDown' || evento.key === 'ArrowUp') {
      evento.preventDefault();
      const passo = evento.key === 'ArrowDown' ? 1 : -1;
      const irmaos = [...el.linhas.children];
      const vizinho = irmaos[irmaos.indexOf(linha) + passo];
      if (vizinho) {
        vizinho.focus();
        selecionar(Number(vizinho.dataset.id));
      }
    }
  });

  return linha;
}

function desenharTabela() {
  el.linhas.replaceChildren(...estado.visiveis.map(montarLinha));
  el.vazio.hidden = estado.visiveis.length > 0;

  // Lista vazia tem duas causas bem diferentes, e a tela precisa separá-las:
  // ou o filtro não achou nada, ou não há documento nenhum ainda — e nesse
  // segundo caso o que falta é alguém largar um arquivo na pasta.
  const semNenhum = estado.documentos.length === 0;
  const filtrando = estado.busca.trim() !== '' || estado.categoria !== 'Todos';

  if (semNenhum && !filtrando) {
    el.vazioTexto.textContent = modo === 'real'
      ? `Nenhum documento ainda. Largue um arquivo em ${estado.pasta} e ele aparece aqui sozinho.`
      : 'Nenhum documento para mostrar.';
    el.abrirPasta.hidden = modo !== 'real';
  } else {
    el.vazioTexto.textContent = 'Nenhum documento corresponde ao filtro.';
    el.abrirPasta.hidden = true;
  }

  el.resumo.textContent =
    `${estado.visiveis.length} de ${estado.documentos.length} registros` +
    ` · categoria ${estado.categoria}`;
}

function desenharDetalhe() {
  const doc = estado.documentos.find((d) => d.id === estado.selecionado);

  // Filtro sem resultado: não há o que explicar.
  el.detalhe.hidden = !doc;
  if (!doc) return;

  el.detArquivo.textContent = doc.arquivo;

  el.detEtiqueta.className = ehRevisar(doc.tipo)
    ? 'ad-etiqueta ad-etiqueta--revisar'
    : 'ad-etiqueta';
  el.detEtiqueta.textContent = doc.tipo;

  el.detConfianca.textContent = `confiança ${doc.confianca}`;
  el.detRegra.textContent = doc.regra;

  el.detChaves.replaceChildren(
    ...doc.chaves.map((chave) => {
      const marca = document.createElement('span');
      marca.className = 'ad-chave';
      marca.textContent = chave;
      return marca;
    })
  );

  el.detTrajeto.replaceChildren(
    ...doc.etapas.map((etapa) => {
      const passo = document.createElement('li');
      passo.className = 'trajeto__passo';
      passo.innerHTML = `
        <span class="trajeto__eixo" aria-hidden="true">
          <span class="trajeto__ponto"></span>
          <span class="trajeto__fio"></span>
        </span>
        <span>
          <h4 class="trajeto__titulo"></h4>
          <p class="trajeto__detalhe"></p>
        </span>`;
      passo.querySelector('.trajeto__titulo').textContent = etapa.titulo;
      passo.querySelector('.trajeto__detalhe').textContent = etapa.detalhe;
      return passo;
    })
  );

  el.detTrecho.textContent = doc.trecho;

  // Abrir e corrigir só existem em modo real: em demonstração não há arquivo
  // no disco para abrir nem catálogo para corrigir.
  el.acoes.hidden = modo !== 'real';
  el.corrigir.hidden = modo !== 'real' || estado.categoriasPossiveis.length === 0;

  if (!el.corrigir.hidden) {
    el.categoriaNova.replaceChildren(
      ...estado.categoriasPossiveis.map(({ chave, rotulo }) => {
        const opcao = document.createElement('option');
        opcao.value = chave;
        opcao.textContent = rotulo;
        opcao.selected = chave === doc.categoria;
        return opcao;
      })
    );
  }
}

function desenhar() {
  el.pasta.textContent = estado.pasta;
  desenharCategorias();
  desenharNumeros();
  desenharTabela();
  desenharDetalhe();
}

/* --------------------------------------------------------- interação */

function selecionar(id) {
  estado.selecionado = id;
  [...el.linhas.children].forEach((linha) => {
    linha.setAttribute('aria-selected', String(Number(linha.dataset.id) === id));
  });
  desenharDetalhe();
}

/** Recalcula o que está visível e mantém a seleção coerente com o filtro. */
async function carregar() {
  if (modo === 'real') {
    const busca = new URLSearchParams({ cat: estado.categoria, q: estado.busca });
    try {
      const resposta = await fetch(`api/documentos?${busca}`);
      const dados = await resposta.json();
      estado.visiveis = dados.linhas ?? [];
      if (dados.categorias) estado.categorias = dados.categorias;
      if (dados.estatisticas) estado.estatisticas = dados.estatisticas;
      // O servidor manda só o que passou no filtro; o detalhe precisa achar
      // o documento selecionado nessa mesma lista.
      estado.documentos = dados.todos ?? estado.visiveis;
      avisar(null);
    } catch {
      // Falha de verdade: dizer isso, em vez de deixar a tela parecendo vazia.
      estado.visiveis = [];
      estado.documentos = [];
      avisar('Não foi possível falar com o AutoDoc. A janela continua tentando;'
        + ' se persistir, feche e abra o programa de novo.');
    }
  } else {
    estado.visiveis = filtrarLocalmente();
  }

  const aindaVisivel = estado.visiveis.some((d) => d.id === estado.selecionado);
  if (!aindaVisivel) estado.selecionado = estado.visiveis[0]?.id ?? null;

  desenhar();
}

let temporizador;
/** Pede ao servidor que abra o documento selecionado no sistema. */
async function abrirDocumento(revelar) {
  if (estado.selecionado === null) return;
  try {
    const resposta = await fetch('api/abrir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: estado.selecionado, revelar }),
    });
    const { aberto } = await resposta.json();
    if (!aberto) avisar('O arquivo não foi encontrado onde o AutoDoc o deixou.');
  } catch {
    avisar('Não foi possível abrir o documento.');
  }
}

el.abrirDoc.addEventListener('click', () => abrirDocumento(false));
el.revelarDoc.addEventListener('click', () => abrirDocumento(true));

el.categoriaNova.addEventListener('change', async (evento) => {
  const categoria = evento.target.value;
  if (estado.selecionado === null) return;
  try {
    const resposta = await fetch('api/reclassificar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: estado.selecionado, categoria }),
    });
    const dados = await resposta.json();
    if (!dados.ok) {
      avisar(`Não foi possível corrigir: ${dados.erro}`);
      return;
    }
    avisar(null);
    // O arquivo mudou de pasta: contagens, filtros e destino mudam junto.
    await carregar();
  } catch {
    avisar('Não foi possível corrigir a categoria.');
  }
});

el.abrirPasta.addEventListener('click', () => {
  fetch('api/abrir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }).catch(() => avisar('Não foi possível abrir a pasta monitorada.'));
});

el.busca.addEventListener('input', (evento) => {
  estado.busca = evento.target.value;
  clearTimeout(temporizador);
  temporizador = setTimeout(carregar, ESPERA_BUSCA);
});

/* --------------------------------------------------- documentos novos */

/** O watchdog rodando de verdade: cada arquivo novo aparece sozinho. */
function ouvirNovidades() {
  const fonte = new EventSource('api/eventos');
  const indicador = el.vigia.closest('.lateral__vigia');

  const situacao = (texto, ativo) => {
    el.vigia.textContent = texto;
    indicador.dataset.ativo = ativo ? 'sim' : 'nao';
  };

  fonte.onopen = () => {
    situacao('watchdog ativo', true);
    avisar(null);
    carregar();
  };

  fonte.onmessage = (evento) => {
    const documento = JSON.parse(evento.data);
    estado.documentos = [documento, ...estado.documentos];
    carregar();
  };

  // Sem close() aqui de propósito: o EventSource volta a tentar sozinho, e
  // fechá-lo na primeira falha deixaria a tela morta até alguém recarregar a
  // página. Uma queda de conexão é um contratempo, não o fim do programa.
  fonte.onerror = () => situacao('reconectando…', false);
}

/* ------------------------------------------------------------- início */

modo = await detectarModo();

if (modo === 'real') {
  // Nada de demonstração sobrevive ao modo real. Sem isto a tela abria com os
  // seis documentos e as estatísticas do protótipo por baixo, e quando a API
  // falhava o `catch` só esvaziava a tabela — sobrava uma tela com números
  // inventados e nenhuma linha, sem jeito de saber se era "ainda não há
  // documento" ou "o servidor quebrou". É a mesma armadilha que já apareceu na
  // pasta monitorada e no instalador.
  Object.assign(estado, {
    documentos: [],
    visiveis: [],
    categorias: [],
    estatisticas: { arquivados: 0, hoje: 0, ocr: 0, revisar: 0 },
    selecionado: null,
  });

  // A barra lateral passa a descrever esta instalação, e não o protótipo: a
  // pasta que está mesmo sendo vigiada, o índice que a busca está usando e se
  // há backup configurado. Anunciar "sincronizado" sem backup seria mentira.
  const servidor = estadoDoServidor() ?? {};
  if (servidor.pasta) estado.pasta = servidor.pasta;
  if (servidor.busca) el.indice.textContent = servidor.busca;
  // Não há banco: o que o AutoDoc sabe mora dentro da pasta organizada, e a
  // lateral mostra qual é ela em vez de um nome de arquivo de banco.
  if (servidor.pasta_saida) el.dados.textContent = servidor.pasta_saida;

  if (Array.isArray(servidor.categorias_possiveis)) {
    estado.categoriasPossiveis = servidor.categorias_possiveis;
  }

  el.backup.textContent = servidor.backup ? 'sincronizado' : 'não configurado';
  el.backup.classList.toggle('lateral__ok', Boolean(servidor.backup));
}

if (modo === 'demo') {
  // Sem backend não há pasta sendo observada — dizer "watchdog ativo" seria
  // mentira, então a demonstração se identifica como tal.
  el.vigia.textContent = 'modo demonstração';
  el.vigia.closest('.lateral__vigia').dataset.ativo = 'nao';
} else {
  ouvirNovidades();
}

await carregar();
