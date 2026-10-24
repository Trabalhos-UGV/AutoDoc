/* O boneco 3D: monta o personagem a partir de uma ficha e o põe na pose.

   Nada aqui vem de arquivo de modelo: cada personagem é feito de formas
   arredondadas — esferas achatadas, cilindros, anéis —, com material de pelo
   (o "sheen" do three.js dá o aspecto aveludado) e brilho de verniz no nariz
   e nos olhos. É o estilo de boneco de vinil de jogos como Animal Crossing.

   A pose chega pronta do Python, no espaço do avatar:

     metros, origem no meio do peito, y para cima, x para a direita DA TELA,
     z para fora da tela (na direção de quem olha).

     pose = {
       cabeca:     { rotacao: [x, y, z, w] },          // quaternion
       expressoes: { piscar_esquerdo, piscar_direito, boca, sorriso, sobrancelhas },  // 0 a 1
       bracos:     { esquerdo: { ombro, cotovelo, pulso }, direito: { ... } },       // [x, y, z]
       maos:       { esquerda: [[x, y, z] × 21] | null, direita: ... },
       feliz:      true | false,   // abana o rabo depressa (comemoração)
       pulo:       metros,         // o boneco inteiro sobe (o "TETRIS!")
     }

   "Esquerdo" é sempre o lado esquerdo da tela: o boneco é um espelho de
   quem joga, como a imagem da câmera era.

   Os braços e as mãos não têm esqueleto com rotação de articulação: cada osso
   é um cilindro colocado entre dois pontos, com uma esfera em cada junta. É o
   jeito mais direto de a mão do boneco ficar exatamente onde estão os 21
   pontos do MediaPipe — e o visual de boneco articulado vem de brinde. */

import * as THREE from 'three';

const CIMA = new THREE.Vector3(0, 1, 0);

// Os dedos como o MediaPipe numera os pontos da mão.
const DEDOS = [
  [0, 1, 2, 3, 4],
  [5, 6, 7, 8],
  [9, 10, 11, 12],
  [13, 14, 15, 16],
  [17, 18, 19, 20],
];
const PALMA = [0, 1, 5, 9, 13, 17];

// Quanto os dedos encolhem para virar pata (1 = mão de gente).
const ENCOLHER_DEDOS = 0.72;

/* ------------------------------------------------------------ materiais */

function pelo(cor, brilho = '#fff3df') {
  return new THREE.MeshPhysicalMaterial({
    color: cor,
    roughness: 0.78,
    sheen: 1,
    sheenRoughness: 0.55,
    sheenColor: new THREE.Color(brilho),
  });
}

function verniz(cor, aspereza = 0.22) {
  return new THREE.MeshPhysicalMaterial({ color: cor, roughness: aspereza, clearcoat: 1, clearcoatRoughness: 0.12 });
}

function fosco(cor) {
  return new THREE.MeshStandardMaterial({ color: cor, roughness: 0.9 });
}

/* --------------------------------------------------------------- formas */

const esfera = new THREE.SphereGeometry(1, 48, 32);
const cilindro = new THREE.CylinderGeometry(1, 1, 1, 24, 1, true);

function bola(material, raio, escala = [1, 1, 1], posicao = [0, 0, 0]) {
  const malha = new THREE.Mesh(esfera, material);
  malha.scale.set(raio * escala[0], raio * escala[1], raio * escala[2]);
  malha.position.set(...posicao);
  malha.castShadow = true;
  return malha;
}

/** Um osso entre dois pontos: cilindro esticado e girado até lá. */
class Osso {
  constructor(material, raio, pai) {
    this.raio = raio;
    this.malha = new THREE.Mesh(cilindro, material);
    this.malha.castShadow = true;
    pai.add(this.malha);
  }

  entre(a, b) {
    const direcao = new THREE.Vector3().subVectors(b, a);
    const comprimento = direcao.length();
    this.malha.visible = comprimento > 1e-4;
    if (!this.malha.visible) return;
    this.malha.position.addVectors(a, b).multiplyScalar(0.5);
    this.malha.scale.set(this.raio, comprimento, this.raio);
    this.malha.quaternion.setFromUnitVectors(CIMA, direcao.divideScalar(comprimento));
  }
}

/** Uma junta: a esfera que arredonda o encontro de dois ossos. */
function junta(material, raio, pai) {
  const malha = bola(material, raio);
  pai.add(malha);
  return malha;
}

/* ------------------------------------------------------------ a cabeça */

// Olho mais fechado que isto vira o arquinho de desenho animado.
const OLHO_FECHADO = 0.55;

