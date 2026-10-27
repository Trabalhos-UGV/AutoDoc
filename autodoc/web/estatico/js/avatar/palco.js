/* O palco: cena, luz de estúdio e câmera onde o personagem aparece.

   A luz é o que separa "boneco bonito" de "formas cinzas":
     - um ambiente de estúdio (RoomEnvironment) que reflete nos materiais;
     - luz principal quente pela esquerda, com sombra suave;
     - contraluz fria por trás, que desenha o contorno contra o fundo escuro;
     - tom de cinema (ACES), para o pelo não estourar no branco.
   O fundo é transparente: quem pinta o fundo é o CSS, no mesmo tom da tela. */

import * as THREE from 'three';
import { RoomEnvironment } from '../../vendor/three/RoomEnvironment.js';

export function criarPalco(canvas) {
  const renderizador = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderizador.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderizador.outputColorSpace = THREE.SRGBColorSpace;
  renderizador.toneMapping = THREE.ACESFilmicToneMapping;
  renderizador.toneMappingExposure = 1.05;
  renderizador.shadowMap.enabled = true;
  renderizador.shadowMap.type = THREE.PCFSoftShadowMap;

  const cena = new THREE.Scene();
  const ambiente = new THREE.PMREMGenerator(renderizador);
  cena.environment = ambiente.fromScene(new RoomEnvironment(), 0.04).texture;
  cena.environmentIntensity = 0.55;

  const principal = new THREE.DirectionalLight('#fff1dc', 2.4);
  principal.position.set(-1.4, 2.2, 2.2);
  principal.castShadow = true;
  principal.shadow.mapSize.set(1024, 1024);
  principal.shadow.radius = 6;
  principal.shadow.camera.left = -1;
  principal.shadow.camera.right = 1;
  principal.shadow.camera.top = 1.5;
  principal.shadow.camera.bottom = -1;
  cena.add(principal);

  const contraluz = new THREE.DirectionalLight('#9fc6ff', 1.6);
  contraluz.position.set(1.2, 1.6, -2.2);
  cena.add(contraluz);

  // O chão só recebe sombra; ele mesmo é invisível.
  const chao = new THREE.Mesh(new THREE.CircleGeometry(1.2, 64), new THREE.ShadowMaterial({ opacity: 0.32 }));
  chao.rotation.x = -Math.PI / 2;
  chao.position.y = -0.18;
  chao.receiveShadow = true;
  cena.add(chao);

  // Enquadramento de busto: cabeça, tronco e braços grandes, como numa
  // chamada de vídeo. As pernas não existem — nem precisariam aparecer.
  const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 20);
  camera.position.set(0, 0.56, 3.5);
  camera.lookAt(0, 0.47, 0);

  let personagem = null;

  function ajustarTamanho() {
    const largura = canvas.clientWidth;
    const altura = canvas.clientHeight;
    if (!largura || !altura) return;
    renderizador.setSize(largura, altura, false);
    camera.aspect = largura / altura;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(ajustarTamanho).observe(canvas);
  ajustarTamanho();

  return {
    definirPersonagem(novo) {
      if (personagem) cena.remove(personagem.raiz);
      personagem = novo;
      cena.add(personagem.raiz);
    },
    desenhar(pose, tempo) {
      if (personagem && pose) personagem.aplicar(pose, tempo);
      renderizador.render(cena, camera);
    },
  };
}
