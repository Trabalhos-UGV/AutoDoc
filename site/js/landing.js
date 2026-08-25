/* Landing do AutoDoc.

   Faz tres coisas: descobre em que sistema o visitante esta e promove o botao
   certo, mostra o tamanho real do pacote em vez de um numero escrito a mao, e
   avisa com todas as letras quando o pacote ainda nao foi gerado — o frame
   original anunciava "48,6 MB" de um arquivo que nunca existiu, e essa e
   exatamente a mentira que este arquivo evita. */

// Mantenha em passo com __version__ em autodoc/__init__.py.
const VERSAO = '0.3.0';

const PACOTES = {
  windows: { arquivo: 'autodoc-setup.pyz', rotulo: 'Baixar para Windows' },
  macos: { arquivo: 'AutoDoc-Setup-macOS.zip', rotulo: 'Baixar para macOS' },
  linux: { arquivo: 'autodoc-setup.pyz', rotulo: 'Baixar para Linux' },
};

/** Descobre o sistema do visitante. Devolve 'windows' | 'macos' | 'linux'. */
function detectarSistema() {
  // userAgentData é o caminho moderno; navigator.platform está obsoleto mas
  // continua sendo o único disponível no Safari e no Firefox.
  const bruto = (
    navigator.userAgentData?.platform ||
    navigator.platform ||
    navigator.userAgent ||
    ''
  ).toLowerCase();

  if (bruto.includes('win')) return 'windows';
  if (bruto.includes('mac') || bruto.includes('darwin')) return 'macos';
  if (bruto.includes('linux') || bruto.includes('x11') || bruto.includes('android')) {
    return 'linux';
  }
  return 'windows'; // o mesmo padrão do protótipo
}

/** Promove o botão do sistema detectado e rebaixa os outros dois. */
function promoverBotao(sistema) {
  const caixa = document.querySelector('[data-baixar]');
  const botoes = [...caixa.querySelectorAll('[data-sistema]')];

  botoes.forEach((botao) => {
    const meu = botao.dataset.sistema === sistema;
    botao.classList.toggle('ad-botao--primario', meu);
    botao.classList.toggle('ad-botao--secundario', !meu);

    if (meu) {
      botao.innerHTML = `<span aria-hidden="true">↓</span> ${PACOTES[sistema].rotulo}`;
      caixa.prepend(botao); // o principal vem primeiro na leitura e no foco
    } else {
      botao.textContent = { windows: 'Windows', macos: 'macOS', linux: 'Linux' }[
        botao.dataset.sistema
      ];
    }
  });

  document.querySelector('[data-arquivo]').textContent = PACOTES[sistema].arquivo;
  document.querySelector('[data-nota-macos]').hidden = sistema !== 'macos';
}

function formatarTamanho(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`;
}

function avisar(html) {
  const aviso = document.querySelector('[data-aviso]');
  aviso.innerHTML = html;
  aviso.hidden = false;
}

/** Confere se o pacote existe e mostra o tamanho de verdade. */
async function conferirPacote(sistema) {
  const tamanho = document.querySelector('[data-tamanho]');
  const caminho = `downloads/${PACOTES[sistema].arquivo}`;

  // Aberta com duplo clique (file://), a página não pode fazer requisição.
  if (location.protocol === 'file:') {
    tamanho.textContent = '—';
    avisar(
      'Esta página foi aberta direto do disco, então não dá para conferir o ' +
        'pacote. Sirva a pasta com <code>python3 -m http.server -d site 8000</code>.'
    );
    return;
  }

  try {
    const resposta = await fetch(caminho, { method: 'HEAD' });
    if (!resposta.ok) throw new Error(String(resposta.status));

    const bytes = Number(resposta.headers.get('content-length'));
    tamanho.textContent = bytes ? formatarTamanho(bytes) : '—';
  } catch {
    tamanho.textContent = '—';
    document
      .querySelectorAll('[data-sistema]')
      .forEach((botao) => botao.setAttribute('aria-disabled', 'true'));
    avisar(
      'O pacote de instalação ainda não foi gerado neste repositório. ' +
        'Ele é criado por <code>ferramentas/gerar_instalador.py</code>, que entra ' +
        'na próxima etapa do projeto. Enquanto isso, dá para rodar o AutoDoc em ' +
        'modo desenvolvedor com os comandos ao lado.'
    );
  }
}

function iniciar() {
  document.querySelector('[data-versao]').textContent = `v${VERSAO} · beta`;

  const sistema = detectarSistema();
  promoverBotao(sistema);
  conferirPacote(sistema);
}

iniciar();