function montarOlho(lado, ficha, materiais) {
  const olho = new THREE.Group();
  olho.position.set(lado * 0.115, 0.045, 0.245);

  const aberto = new THREE.Group();
  olho.add(aberto);
  aberto.add(bola(materiais.esclera, 0.068, [1, 1.12, 0.62]));
  aberto.add(bola(materiais.iris, 0.048, [1, 1.1, 0.5], [0, -0.004, 0.03]));
  // O brilho no olho é o que dá vida ao boneco; sem ele o olhar fica morto.
  aberto.add(bola(materiais.reflexo, 0.014, [1, 1, 0.5], [lado * -0.013, 0.018, 0.056]));

  // Fechado, o olho é um arco — o jeito de desenho animado. Uma pálpebra
  // cobrindo a esfera inteira parecia um olho inchado.
  const fechado = new THREE.Mesh(new THREE.TorusGeometry(0.048, 0.009, 10, 32, Math.PI), materiais.iris);
  fechado.position.set(0, -0.012, 0.042);
  fechado.visible = false;
  olho.add(fechado);

  // A pálpebra pende de cima: crescer em y é ela descendo sobre o olho.
  const palpebra = new THREE.Group();
  palpebra.position.y = 0.078;
  const tampa = bola(materiais.pelo, 0.074, [1.08, 1, 0.72], [0, -0.074, 0.004]);
  palpebra.add(tampa);
  palpebra.visible = false;
  aberto.add(palpebra);

  const sobrancelha = bola(materiais.peloEscuro, 0.03, [1.5, 0.45, 0.5], [lado * 0.01, 0.105, 0.03]);
  sobrancelha.rotation.z = lado * -0.18;
  olho.add(sobrancelha);

  return { olho, aberto, fechado, palpebra, sobrancelha, alturaSobrancelha: sobrancelha.position.y };
}

function montarOrelha(lado, ficha, materiais) {
  const orelha = new THREE.Group();
  const caida = ficha.orelhas === 'caidas';
  // Caída: presa no alto da cabeça e pendurada pelo lado, quase vertical,
  // como orelha de vira-lata. Em pé: aponta para cima, um pouco aberta.
  orelha.position.set(lado * (caida ? 0.24 : 0.2), caida ? 0.16 : 0.2, caida ? 0.0 : -0.02);
  orelha.rotation.z = lado * (caida ? -2.82 : -0.35);
  orelha.rotation.x = caida ? 0.22 : -0.1;
  const forma = bola(materiais.peloEscuro, 0.1, caida ? [0.82, 1.75, 0.34] : [0.72, 1.55, 0.32], [0, 0.14, 0]);
  orelha.add(forma);
  if (!caida) orelha.add(bola(materiais.focinho, 0.06, [0.6, 1.3, 0.2], [0, 0.12, 0.022]));
  return orelha;
}

function montarCabeca(ficha, materiais) {
  const cabeca = new THREE.Group();
  cabeca.position.y = 0.42; // a nuca, onde a cabeça gira — logo acima da coleira

  const cranio = new THREE.Group();
  cranio.position.y = 0.2;
  cabeca.add(cranio);

  cranio.add(bola(materiais.pelo, 0.3, [1.08, 0.95, 0.96]));
  // A testa mais clara e as bochechas: o pelo de cachorro não é de uma cor só.
  cranio.add(bola(materiais.focinho, 0.155, [1.25, 0.82, 0.9], [0, -0.075, 0.2]));
  cranio.add(bola(materiais.nariz, 0.05, [1.35, 0.92, 0.9], [0, -0.03, 0.345]));
  cranio.add(bola(materiais.reflexo, 0.012, [1.4, 0.7, 0.6], [-0.015, -0.005, 0.383]));

  // A boca é uma cavidade escura que abre; a língua aparece com ela.
  const boca = new THREE.Group();
  boca.position.set(0, -0.125, 0.285);
  const cavidade = bola(materiais.boca, 0.075, [1, 1, 0.55]);
  const lingua = bola(materiais.lingua, 0.05, [1, 0.7, 0.8], [0, -0.03, 0.02]);
  boca.add(cavidade, lingua);
  cranio.add(boca);

  const olhos = [montarOlho(-1, ficha, materiais), montarOlho(1, ficha, materiais)];
  for (const { olho } of olhos) cranio.add(olho);

  const orelhas = [montarOrelha(-1, ficha, materiais), montarOrelha(1, ficha, materiais)];
  for (const orelha of orelhas) cranio.add(orelha);

  // Bochecha rosada: só um toque, em material translúcido.
  for (const lado of [-1, 1]) {
    cranio.add(bola(materiais.bochecha, 0.045, [1.2, 0.8, 0.3], [lado * 0.19, -0.06, 0.225]));
  }

  return { cabeca, cranio, boca, cavidade, lingua, olhos, orelhas };
}

/* ------------------------------------------------------------- o corpo */

