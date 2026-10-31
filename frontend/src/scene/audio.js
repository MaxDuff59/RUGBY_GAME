// Le son des scènes de match, synthétisé par Web Audio (aucun fichier) : la rumeur du
// public (un bruit filtré qui respire), le sifflet de l'arbitre, l'impact d'un
// plaquage, le pied dans le ballon, la clameur d'un essai, les sifflets contre une
// pénalité. Rien ne sort quand le joueur a coupé le son.

export function createAudio() {
  const Context = window.AudioContext ?? window.webkitAudioContext;
  if (!Context) return silent();
  let ctx;
  try {
    ctx = new Context();
  } catch {
    return silent();
  }
  const master = ctx.createGain();
  master.gain.value = 0;
  master.connect(ctx.destination);

  // Bruit rose approché, en boucle : la matière de la foule et des chocs.
  const length = ctx.sampleRate * 2;
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  let b0 = 0;
  let b1 = 0;
  let b2 = 0;
  for (let i = 0; i < length; i++) {
    const white = Math.random() * 2 - 1;
    b0 = 0.997 * b0 + white * 0.029591;
    b1 = 0.985 * b1 + white * 0.032534;
    b2 = 0.95 * b2 + white * 0.048056;
    data[i] = (b0 + b1 + b2 + white * 0.05) * 0.6;
  }
  const noise = () => {
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    source.loopStart = Math.random();
    return source;
  };

  // La rumeur : deux bandes de bruit, une grave (le stade), une médiane (les voix),
  // et une lente respiration.
  const crowd = ctx.createGain();
  crowd.gain.value = 0.25;
  crowd.connect(master);
  const bands = [
    [380, 0.8, 1],
    [900, 1.2, 0.55],
  ].map(([frequency, q, gain]) => {
    const source = noise();
    const filter = ctx.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.value = frequency;
    filter.Q.value = q;
    const level = ctx.createGain();
    level.gain.value = gain;
    source.connect(filter).connect(level).connect(crowd);
    source.start();
    return { source, filter };
  });
  const breath = ctx.createOscillator();
  breath.frequency.value = 0.21;
  const breathDepth = ctx.createGain();
  breathDepth.gain.value = 0.06;
  breath.connect(breathDepth).connect(crowd.gain);
  breath.start();

  const now = () => ctx.currentTime;

  // Un éclat de bruit filtré : clameur, impact, sifflets du public.
  function burst({ frequency, q = 1, type = "bandpass", peak, attack, hold, release, at = now() }) {
    const source = noise();
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = frequency;
    filter.Q.value = q;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, at);
    gain.gain.linearRampToValueAtTime(peak, at + attack);
    gain.gain.setValueAtTime(peak, at + attack + hold);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + attack + hold + release);
    source.connect(filter).connect(gain).connect(master);
    source.start(at);
    source.stop(at + attack + hold + release + 0.05);
    return filter;
  }

  function tone({ frequency, type = "sine", peak, attack, release, slide = 1, at = now() }) {
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, at);
    osc.frequency.exponentialRampToValueAtTime(frequency * slide, at + attack + release);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, at);
    gain.gain.linearRampToValueAtTime(peak, at + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + attack + release);
    osc.connect(gain).connect(master);
    osc.start(at);
    osc.stop(at + attack + release + 0.05);
    return osc;
  }

  const sounds = {
    // Sifflet à bille : une note aiguë roulée par une modulation rapide. `long` : le
    // coup de sifflet d'une pénalité ou d'un essai.
    whistle(long = false) {
      const at = now();
      const duration = long ? 0.9 : 0.35;
      const osc = ctx.createOscillator();
      osc.type = "triangle";
      osc.frequency.value = 2900;
      const trill = ctx.createOscillator();
      trill.frequency.value = 28;
      const depth = ctx.createGain();
      depth.gain.value = 140;
      trill.connect(depth).connect(osc.frequency);
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0, at);
      gain.gain.linearRampToValueAtTime(0.16, at + 0.03);
      gain.gain.setValueAtTime(0.16, at + duration - 0.08);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);
      osc.connect(gain).connect(master);
      osc.start(at);
      trill.start(at);
      osc.stop(at + duration + 0.05);
      trill.stop(at + duration + 0.05);
    },
    // Choc d'un plaquage : un coup sourd et le froissement des corps.
    impact() {
      tone({ frequency: 90, peak: 0.5, attack: 0.005, release: 0.22, slide: 0.5 });
      burst({ frequency: 700, q: 0.7, peak: 0.35, attack: 0.005, hold: 0.03, release: 0.18 });
    },
    // Le pied dans le ballon.
    kick() {
      tone({ frequency: 160, peak: 0.45, attack: 0.002, release: 0.12, slide: 0.6 });
      burst({ frequency: 2400, q: 1.5, peak: 0.12, attack: 0.002, hold: 0.01, release: 0.05 });
    },
    // La clameur d'un essai ou d'une pénalité passée : le stade se lève d'un coup.
    roar() {
      burst({ frequency: 650, q: 0.5, peak: 0.55, attack: 0.25, hold: 1.6, release: 2.2 });
      burst({ frequency: 1500, q: 0.9, peak: 0.25, attack: 0.3, hold: 1.2, release: 1.8 });
    },
    // Un « oh » de déception.
    groan() {
      const filter = burst({ frequency: 520, q: 1.2, peak: 0.3, attack: 0.15, hold: 0.5, release: 1.2 });
      filter.frequency.exponentialRampToValueAtTime(300, now() + 1.6);
    },
    // Les sifflets du public contre une décision.
    boo() {
      const at = now();
      for (let i = 0; i < 7; i++) {
        tone({ frequency: 2300 + Math.random() * 1400, type: "sine", peak: 0.03, attack: 0.2, release: 1.4 + Math.random(), slide: 0.92, at: at + Math.random() * 0.4 });
      }
      burst({ frequency: 260, q: 1.5, peak: 0.22, attack: 0.3, hold: 0.8, release: 1.2 });
    },
  };

  let muted = false;
  return {
    // Le niveau de la rumeur : 0 (calme) à 1 (le stade debout).
    setTension(level) {
      if (ctx.state === "closed") return;
      crowd.gain.setTargetAtTime(0.2 + level * 0.35, now(), 0.6);
      bands[1].filter.frequency.setTargetAtTime(900 + level * 400, now(), 0.6);
    },
    play(name, ...args) {
      if (muted || ctx.state !== "running") return;
      sounds[name]?.(...args);
    },
    setMuted(value) {
      muted = value;
      if (ctx.state === "closed") return;
      master.gain.setTargetAtTime(value ? 0 : 0.8, now(), 0.15);
      if (!value && ctx.state === "suspended") ctx.resume().catch(() => {});
    },
    // Le navigateur garde le son en suspens jusqu'au premier geste du joueur.
    wake() {
      if (!muted && ctx.state === "suspended") ctx.resume().catch(() => {});
    },
    dispose() {
      bands.forEach(({ source }) => source.stop());
      breath.stop();
      ctx.close().catch(() => {});
    },
  };
}

function silent() {
  return { setTension() {}, play() {}, setMuted() {}, wake() {}, dispose() {} };
}
