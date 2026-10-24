/* Uma pose de demonstração, sem câmera: o personagem acena, pisca e fala.

   Serve para três coisas: desenvolver o boneco sem ninguém na frente da
   câmera, mostrar os personagens na vitrine e na escolha, e — mais tarde — o
   jeito "parado" do personagem quando a pessoa sai da câmera. Segue o mesmo
   formato da pose que o Python manda (ver construtor.js). */

// Mão aberta, palma para a frente, no espaço da própria mão: pulso na origem,
// dedos para cima, polegar para o lado de +x. Metros, já no tamanho de pata.
const MAO_ABERTA = [
  [0, 0, 0],
  [0.05, 0.035, 0.01], [0.085, 0.07, 0.02], [0.11, 0.105, 0.025], [0.13, 0.135, 0.03],
  [0.045, 0.165, 0], [0.05, 0.225, 0], [0.053, 0.27, 0], [0.055, 0.305, 0],
  [0.008, 0.175, 0], [0.008, 0.245, 0], [0.008, 0.295, 0], [0.008, 0.335, 0],
  [-0.03, 0.165, 0], [-0.034, 0.228, 0], [-0.036, 0.272, 0], [-0.038, 0.305, 0],
  [-0.062, 0.145, 0], [-0.07, 0.19, 0], [-0.075, 0.222, 0], [-0.079, 0.25, 0],
];

function girar([x, y, z], angulo) {
  const c = Math.cos(angulo);
  const s = Math.sin(angulo);
  return [x * c - y * s, x * s + y * c, z];
}

/** A mão aberta (ou fechando, com `fechar` de 0 a 1), posta no pulso e girada. */
function mao(pulso, lado, angulo, fechar = 0) {
  return MAO_ABERTA.map(([x, y, z], i) => {
    // Fechar: cada dedo dobra para a frente, mais perto da ponta.
    const falange = i === 0 ? 0 : (i - 1) % 4;
    const base = MAO_ABERTA[i === 0 ? 0 : i - falange];
    const dobra = fechar * (falange / 3);
    const local = [lado * x, base[1] + (y - base[1]) * (1 - dobra * 0.6), z + (y - base[1]) * dobra * 0.9];
    const [gx, gy, gz] = girar(local, angulo);
    return [pulso[0] + gx, pulso[1] + gy, pulso[2] + gz];
  });
}

function quaternionDe(guinada, arfagem, rolagem) {
  // y (guinada), x (arfagem), z (rolagem), na ordem YXZ.
  const [cy, sy] = [Math.cos(guinada / 2), Math.sin(guinada / 2)];
  const [cx, sx] = [Math.cos(arfagem / 2), Math.sin(arfagem / 2)];
  const [cz, sz] = [Math.cos(rolagem / 2), Math.sin(rolagem / 2)];
  return [
    sx * cy * cz + cx * sy * sz,
    cx * sy * cz - sx * cy * sz,
    cx * cy * sz - sx * sy * cz,
    cx * cy * cz + sx * sy * sz,
  ];
}

export function poseDeDemonstracao(tempo) {
  const piscada = tempo % 3.2 < 0.14 ? 1 : 0;
  const fala = Math.max(0, Math.sin(tempo * 9)) * (Math.sin(tempo * 0.9) > 0.2 ? 0.7 : 0);
  const aceno = Math.sin(tempo * 5.5);

  // O braço direito (da tela) acena; o esquerdo descansa na frente do corpo.
  const ombroD = [0.23, 0.3, 0];
  const cotoveloD = [0.4, 0.42, 0.06];
  const pulsoD = [0.43 + aceno * 0.05, 0.66, 0.1];
  const ombroE = [-0.23, 0.3, 0];
  const cotoveloE = [-0.32, 0.08, 0.1];
  const pulsoE = [-0.2, -0.02, 0.24];

  return {
    cabeca: { rotacao: quaternionDe(Math.sin(tempo * 0.7) * 0.35, Math.sin(tempo * 1.1) * 0.08, Math.sin(tempo * 0.5) * 0.12) },
    expressoes: {
      piscar_esquerdo: piscada,
      piscar_direito: piscada,
      boca: fala,
      sorriso: 0.6 + Math.sin(tempo * 0.4) * 0.3,
      sobrancelhas: Math.max(0, Math.sin(tempo * 0.8)) * 0.8,
    },
    bracos: {
      esquerdo: { ombro: ombroE, cotovelo: cotoveloE, pulso: pulsoE },
      direito: { ombro: ombroD, cotovelo: cotoveloD, pulso: pulsoD },
    },
    maos: {
      esquerda: mao(pulsoE, -1, -1.2, 0.85),
      direita: mao(pulsoD, 1, -0.15 + aceno * 0.25, 0),
    },
    feliz: true,
  };
}
