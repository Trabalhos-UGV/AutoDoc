/* A vitrine: um personagem em pose de demonstração.

   avatar.html?personagem=caramelo — sem o parâmetro, o primeiro da lista.
   O parâmetro `t` congela o tempo num instante, para capturas sempre iguais. */

import { construirPersonagem } from './avatar/construtor.js';
import { poseDeDemonstracao } from './avatar/demo.js';
import { FICHAS } from './avatar/fichas.js';
import { criarPalco } from './avatar/palco.js';

const parametros = new URLSearchParams(location.search);
const nome = parametros.get('personagem') ?? Object.keys(FICHAS)[0];
const congelado = parametros.has('t') ? Number(parametros.get('t')) : null;

const palco = criarPalco(document.querySelector('[data-palco]'));
const personagem = construirPersonagem(FICHAS[nome]);
palco.definirPersonagem(personagem);
document.querySelector('[data-nome]').textContent = `· ${personagem.nome}`;

function quadro(agora) {
  const tempo = congelado ?? agora / 1000;
  palco.desenhar(poseDeDemonstracao(tempo), tempo);
  requestAnimationFrame(quadro);
}
requestAnimationFrame(quadro);
