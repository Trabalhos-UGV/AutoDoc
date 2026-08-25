/* Descobre se a página está sendo servida pelo backend do AutoDoc ou aberta
   solta, em demonstração.

   Em modo real os dados vêm da API; em demonstração vêm de dados-demo.js. A
   diferença fica registrada em body[data-modo], que o CSS usa para esconder a
   barra de navegação do protótipo. */

const TEMPO_LIMITE = 800;

// O que /api/estado respondeu, guardado para quem precisar depois: a pasta que
// está sendo monitorada, o índice de busca em uso, se há backup configurado.
let estadoServidor = null;

export async function detectarModo() {
  try {
    const resposta = await fetch('api/estado', {
      signal: AbortSignal.timeout(TEMPO_LIMITE),
    });
    if (resposta.ok) {
      estadoServidor = await resposta.json();
      document.body.dataset.modo = 'real';
      return 'real';
    }
  } catch {
    // Sem backend: servidor estático, file:// ou tempo esgotado.
  }

  document.body.dataset.modo = 'demo';
  return 'demo';
}

/** O que o servidor informou sobre si, ou null em modo demonstração. */
export const estadoDoServidor = () => estadoServidor;

/** Espera `ms`. Usado pelos roteiros de demonstração. */
export const esperar = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Respeita quem pediu menos animação no sistema. */
export const animacaoReduzida = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;