function montarCorpo(ficha, materiais) {
  const corpo = new THREE.Group();
  const tronco = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.2, 12, 32), materiais.pelo);
  tronco.scale.set(1.15, 1, 0.9);
  tronco.position.y = 0.08;
  tronco.castShadow = true;
  corpo.add(tronco);
  corpo.add(bola(materiais.focinho, 0.15, [1, 1.2, 0.55], [0, 0.07, 0.14]));

  const coleira = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.028, 16, 48), materiais.coleira);
  coleira.rotation.x = Math.PI / 2;
  coleira.position.y = 0.43;
  coleira.castShadow = true;
  corpo.add(coleira);
  const plaquinha = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.012, 32), materiais.dourado);
  plaquinha.rotation.x = Math.PI / 2;
  plaquinha.position.set(0, 0.385, 0.165);
  corpo.add(plaquinha);

  const cauda = new THREE.Group();
  cauda.position.set(0, -0.02, -0.17);
  const pontaCauda = new THREE.Mesh(new THREE.CapsuleGeometry(0.04, 0.2, 8, 16), materiais.pelo);
  pontaCauda.position.y = 0.12;
  pontaCauda.castShadow = true;
  cauda.add(pontaCauda);
  cauda.rotation.x = -0.9;
  corpo.add(cauda);

  return { corpo, cauda };
}

/* ------------------------------------------------------------ as patas */

class Pata {
  constructor(materiais, pai) {
    this.grupo = new THREE.Group();
    pai.add(this.grupo);
    this.palma = bola(materiais.pelo, 1);
    this.almofada = bola(materiais.almofada, 1);
    this.grupo.add(this.palma, this.almofada);
    this.ossos = [];
    this.juntas = [];
    this.pontas = [];
    for (const dedo of DEDOS) {
      for (let i = 1; i < dedo.length; i++) this.ossos.push([new Osso(materiais.pelo, 1, this.grupo), dedo[i - 1], dedo[i]]);
      for (const indice of dedo.slice(1, -1)) this.juntas.push([junta(materiais.pelo, 1, this.grupo), indice]);
      this.pontas.push([junta(materiais.pelo, 1, this.grupo), dedo[dedo.length - 1]]);
    }
  }

  aplicar(pontos) {
    this.grupo.visible = Boolean(pontos);
    if (!pontos) return;
    const p = pontos.map(([x, y, z]) => new THREE.Vector3(x, y, z));
    // Pata, não mão: os dedos encolhem em direção à base, ficando curtos e
    // gordinhos. A posição de cada dedo continua sendo a da mão de verdade.
    for (const dedo of DEDOS) {
      const base = p[dedo[0] === 0 ? 1 : dedo[0]].clone();
      for (const indice of dedo.slice(1)) p[indice].sub(base).multiplyScalar(ENCOLHER_DEDOS).add(base);
    }
    // O tamanho da pata sai da própria mão: pulso até a base do médio.
    const palmo = p[0].distanceTo(p[9]);
    const raioDedo = palmo * 0.2;

    for (const [osso, a, b] of this.ossos) {
      osso.raio = raioDedo;
      osso.entre(p[a], p[b]);
    }
    for (const [esferaJunta, indice] of this.juntas) {
      esferaJunta.position.copy(p[indice]);
      esferaJunta.scale.setScalar(raioDedo);
    }
    for (const [ponta, indice] of this.pontas) {
      ponta.position.copy(p[indice]);
      ponta.scale.setScalar(raioDedo * 1.04);
    }

    // A palma: um disco gordinho orientado pela própria mão.
    const centro = PALMA.reduce((soma, i) => soma.add(p[i]), new THREE.Vector3()).multiplyScalar(1 / PALMA.length);
    const eixoY = new THREE.Vector3().subVectors(p[9], p[0]).normalize();
    const eixoX = new THREE.Vector3().subVectors(p[5], p[17]).normalize();
    const eixoZ = new THREE.Vector3().crossVectors(eixoX, eixoY).normalize();
    eixoX.crossVectors(eixoY, eixoZ);
    const orientacao = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(eixoX, eixoY, eixoZ));
    this.palma.position.copy(centro);
    this.palma.quaternion.copy(orientacao);
    this.palma.scale.set(palmo * 0.62, palmo * 0.62, palmo * 0.3);
    // A almofada da pata, do lado da palma.
    this.almofada.position.copy(centro).addScaledVector(eixoZ, palmo * 0.22);
    this.almofada.quaternion.copy(orientacao);
    this.almofada.scale.set(palmo * 0.32, palmo * 0.27, palmo * 0.12);
  }
}

class Braco {
  constructor(materiais, pai) {
    this.grupo = new THREE.Group();
    pai.add(this.grupo);
    this.ombro = junta(materiais.pelo, 0.075, this.grupo);
    this.cotovelo = junta(materiais.pelo, 0.062, this.grupo);
    this.pulso = junta(materiais.pelo, 0.056, this.grupo);
    this.superior = new Osso(materiais.pelo, 0.066, this.grupo);
    this.antebraco = new Osso(materiais.pelo, 0.058, this.grupo);
  }

