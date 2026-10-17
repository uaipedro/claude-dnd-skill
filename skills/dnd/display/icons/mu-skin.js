// Skin "MU" da tela de jogo: janela de personagem com inventário em grade e
// barra de skills com orbes. Lê os mesmos dados do painel original (_playerData),
// então tudo que o push_stats.py manda aparece aqui. F8 liga/desliga.
(function () {
  'use strict';

  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = '/icons/mu-skin.css?v=' + Date.now();
  document.head.appendChild(css);

  let catalogo = { itens: [], magias: {} };
  let retratos = {};
  const semAcento = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function ligada() {
    try { return localStorage.getItem('mu-skin') !== 'off'; } catch (e) { return true; }
  }
  function aplicarLigada(on) {
    document.body.classList.toggle('mu', on);
    barra.style.display = on ? '' : 'none';
    direita.style.display = on ? '' : 'none';
    party.style.display = on ? '' : 'none';
    try { localStorage.setItem('mu-skin', on ? 'on' : 'off'); } catch (e) {}
  }

  // ── Tooltip ─────────────────────────────────────────────────────
  const tip = document.createElement('div');
  tip.id = 'mu-tip';
  document.body.appendChild(tip);

  function htmlTip(d) {
    let h = `<div class="t-nome r-${d.raridade || 'comum'}">${esc(d.nome)}</div>`;
    if (d.tipo) h += `<div class="t-tipo">${esc(d.tipo)}</div>`;
    (d.linhas || []).forEach(l => { h += `<div class="t-lin">${esc(l)}</div>`; });
    (d.opcoes || []).forEach(l => { h += `<div class="t-op">${esc(l)}</div>`; });
    if (d.aviso) h += `<div class="t-aviso">${esc(d.aviso)}</div>`;
    if (d.desc) h += `<div class="t-desc">${esc(d.desc)}</div>`;
    return h;
  }
  function moverTip(ev) {
    const pad = 16, r = tip.getBoundingClientRect();
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
    tip.style.left = Math.max(8, x) + 'px';
    tip.style.top = Math.max(8, y) + 'px';
  }
  function comTip(el, dados) {
    el.addEventListener('mouseenter', ev => { tip.innerHTML = htmlTip(dados()); tip.classList.add('on'); moverTip(ev); });
    el.addEventListener('mousemove', moverTip);
    el.addEventListener('mouseleave', () => tip.classList.remove('on'));
  }

  // botão ⚙ abre/fecha as configurações da tela
  const cfg = document.createElement('button');
  cfg.id = 'mu-config-btn'; cfg.type = 'button'; cfg.title = 'Configurações (C)'; cfg.textContent = '⚙ Propriedades';
  cfg.addEventListener('click', () => document.body.classList.toggle('mu-config'));
  // fileira de botões no canto inferior direito: Dados, Galeria, Propriedades
  const botoes = document.createElement('div');
  botoes.id = 'mu-botoes';
  document.body.appendChild(botoes);
  botoes.appendChild(cfg);
  function juntarBotoes() {
    ['dados-btn', 'galeria-btn', 'dm-help-btn'].forEach((id, i) => {
      const b = document.getElementById(id);
      if (b && b.parentNode !== botoes) botoes.insertBefore(b, botoes.children[i] || cfg);
    });
  }
  // ── Autoplay de voz: começa a falar assim que o texto chega, sem esperar a digitação ──
  const voz = document.createElement('button');
  voz.id = 'mu-voz-btn'; voz.type = 'button'; voz.title = 'Narração automática (V)';
  botoes.insertBefore(voz, cfg);
  let vozOn = false;
  try { vozOn = localStorage.getItem('mu-voz') === '1'; } catch (e) {}
  const filaVoz = [];
  let vozFonte = null, vozTocando = false, vozGeracao = 0;
  const carregadaEm = Date.now();

  function pintarVoz() {
    voz.textContent = vozOn ? '🔊 Voz: on' : '🔈 Voz: off';
    voz.classList.toggle('on', vozOn);
  }
  function limparMarkdown(t) {
    return String(t || '').replace(/[*_#>`~]/g, '').replace(/\[(.*?)\]\(.*?\)/g, '$1').replace(/\s+/g, ' ').trim();
  }
  function enfileirarVoz(texto, falante) {
    if (!vozOn || Date.now() - carregadaEm < 3000) return;   // não lê o histórico ao abrir a página
    String(texto || '').split(/\n\s*\n/).map(limparMarkdown).filter(Boolean).forEach(par => {
      // pedaços de até ~1500 caracteres, cortados em fim de frase
      while (par.length > 1500) {
        const corte = par.lastIndexOf('. ', 1500);
        const i = corte > 400 ? corte + 1 : 1500;
        filaVoz.push({ texto: par.slice(0, i).trim(), falante }); par = par.slice(i).trim();
      }
      filaVoz.push({ texto: par, falante });
    });
    try { _ttsFetchPcm(filaVoz[0].texto, filaVoz[0].falante).catch(() => {}); } catch (e) {}
    tocarFila();
  }
  async function tocarFila() {
    if (vozTocando) return;
    vozTocando = true;
    const geracao = vozGeracao;
    try {
      while (filaVoz.length && geracao === vozGeracao) {
        const item = filaVoz.shift();
        if (filaVoz[0]) { try { _ttsFetchPcm(filaVoz[0].texto, filaVoz[0].falante).catch(() => {}); } catch (e) {} }
        await falar(item);
      }
    } finally { vozTocando = false; }
  }
  async function falar({ texto, falante }) {
    try {
      if (typeof _ttsServerOk !== 'undefined' && !_ttsServerOk) throw new Error('sem servidor');
      const pcm = await _ttsFetchPcm(texto, falante || '');
      if (!vozOn) return;
      const ctx = _getTtsCtx();
      if (ctx.state !== 'running') await ctx.resume();
      const i16 = new Int16Array(pcm);
      const buf = ctx.createBuffer(1, i16.length, 24000);
      const ch = buf.getChannelData(0);
      for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
      await new Promise(fim => {
        const src = ctx.createBufferSource();
        src.buffer = buf; src.connect(ctx.destination);
        src.onended = () => { if (vozFonte === src) vozFonte = null; fim(); };
        vozFonte = src; src.start(0);
      });
    } catch (e) {
      if (!('speechSynthesis' in window) || !vozOn) return;
      await new Promise(fim => {
        const u = new SpeechSynthesisUtterance(texto);
        u.lang = 'pt-BR'; u.onend = fim; u.onerror = fim;
        speechSynthesis.speak(u);
      });
    }
  }
  function pararVoz() {
    vozGeracao++; filaVoz.length = 0;
    if (vozFonte) { try { vozFonte.stop(); } catch (e) {} vozFonte = null; }
    if ('speechSynthesis' in window) speechSynthesis.cancel();
  }
  function alternarVoz() {
    vozOn = !vozOn;
    try { localStorage.setItem('mu-voz', vozOn ? '1' : '0'); } catch (e) {}
    if (vozOn) {
      try { const ctx = _getTtsCtx(); if (ctx.state !== 'running') ctx.resume(); } catch (e) {}
      try { _ttsAutoNarrate = false; } catch (e) {}   // desliga o auto-narrar antigo pra não falar duas vezes
    } else pararVoz();
    pintarVoz();
  }
  voz.addEventListener('click', alternarVoz);
  document.addEventListener('keydown', ev => {
    if (ev.target.closest('input, textarea, select, [contenteditable]')) return;
    if (ev.key === 'v' || ev.key === 'V') alternarVoz();
  });
  if (vozOn) { try { _ttsAutoNarrate = false; } catch (e) {} }
  pintarVoz();
  // o navegador só libera o áudio depois de um clique: o primeiro clique na página destrava
  document.addEventListener('pointerdown', () => {
    try { const ctx = _getTtsCtx(); if (ctx.state !== 'running') ctx.resume(); } catch (e) {}
  }, { once: true });

  const origTexto = window.handleIncomingText, origNpc = window.renderNPCBlock;
  if (typeof origTexto === 'function') window.handleIncomingText = function (texto) {
    enfileirarVoz(texto, ''); return origTexto.apply(this, arguments);
  };
  if (typeof origNpc === 'function') window.renderNPCBlock = function (nome, texto, replay) {
    if (!replay) enfileirarVoz(texto, nome); return origNpc.apply(this, arguments);
  };

  // ── Trilha sonora: o trilha.sh escreve atual.json e a tela toca em loop ──
  const musica = new Audio();
  musica.loop = true;
  let musVol = 0.35, musPausada = false, musArquivo = null, musTitulo = '';
  try { musVol = +(localStorage.getItem('mu-musica-vol') ?? 0.35); musPausada = localStorage.getItem('mu-musica-pausa') === '1'; } catch (e) {}
  musica.volume = musVol;
  const musBtn = document.createElement('button');
  musBtn.id = 'mu-musica-btn'; musBtn.type = 'button';
  botoes.insertBefore(musBtn, voz);
  const musPainel = document.createElement('div');
  musPainel.id = 'mu-musica-painel';
  musPainel.innerHTML = '<div class="titulo"></div><label>Volume <input type="range" min="0" max="100"></label>';
  document.body.appendChild(musPainel);
  const musSlider = musPainel.querySelector('input');
  musSlider.value = Math.round(musVol * 100);
  musSlider.addEventListener('input', () => {
    musica.volume = musVol = musSlider.value / 100;
    try { localStorage.setItem('mu-musica-vol', musVol); } catch (e) {}
  });
  function pintarMusica() {
    const tocando = musArquivo && !musica.paused;
    musBtn.textContent = !musArquivo ? '🎵 —' : (tocando ? '🎵 Pausar' : '🎵 Tocar');
    musBtn.classList.toggle('on', !!tocando);
    musBtn.title = musTitulo ? musTitulo + ' (M)' : 'Sem trilha (M)';
    musPainel.querySelector('.titulo').textContent = musTitulo || 'Nenhuma trilha';
  }
  function alternarMusica() {
    if (!musArquivo) return;
    if (musica.paused) { musPausada = false; musica.play().catch(() => {}); }
    else { musPausada = true; musica.pause(); }
    try { localStorage.setItem('mu-musica-pausa', musPausada ? '1' : '0'); } catch (e) {}
    pintarMusica();
  }
  musBtn.addEventListener('click', alternarMusica);
  musBtn.addEventListener('contextmenu', ev => { ev.preventDefault(); musPainel.classList.toggle('on'); });
  musBtn.addEventListener('mouseenter', () => musPainel.classList.add('on'));
  musPainel.addEventListener('mouseleave', () => musPainel.classList.remove('on'));
  musica.addEventListener('play', pintarMusica);
  musica.addEventListener('pause', pintarMusica);
  document.addEventListener('keydown', ev => {
    if (ev.target.closest('input, textarea, select, [contenteditable]')) return;
    if (ev.key === 'm' || ev.key === 'M') alternarMusica();
  });
  let musUltimoT = null;
  async function checarTrilha() {
    try {
      const j = await fetch('/icons/trilhas/atual.json?_=' + Date.now(), { cache: 'no-store' }).then(r => r.ok ? r.json() : null);
      if (!j || j.t === musUltimoT) return;
      const primeira = musUltimoT === null;
      musUltimoT = j.t;
      if (!j.arquivo) { musArquivo = null; musTitulo = ''; musica.pause(); musica.removeAttribute('src'); pintarMusica(); return; }
      if (j.arquivo !== musArquivo) {
        musArquivo = j.arquivo; musTitulo = j.titulo || j.arquivo;
        musica.src = '/icons/trilhas/' + encodeURIComponent(j.arquivo);
        // trilha nova do Mestre toca mesmo que a anterior estivesse pausada; ao recarregar a página, respeita a pausa
        if (!primeira) musPausada = false;
        if (j.pausada) musPausada = true;
        if (!musPausada) musica.play().catch(() => {});
      }
      pintarMusica();
    } catch (e) {}
  }
  // o navegador só deixa tocar depois de um clique na página
  document.addEventListener('pointerdown', () => { if (musArquivo && !musPausada && musica.paused) musica.play().catch(() => {}); });
  checarTrilha();
  setInterval(checarTrilha, 3000);
  pintarMusica();

  juntarBotoes();
  setTimeout(juntarBotoes, 1500);
  document.addEventListener('keydown', ev => {
    if (ev.target.closest('input, textarea, select, [contenteditable]')) return;
    if (ev.key === 'c' || ev.key === 'C') document.body.classList.toggle('mu-config');
    if (ev.key === 'Escape') document.body.classList.remove('mu-config');
  });

  // retrato ampliado ao clicar
  const lupa = document.createElement('div');
  lupa.id = 'mu-lupa';
  document.body.appendChild(lupa);
  lupa.addEventListener('click', () => lupa.classList.remove('on'));
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') lupa.classList.remove('on'); });
  function ampliar(nome) {
    if (!retratos[nome]) return;
    tip.classList.remove('on');
    lupa.innerHTML = `<div class="mu-lupa-moldura"><img src="${esc(retratos[nome])}" alt=""><div class="mu-lupa-nome">${esc(nome)}</div></div>`;
    lupa.classList.add('on');
  }

  // ── Itens ───────────────────────────────────────────────────────
  const MOEDAS = /(\d+)\s*po\b|(\d+)\s*pp\b|(\d+)\s*pc\b/gi;

  function descreverItem(texto) {
    const t = semAcento(texto);
    const base = catalogo.itens.find(i => t.includes(semAcento(i.chave)));
    const qtd = (texto.match(/\((\d+)\)|^(\d+)\s+/) || []).slice(1).find(Boolean);
    const d = Object.assign({ nome: texto, icone: '📦', w: 1, h: 1, raridade: 'comum' }, base || {});
    if (!base) d.desc = texto;
    if (qtd) d.qtd = +qtd;
    d.original = texto;
    return d;
  }

  function icone(d) {
    return d.img ? `<img class="ico" src="${esc(d.img)}" alt="">` : `<span class="ico">${esc(d.icone || '❔')}</span>`;
  }

  // ── Janela do personagem ────────────────────────────────────────
  const janela = document.createElement('div');
  janela.id = 'mu-personagem';
  const direita = document.createElement('div');
  direita.id = 'mu-direita';
  document.body.appendChild(direita);

  // ── Retratos da party (esquerda, estilo BG3) ────────────────────
  const party = document.createElement('div');
  party.id = 'mu-party';
  document.body.appendChild(party);
  let hpParty = {};

  function renderParty(membros) {
    let turno = null;
    try { turno = _currentTurnOrder; } catch (e) {}
    const atual = turno && turno.current;
    party.innerHTML = (turno && turno.order && turno.order.length ? `<div class="mu-rodada">Rodada <b>${turno.round ?? 1}</b></div>` : '') +
      membros.map((m, i) => {
        const hp = m.hp || {};
        const temHp = hp.max != null;
        const pct = temHp && hp.max ? Math.max(0, Math.min(100, 100 * hp.current / hp.max)) : 100;
        const cls = ['mu-membro'];
        if (i === 0) cls.push('pj');
        if (atual && atual === m.name) cls.push('vez');
        if (temHp && hp.current <= 0) cls.push('caido');
        else if (temHp && pct <= 40) cls.push('ferido');
        const ret = retratos[m.name] ? `style="background-image:url('${retratos[m.name]}')"` : '';
        const ini = (m.name || '?').replace(/^(Irmã|Irmão)\s+/, '')[0];
        const curto = (m.name || '').replace(/^(Irmã|Irmão)\s+/, '').split(' ')[0];
        const mudou = hpParty[m.name] !== undefined && temHp && hpParty[m.name] !== hp.current
          ? (hp.current < hpParty[m.name] ? ' dano' : ' cura') : '';
        if (temHp) hpParty[m.name] = hp.current;
        return `<div class="${cls.join(' ')}${mudou}" data-i="${i}">
          <div class="mu-foto" ${ret}>${ret ? '' : `<span>${esc(ini)}</span>`}</div>
          ${m.ac != null ? `<div class="mu-ca">${m.ac}</div>` : ''}
          ${m.concentration ? '<div class="mu-conc" title="Concentração">◈</div>' : ''}
          ${(m.conditions || []).length ? '<div class="mu-cond">!</div>' : ''}
          <div class="mu-nm">${esc(curto)}</div>
          <div class="mu-hp"><i style="width:${pct}%"></i>${temHp ? `<span>${hp.current}/${hp.max}</span>` : ''}</div>
        </div>`;
      }).join('');
    requestAnimationFrame(() => {
      const sc = document.getElementById('speaker-card');
      if (sc) sc.style.top = (party.getBoundingClientRect().bottom + 14) + 'px';
    });
    party.querySelectorAll('.mu-membro').forEach(el => el.addEventListener('click', () => ampliar(membros[+el.dataset.i].name)));
    party.querySelectorAll('.mu-membro').forEach(el => comTip(el, () => {
      const m = membros[+el.dataset.i], hp = m.hp || {};
      const linhas = [];
      if (hp.max != null) linhas.push(`Vida ${hp.current}/${hp.max}${hp.temp ? ` (+${hp.temp} temp.)` : ''}`);
      if (m.ac != null) linhas.push(`CA ${m.ac}`);
      if (m.class) linhas.push(m.class.replace(/\s*\(.*\)/, '') + (m.level ? ` ${m.level}` : ''));
      return { nome: m.name, raridade: el.classList.contains('pj') ? 'antigo' : 'excelente', tipo: m.race || (el.classList.contains('pj') ? '' : 'Companheiro'),
        linhas, opcoes: [m.concentration && `Concentração: ${m.concentration}`, ...(m.conditions || [])].filter(Boolean), desc: m.nota };
    }));
  }

  const SLOTS = [
    { id: 'asas',       rotulo: 'Asas',      x: 8,   y: 0,   w: 64, h: 30 },
    { id: 'elmo',       rotulo: 'Elmo',      x: 117, y: 0,   w: 44, h: 40 },
    { id: 'amuleto',    rotulo: 'Amul.',     x: 172, y: 8,   w: 30, h: 30 },
    { id: 'arma',       rotulo: 'Arma',      x: 8,   y: 38,  w: 64, h: 98 },
    { id: 'armadura',   rotulo: 'Armadura',  x: 107, y: 48,  w: 64, h: 82 },
    { id: 'secundaria', rotulo: 'Mão sec.',  x: 206, y: 38,  w: 64, h: 98 },
    { id: 'luvas',      rotulo: 'Luvas',     x: 8,   y: 142, w: 44, h: 34 },
    { id: 'anel',       rotulo: 'Anel',      x: 76,  y: 146, w: 28, h: 28 },
    { id: 'calcas',     rotulo: 'Calças',    x: 117, y: 138, w: 44, h: 38 },
    { id: 'anel2',      rotulo: 'Anel',      x: 174, y: 146, w: 28, h: 28 },
    { id: 'botas',      rotulo: 'Botas',     x: 226, y: 142, w: 44, h: 34 },
  ];
  const ATRIBS = [['str', 'Força'], ['dex', 'Destreza'], ['con', 'Constituição'],
                  ['int', 'Inteligência'], ['wis', 'Sabedoria'], ['cha', 'Carisma']];

  function empacotar(itens, cols) {
    const ocup = [];
    const livre = (r, c, w, h) => {
      if (c + w > cols) return false;
      for (let i = r; i < r + h; i++) for (let j = c; j < c + w; j++) if (ocup[i] && ocup[i][j]) return false;
      return true;
    };
    // os grandes primeiro, como quem arruma mochila de MMO
    const ordem = itens.slice().sort((a, b) => b.w * b.h - a.w * a.h);
    ordem.forEach(it => {
      for (let r = 0; ; r++) {
        let ok = false;
        for (let c = 0; c < cols; c++) {
          if (livre(r, c, it.w, it.h)) {
            for (let i = r; i < r + it.h; i++) { ocup[i] = ocup[i] || []; for (let j = c; j < c + it.w; j++) ocup[i][j] = 1; }
            it.r = r; it.c = c; ok = true; break;
          }
        }
        if (ok) break;
      }
    });
    return Math.max(5, ocup.length);
  }

  function renderJanela(p, companheiros) {
    const sheet = p.sheet || {};
    const inv = (sheet.inventory || []).map(x => typeof x === 'string' ? x : (x.name || ''));
    let moedas = null;
    const itens = [];
    inv.forEach(txt => {
      if (/\d+\s*p[ocp]\b/i.test(txt) && txt.replace(MOEDAS, '').replace(/[\s,·e]/g, '') === '') { moedas = txt; return; }
      itens.push(descreverItem(txt));
    });
    const equipados = {};
    const mochila = [];
    itens.forEach(it => { if (it.slot && !equipados[it.slot]) equipados[it.slot] = it; else mochila.push(it); });
    const linhas = empacotar(mochila, 8);

    const nivel = p.level || 1;
    const retrato = retratos[p.name] ? `style="background-image:url('${retratos[p.name]}')"` : '';
    const ab = p.ability_scores || {};
    let h = `<div class="mu-janela">
      <div class="mu-titulo">Personagem</div>
      <div class="mu-cab">
        <div class="mu-retrato" ${retrato}></div>
        <div>
          <div class="mu-nome">${esc(p.name)}</div>
          <div class="mu-classe">${esc((p.class || '').replace(/\s*\(.*\)/, ''))}</div>
          <div class="mu-nivel">Nível <b>${nivel}</b> · ${esc(p.race || '')}</div>
        </div>
      </div>
      <div class="mu-atribs">${ATRIBS.map(([k, n]) => ab[k]
        ? `<div class="mu-atrib"><span>${n}</span><b>${ab[k].score}<i>${esc(ab[k].mod)}</i></b></div>` : '').join('')}
      </div>
      <div class="mu-equip"><div class="mu-silhueta">🧍</div>
        ${SLOTS.map(s => {
          const it = equipados[s.id];
          return `<div class="mu-slot ${it ? 'cheio r-' + it.raridade : 'vazio'}" data-slot="${s.id}" data-rotulo="${s.rotulo}"
            style="left:${s.x}px;top:${s.y}px;width:${s.w}px;height:${s.h}px">${it ? icone(it) : ''}</div>`;
        }).join('')}
      </div>
    </div>
    <div class="mu-janela">
      <div class="mu-titulo">Inventário</div>
      <div class="mu-grade" style="grid-template-rows:repeat(${linhas}, var(--cel))">
        ${mochila.map((it, i) => `<div class="mu-item r-${it.raridade}" data-i="${i}" data-w="${it.w}" data-h="${it.h}"
          style="grid-column:${it.c + 1} / span ${it.w};grid-row:${it.r + 1} / span ${it.h}">${icone(it)}${it.qtd ? `<span class="qtd">${it.qtd}</span>` : ''}</div>`).join('')}
      </div>
      <div class="mu-zen"><span>Moedas</span><b>${esc(moedas || '0 po')}</b></div>
    </div>`;
    janela.innerHTML = h;

    janela.querySelectorAll('.mu-item').forEach(el => comTip(el, () => mochila[+el.dataset.i]));
    janela.querySelectorAll('.mu-slot.cheio').forEach(el => comTip(el, () => equipados[el.dataset.slot]));
    janela.querySelectorAll('.mu-slot.vazio').forEach(el => comTip(el, () => ({ nome: el.dataset.rotulo, tipo: 'Vazio', raridade: 'comum' })));
    janela.querySelectorAll('.mu-atrib').forEach((el, i) => {
      const [k, n] = ATRIBS[i];
      comTip(el, () => ({ nome: n, raridade: 'antigo', linhas: [`Valor ${ab[k].score} · modificador ${ab[k].mod}`],
        opcoes: ['Orientação: +1d4 nos testes fora de combate'] }));
    });

    const rj = janela.querySelector('.mu-retrato');
    if (rj) rj.addEventListener('click', () => ampliar(p.name));
    if (janela.parentNode !== direita) direita.appendChild(janela);

  }

  // ── Barra de skills ─────────────────────────────────────────────
  const barra = document.createElement('div');
  barra.id = 'mu-barra';
  document.body.appendChild(barra);
  let skillsAtuais = [];
  let ultimo = {};

  function montarSkills(p) {
    const sheet = p.sheet || {};
    const lista = [];
    (sheet.attacks || []).forEach(a => {
      const it = descreverItem(a.name);
      lista.push({ nome: a.name, img: it.img, icone: it.icone, raridade: 'excelente', tipo: 'Ataque',
        linhas: [`Ataque ${a.bonus} · dano ${a.damage} ${(a.type || '').toLowerCase()}`], desc: a.notes });
    });
    const sp = sheet.spells || {};
    const magia = (n, nivelPadrao) => {
      const m = catalogo.magias[semAcento(n)] || {};
      const nv = m.nivel ?? nivelPadrao;
      return { nome: m.nome || n, original: n, img: m.img, icone: m.icone || '🔮', nivel: nv, ritual: m.ritual,
        raridade: 'magia', tipo: nv === 0 ? 'Truque' : `Magia de ${nv}º círculo${m.ritual ? ' · ritual' : ''}`,
        linhas: m.linhas || [], desc: nv === 0 ? '' : `CD ${sp.save_dc ?? '—'} · ataque ${sp.attack_bonus ?? '—'}` };
    };
    (sp.cantrips || []).forEach(n => lista.push(magia(n, 0)));
    lista.push({ sep: true });
    (sp.prepared || []).forEach(n => lista.push(magia(n, 1)));
    return lista;
  }

  function slotsRestantes(p) {
    const s = p.spell_slots || (p.sheet && p.sheet.spells && p.sheet.spells.slots) || {};
    let rest = 0, max = 0;
    Object.values(s).forEach(v => { max += v.max || 0; rest += (v.max || 0) - (v.used || 0); });
    return { rest, max };
  }

  function renderBarra(p) {
    const hp = p.hp || { current: 0, max: 1 };
    const pctHp = hp.max ? Math.max(0, Math.min(100, 100 * hp.current / hp.max)) : 0;
    const { rest, max } = slotsRestantes(p);
    const pctMana = max ? 100 * rest / max : 0;
    const xp = p.xp || {};
    const pctXp = xp.next ? Math.min(100, 100 * (xp.current || 0) / xp.next) : 0;
    const hd = p.hit_dice || {};
    skillsAtuais = montarSkills(p);
    const pocao = ((p.sheet || {}).inventory || []).map(x => typeof x === 'string' ? x : x.name).find(t => /po[cç][aã]o/i.test(t));
    const fogo = ((p.sheet || {}).inventory || []).map(x => typeof x === 'string' ? x : x.name).find(t => /fogo alqu/i.test(semAcento(t)));

    const buffs = [];
    if (p.concentration) buffs.push(`<div class="mu-buff">◈ ${esc(p.concentration)}</div>`);
    (p.conditions || []).forEach(c => buffs.push(`<div class="mu-buff ruim">${esc(c)}</div>`));
    (p.effects || []).forEach(e => buffs.push(`<div class="mu-buff">${esc(e.name || e)}</div>`));
    ((p.sheet || {}).features || []).forEach(f => { if (/\(ativo\)/i.test(f.name)) buffs.push(`<div class="mu-buff">${esc(f.name.replace(/\s*\(ativo\)/i, ''))}</div>`); });

    let tecla = 0;
    const skillsHtml = skillsAtuais.map((s, i) => {
      if (s.sep) return '<div class="mu-sep"></div>';
      tecla++;
      const semMana = s.nivel > 0 && rest <= 0;
      const ativa = p.concentration && semAcento(p.concentration) === semAcento(s.original || s.nome);
      return `<div class="mu-skill${semMana ? ' sem-mana' : ''}${s.ritual ? ' ritual' : ''}${ativa ? ' ativa' : ''}" data-i="${i}" data-tecla="${tecla}">
        <span class="tecla">${tecla}</span>${icone(s)}${s.nivel ? `<span class="nv">${s.ritual ? 'R' : s.nivel}</span>` : ''}</div>`;
    }).join('');
    const rapidos = [pocao && { k: 'Q', t: pocao }, fogo && { k: 'W', t: fogo }].filter(Boolean);
    const rapidosHtml = rapidos.length ? '<div class="mu-sep"></div>' + rapidos.map(r => {
      const d = descreverItem(r.t);
      return `<div class="mu-skill mu-rapido" data-t="${esc(r.t)}"><span class="tecla">${r.k}</span>${icone(d)}</div>`;
    }).join('') : '';

    barra.innerHTML = `
      <div class="mu-orbe-wrap${pctHp <= 34 ? ' baixa' : ''}" id="mu-orbe-vida">
        <div class="mu-orbe vida${hp.temp ? ' temp' : ''}"><div class="liquido" style="height:${pctHp}%"></div><div class="brilho"></div></div>
        <div class="mu-orbe-aro"></div>
        <div class="mu-orbe-num">${hp.current}${hp.temp ? `<span style="color:#ffe08a">+${hp.temp}</span>` : ''} / ${hp.max}<small>VIDA</small></div>
      </div>
      <div class="mu-painel">
        <div class="mu-buffs">${buffs.join('')}</div>
        <div class="mu-info">
          <div class="mu-chip" data-tip="ca">CA <b>${p.ac ?? '—'}</b></div>
          <div class="mu-chip" data-tip="desl">Desloc. <b>${p.speed ?? '—'} ft</b></div>
          <div class="mu-chip" data-tip="ini">Inic. <b>${esc(p.initiative ?? '—')}</b></div>
          <div class="mu-chip" data-tip="dv">DV <b>${hd.remaining ?? '—'}/${hd.max ?? '—'}${hd.die ? ' ' + esc(hd.die) : ''}</b></div>
          <div class="mu-chip insp${p.inspiration ? '' : ' off'}" data-tip="insp">Inspiração <b>✦</b></div>
        </div>
        <div class="mu-skills">${skillsHtml}${rapidosHtml}</div>
        <div class="mu-xp">
          <div class="mu-xp-barra"><i style="width:${pctXp}%"></i></div>
          <div class="mu-xp-txt">Nível <b>${p.level || 1}</b> · XP ${xp.current ?? 0} / ${xp.next ?? '—'}</div>
        </div>
      </div>
      <div class="mu-orbe-wrap" id="mu-orbe-mana">
        <div class="mu-orbe mana"><div class="liquido" style="height:${pctMana}%"></div><div class="brilho"></div></div>
        <div class="mu-orbe-aro"></div>
        <div class="mu-orbe-num">${rest} / ${max}<small>ESPAÇOS</small></div>
      </div>`;

    // pisca a orbe quando o valor muda
    if (ultimo.hp !== undefined && ultimo.hp !== hp.current) barra.querySelector('#mu-orbe-vida').classList.add('pulso');
    if (ultimo.mana !== undefined && ultimo.mana !== rest) barra.querySelector('#mu-orbe-mana').classList.add('pulso');
    ultimo = { hp: hp.current, mana: rest };

    barra.querySelectorAll('.mu-skill:not(.mu-rapido)').forEach(el => {
      comTip(el, () => {
        const s = skillsAtuais[+el.dataset.i];
        return el.classList.contains('sem-mana') ? Object.assign({ aviso: 'Sem espaços de magia' }, s)
          : (s.ritual && rest <= 0 ? Object.assign({ aviso: 'Só como ritual (+10 min)' }, s) : s);
      });
      el.addEventListener('click', () => { el.classList.remove('clique'); void el.offsetWidth; el.classList.add('clique'); });
    });
    barra.querySelectorAll('.mu-rapido').forEach(el => comTip(el, () => descreverItem(el.dataset.t)));
    const tips = {
      ca: { nome: 'Classe de Armadura', raridade: 'antigo', linhas: [`CA ${p.ac}`, 'Couro batido + Des'] },
      desl: { nome: 'Deslocamento', raridade: 'antigo', linhas: [`${p.speed} ft por turno`] },
      ini: { nome: 'Iniciativa', raridade: 'antigo', linhas: [`${p.initiative} no d20`] },
      dv: { nome: 'Dados de Vida', raridade: 'antigo', linhas: [`${hd.remaining}/${hd.max} ${hd.die || ''}`, 'Gaste num descanso curto'] },
      insp: { nome: 'Inspiração', raridade: 'missao', linhas: [p.inspiration ? 'Disponível' : 'Gasta'], desc: 'Vantagem numa rolagem.' },
    };
    barra.querySelectorAll('.mu-chip').forEach(el => comTip(el, () => tips[el.dataset.tip]));
  }

  // atalhos 1–9 / Q W só dão o efeito visual (a jogada continua no terminal)
  document.addEventListener('keydown', ev => {
    if (ev.target.closest('input, textarea, select, [contenteditable]')) return;
    if (ev.key === 'F8') { ev.preventDefault(); aplicarLigada(!document.body.classList.contains('mu')); return; }
    let el = null;
    if (/^[1-9]$/.test(ev.key)) el = barra.querySelector(`.mu-skill[data-tecla="${ev.key}"]`);
    else if (/^[qw]$/i.test(ev.key)) el = [...barra.querySelectorAll('.mu-rapido')].find(x => x.querySelector('.tecla').textContent === ev.key.toUpperCase());
    if (el) { el.classList.remove('clique'); void el.offsetWidth; el.classList.add('clique'); }
  });

  // ── Liga nos dados do painel original ───────────────────────────
  function render() {
    let dados;
    try { dados = _playerData; } catch (e) { return; }
    const nomes = Object.keys(dados || {});
    if (!nomes.length) return;
    const pj = nomes.map(n => dados[n]).find(p => p.sheet || p.ability_scores) || dados[nomes[0]];
    const resto = nomes.filter(n => n !== pj.name).map(n => dados[n]);
    renderJanela(pj, resto);
    renderParty([pj, ...resto]);
    renderBarra(pj);
  }

  const original = window.updateStats;
  if (typeof original === 'function') {
    window.updateStats = function (stats) {
      original.apply(this, arguments);
      try { render(); } catch (e) { console.error('[mu-skin]', e); }
    };
  }

  Promise.all([
    fetch('/icons/mu-itens.json?v=' + Date.now()).then(r => r.json()).then(j => { catalogo = j; }).catch(() => {}),
    fetch('/portraits').then(r => r.json()).then(j => { retratos = j; }).catch(() => {}),
  ]).then(() => { aplicarLigada(ligada()); render(); });
})();