  aplicar(braco) {
    this.grupo.visible = Boolean(braco);
    if (!braco) return;
    const [ombro, cotovelo, pulso] = [braco.ombro, braco.cotovelo, braco.pulso].map(([x, y, z]) => new THREE.Vector3(x, y, z));
    this.ombro.position.copy(ombro);
    this.cotovelo.position.copy(cotovelo);
    this.pulso.position.copy(pulso);
    this.superior.entre(ombro, cotovelo);
    this.antebraco.entre(cotovelo, pulso);
  }
}

/* ------------------------------------------------------------- o todo */

export function construirPersonagem(ficha) {
  const cores = ficha.cores;
  const materiais = {
    pelo: pelo(cores.pelo, cores.brilho),
    peloEscuro: pelo(cores.peloEscuro, cores.brilho),
    focinho: pelo(cores.focinho, '#ffffff'),
    nariz: verniz(cores.nariz),
    boca: fosco(cores.boca),
    lingua: verniz(cores.lingua, 0.45),
    esclera: verniz('#fbf8f2', 0.3),
    iris: verniz(cores.olhos, 0.15),
    reflexo: new THREE.MeshBasicMaterial({ color: '#ffffff' }),
    bochecha: new THREE.MeshStandardMaterial({ color: '#ff8a8a', transparent: true, opacity: 0.35, roughness: 1, depthWrite: false }),
    almofada: verniz(cores.almofada, 0.5),
    coleira: verniz(cores.coleira, 0.4),
    dourado: new THREE.MeshPhysicalMaterial({ color: '#e8b64c', metalness: 1, roughness: 0.25 }),
  };

  const raiz = new THREE.Group();
  const { corpo, cauda } = montarCorpo(ficha, materiais);
  const cabeca = montarCabeca(ficha, materiais);
  raiz.add(corpo, cabeca.cabeca);
  const bracos = { esquerdo: new Braco(materiais, raiz), direito: new Braco(materiais, raiz) };
  const patas = { esquerda: new Pata(materiais, raiz), direita: new Pata(materiais, raiz) };
  const rotacao = new THREE.Quaternion();

  function aplicar(pose, tempo) {
    rotacao.set(...pose.cabeca.rotacao);
    cabeca.cabeca.quaternion.slerp(rotacao, 1);

    // Respira sempre, de leve: parado demais, o boneco parece estátua.
    corpo.scale.set(1, 1 + Math.sin(tempo * 2.2) * 0.012, 1);
    raiz.position.y = pose.pulo ?? 0;

    const e = pose.expressoes;
    const [olhoEsquerdo, olhoDireito] = cabeca.olhos;
    // Pálpebra aberta fica escondida: achatada, ela aparecia de lado como um
    // risco escuro atravessando a testa.
    for (const [olho, piscar] of [[olhoEsquerdo, e.piscar_esquerdo], [olhoDireito, e.piscar_direito]]) {
      const fechado = piscar >= OLHO_FECHADO;
      olho.aberto.visible = !fechado;
      olho.fechado.visible = fechado;
      olho.palpebra.visible = !fechado && piscar > 0.03;
      olho.palpebra.scale.y = Math.max(piscar / OLHO_FECHADO, 0.03);
    }
    for (const olho of cabeca.olhos) olho.sobrancelha.position.y = olho.alturaSobrancelha + e.sobrancelhas * 0.03;

    // Boca: abre em altura; o sorriso alarga e levanta.
    cabeca.cavidade.scale.set(0.075 * (1 + e.sorriso * 0.45), 0.075 * (0.08 + e.boca * 0.95), 0.075 * 0.55);
    cabeca.boca.position.y = -0.125 + e.sorriso * 0.012;
    cabeca.lingua.visible = e.boca > 0.25;

    // As orelhas e a cauda balançam sozinhas: parado demais, o boneco parece estátua.
    for (const [i, orelha] of cabeca.orelhas.entries()) {
      orelha.rotation.x = (ficha.orelhas === 'caidas' ? 0.22 : -0.1) + Math.sin(tempo * 2.1 + i) * 0.05;
    }
    cauda.rotation.z = Math.sin(tempo * (pose.feliz ? 14 : 3)) * (pose.feliz ? 0.6 : 0.25);

    bracos.esquerdo.aplicar(pose.bracos.esquerdo);
    bracos.direito.aplicar(pose.bracos.direito);
    patas.esquerda.aplicar(pose.maos.esquerda);
    patas.direita.aplicar(pose.maos.direita);
  }

  return { raiz, aplicar, nome: ficha.nome };
}
