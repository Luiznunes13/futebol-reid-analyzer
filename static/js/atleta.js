// atleta.js — Análise de atleta específico (one-shot heatmap)

// ─── Navegação entre tabs ─────────────────────────────────────────
function mudarTab(btn) {
  document.querySelectorAll('.cv-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.cv-tab-content').forEach(p => p.classList.add('hidden'));
  btn.classList.add('active');
  document.getElementById(btn.dataset.tab).classList.remove('hidden');
}

let fotosFiles   = [];
let pollingTimer = null;
let ytUrlAtleta  = null;   // URL do YouTube selecionada
let _nomeInputTimer = null;

// ─── Utils ────────────────────────────────────────────────────────
function toast(msg, tipo = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className   = 'toast' + (tipo ? ' ' + tipo : '');
  t.classList.remove('hidden');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 4500);
}

// ─── Init ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setupUpload();
  setupBotoes();
  setupThreshold();
  carregarAtletas();

  // Recuperar análise concluída se Flask ainda tem o estado em memória
  fetch('/api/atleta/status')
    .then(r => r.json())
    .then(data => {
      if (data.status === 'concluido' && data.heatmap) {
        document.getElementById('resultado-idle').classList.add('hidden');
        document.getElementById('heatmap-section').classList.remove('hidden');
        mostrarResultado(data);
        // Navegar para tab resultado
        const btnRes = document.getElementById('tab-btn-resultado');
        if (btnRes) mudarTab(btnRes);
      } else if (data.status === 'rodando') {
        // Análise em andamento — retomar polling
        document.getElementById('resultado-idle').classList.add('hidden');
        document.getElementById('progresso-section').classList.remove('hidden');
        iniciarPolling();
        // Navegar para tab resultado
        const btnRes = document.getElementById('tab-btn-resultado');
        if (btnRes) mudarTab(btnRes);
      }
    })
    .catch(() => {});

  // Recuperar captura automática em andamento ou aguardando revisão
  fetch('/api/atleta/capturar_refs/status')
    .then(r => r.json())
    .then(data => {
      if (!data.status) return;
      const prog = document.getElementById('captura-refs-progress');
      prog.style.display = 'block';
      const bar   = document.getElementById('captura-refs-bar');
      const label = document.getElementById('captura-refs-label');
      const count = document.getElementById('captura-refs-count');
      bar.style.width = (data.progresso || 0) + '%';
      count.textContent = `${data.salvos || (data.candidatos || []).length || 0} salvos`;
      if (data.status === 'aguardando_revisao') {
        bar.style.background = '#f59e0b';
        label.textContent = `✅ Captura concluída — revise as ${(data.candidatos || []).length} fotos abaixo`;
        _mostrarRevisao(data);
        // Esconder idle, mostrar revisão
        const idle = document.getElementById('fotos-idle');
        if (idle) idle.classList.add('hidden');
        document.getElementById('btn-capturar-refs').disabled = false;
      } else if (data.status === 'rodando' || data.status === 'iniciando') {
        label.textContent = 'Retomando captura…';
        document.getElementById('btn-capturar-refs').disabled = true;
        document.getElementById('btn-capturar-refs').textContent = 'Iniciando…';
        if (_capturaRefsTimer) clearInterval(_capturaRefsTimer);
        _capturaRefsTimer = setInterval(_pollCaptura, 1500);
      }
    })
    .catch(() => {});
});

// ─── Upload de fotos ─────────────────────────────────────────────
function setupUpload() {
  const zone  = document.getElementById('upload-zone');
  const input = document.getElementById('fotos-input');

  input.addEventListener('change', () => {
    fotosFiles = Array.from(input.files);
    renderPreview();
    validarBotaoEmbed();
  });

  zone.addEventListener('dragover',   e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave',  () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    fotosFiles = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    renderPreview();
    validarBotaoEmbed();
  });
}

function renderPreview() {
  const el = document.getElementById('fotos-preview');
  el.innerHTML = '';
  fotosFiles.slice(0, 20).forEach(f => {
    const img = document.createElement('img');
    img.src = URL.createObjectURL(f);
    el.appendChild(img);
  });
  el.classList.toggle('hidden', fotosFiles.length === 0);
}

function validarBotaoEmbed() {
  const nome = document.getElementById('nome-atleta').value.trim();
  const temFotosLocal    = fotosFiles.length >= 1;
  const temFotosServidor = _fotosSalvasTotal > 0;
  const btn = document.getElementById('btn-gerar-embedding');
  btn.disabled = !nome;
  if (nome && !temFotosLocal && !temFotosServidor) {
    btn.textContent = 'Gerar Embedding';
    btn.title = 'Nenhuma foto ainda. Envie fotos ou use o extrator.';
  } else if (nome && !temFotosLocal && temFotosServidor) {
    btn.textContent = `Gerar Embedding (${_fotosSalvasTotal} fotos salvas)`;
    btn.title = `Usar as ${_fotosSalvasTotal} fotos já salvas em atleta_refs/${nome}`;
  } else if (nome && temFotosLocal) {
    btn.textContent = `Gerar Embedding (${fotosFiles.length} foto${fotosFiles.length > 1 ? 's' : ''})`;
    btn.title = '';
  } else {
    btn.textContent = 'Gerar Embedding';
    btn.title = '';
  }
}

// ─── Threshold slider ─────────────────────────────────────────────
function setupThreshold() {
  const range = document.getElementById('threshold-range');
  range.addEventListener('input', () => {
    document.getElementById('threshold-val').textContent = range.value;
  });
}

// ─── Botões ───────────────────────────────────────────────────────
function setupBotoes() {
  document.getElementById('nome-atleta').addEventListener('input', () => {
    validarBotaoEmbed();
    const nome = document.getElementById('nome-atleta').value.trim();
    if (!nome) { _atualizarBotaoFotosSalvas('', 0); return; }
    // Busca contagem real no servidor (debounced)
    clearTimeout(_nomeInputTimer);
    _nomeInputTimer = setTimeout(async () => {
      try {
        const r = await fetch(`/api/atleta/refs/${encodeURIComponent(nome)}?page=1&per=1`);
        const d = await r.json();
        _atualizarBotaoFotosSalvas(nome, d.total || 0);
      } catch { _atualizarBotaoFotosSalvas(nome, -1); }
    }, 400);
  });
  document.getElementById('btn-gerar-embedding').addEventListener('click', gerarEmbedding);
  document.getElementById('btn-analisar').addEventListener('click', iniciarAnalise);
  document.getElementById('btn-nova-analise').addEventListener('click', resetUI);
  document.getElementById('btn-buscar-yt').addEventListener('click', buscarYtAtleta);
  document.getElementById('btn-usar-stream').addEventListener('click', usarStreamAtleta);
  document.getElementById('yt-url-atleta').addEventListener('keydown', e => {
    if (e.key === 'Enter') buscarYtAtleta();
  });
}

// ─── YouTube ───────────────────────────────────────────────────
function _ytShow(id, visible) {
  document.getElementById(id).classList.toggle('hidden', !visible);
}

async function buscarYtAtleta() {
  const url = document.getElementById('yt-url-atleta').value.trim();
  if (!url) return;

  const btn = document.getElementById('btn-buscar-yt');
  btn.disabled = true;
  btn.textContent = '...';
  _ytShow('yt-info-atleta', false);
  _ytShow('yt-erro-atleta', false);
  _ytShow('yt-selecionado', false);
  ytUrlAtleta = null;

  try {
    const res  = await fetch('/api/videos/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erro ao buscar');

    document.getElementById('yt-thumb').src          = data.thumbnail || '';
    document.getElementById('yt-titulo').textContent = data.titulo    || url;
    document.getElementById('yt-duracao').textContent = data.duracao  || '';
    _ytShow('yt-info-atleta', true);
  } catch (e) {
    document.getElementById('yt-erro-atleta').textContent = '❌ ' + e.message;
    _ytShow('yt-erro-atleta', true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Buscar';
  }
}

function usarStreamAtleta() {
  const url    = document.getElementById('yt-url-atleta').value.trim();
  const titulo = document.getElementById('yt-titulo').textContent;
  ytUrlAtleta  = url;

  // Adicionar/atualizar option __stream__ no select
  const sel = document.getElementById('video-select');
  let opt = sel.querySelector('option[value="__stream__"]');
  if (!opt) { opt = document.createElement('option'); opt.value = '__stream__'; sel.appendChild(opt); }
  opt.textContent = '▶ ' + titulo;
  sel.value = '__stream__';

  _ytShow('yt-info-atleta', false);
  const selDiv = document.getElementById('yt-selecionado');
  selDiv.textContent = '✔ YouTube selecionado: ' + titulo;
  _ytShow('yt-selecionado', true);
  toast('Stream do YouTube selecionado', 'success');
}

// ─── Gerar embedding ─────────────────────────────────────────────
async function gerarEmbedding() {
  const nome   = document.getElementById('nome-atleta').value.trim();
  const btn    = document.getElementById('btn-gerar-embedding');
  const status = document.getElementById('status-embedding');

  if (!nome)                { toast('Nome do atleta obrigatório', 'error'); return; }
  // fotosFiles pode ser vazio se o usuário usou o extrator (crops salvos no servidor)

  btn.disabled    = true;
  btn.textContent = 'Processando fotos…';

  const fd = new FormData();
  fd.append('nome', nome);
  fotosFiles.forEach(f => fd.append('fotos', f));

  try {
    const res  = await fetch('/api/atleta/fotos', { method: 'POST', body: fd });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erro desconhecido');

    status.textContent = `✓ Embedding gerado com ${data.n_fotos} foto(s). Atleta "${data.nome}" pronto.`;
    status.className   = 'status-msg ok';
    status.classList.remove('hidden');
    toast(`Embedding de ${data.nome} salvo!`, 'success');
    await carregarAtletas();

  } catch (e) {
    status.textContent = '✗ ' + e.message;
    status.className   = 'status-msg erro';
    status.classList.remove('hidden');
    toast('Erro: ' + e.message, 'error');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Gerar Embedding de Referência';
  }
}

// ─── Listar atletas salvos ────────────────────────────────────────
async function carregarAtletas() {
  try {
    const res  = await fetch('/api/atleta/atletas');
    const data = await res.json();
    if (!data.success) return;

    const lista  = document.getElementById('atletas-lista');
    const salvos = document.getElementById('atletas-salvos');
    const select = document.getElementById('atleta-select');

    lista.innerHTML  = '';
    select.innerHTML = '<option value="">— selecione um atleta —</option>';

    if (data.atletas.length > 0) {
      salvos.classList.remove('hidden');
      data.atletas.forEach(a => {
        // Chip clicável
        const chip = document.createElement('span');
        chip.className    = 'atleta-chip';
        chip.textContent  = `${a.nome} (${a.n_fotos} fotos)`;
        chip.dataset.nome = a.nome;
        chip.addEventListener('click', () => {
          document.querySelectorAll('.atleta-chip').forEach(c => c.classList.remove('selecionado'));
          chip.classList.add('selecionado');
          select.value = a.nome;
          _atualizarBotaoFotosSalvas(a.nome, a.n_fotos);
        });
        lista.appendChild(chip);

        // Option no select
        const opt = document.createElement('option');
        opt.value       = a.nome;
        opt.textContent = `${a.nome} (${a.n_fotos} fotos)`;
        select.appendChild(opt);
      });
    } else {
      salvos.classList.add('hidden');
    }
  } catch { /* silencioso */ }
}

// ─── Iniciar análise ─────────────────────────────────────────────
async function iniciarAnalise() {
  const nome      = document.getElementById('atleta-select').value;
  const videoSel  = document.getElementById('video-select').value;
  const threshold = parseFloat(document.getElementById('threshold-range').value);
  const btn       = document.getElementById('btn-analisar');

  if (!nome) { toast('Selecione um atleta', 'error'); return; }

  // Resolver fonte do vídeo: stream YT ou arquivo local
  const isStream = videoSel === '__stream__';
  if (!videoSel && !ytUrlAtleta) { toast('Selecione um vídeo ou cole um link do YouTube', 'error'); return; }
  if (isStream && !ytUrlAtleta)  { toast('Link do YouTube não definido', 'error'); return; }
  const video = isStream ? ytUrlAtleta : videoSel;

  btn.disabled    = true;
  btn.textContent = 'Aguarde…';

  document.getElementById('resultado-idle').classList.add('hidden');
  document.getElementById('heatmap-section').classList.add('hidden');
  document.getElementById('progresso-section').classList.remove('hidden');
  setProgresso(0, isStream ? 'Baixando vídeo do YouTube…' : 'Iniciando análise…', 0, 0);
  // Navegar para tab resultado imediatamente
  const btnRes = document.getElementById('tab-btn-resultado');
  if (btnRes) mudarTab(btnRes);

  try {
    const res  = await fetch('/api/atleta/analisar', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ nome, video, threshold }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erro ao iniciar');
    toast(`Análise de ${nome} iniciada`, 'success');
    iniciarPolling();
    // Navegar para tab resultado
    const btnRes = document.getElementById('tab-btn-resultado');
    if (btnRes) mudarTab(btnRes);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
    resetUI();
    btn.disabled    = false;
    btn.textContent = 'Iniciar Análise';
  }
}

// ─── Polling ─────────────────────────────────────────────────────
function iniciarPolling() {
  clearInterval(pollingTimer);
  pollingTimer = setInterval(async () => {
    try {
      const res  = await fetch('/api/atleta/status');
      const data = await res.json();

      const texto = data.status === 'rodando'
        ? `Analisando frame ${(data.frame || 0).toLocaleString()} de ${(data.total_frames || 0).toLocaleString()}…`
        : data.status;

      setProgresso(data.progresso || 0, texto, data.frame || 0, data.matches || 0);

      if (data.status === 'concluido') {
        clearInterval(pollingTimer);
        mostrarResultado(data);
        const btn = document.getElementById('btn-analisar');
        btn.disabled    = false;
        btn.textContent = 'Iniciar Análise';

      } else if (data.status === 'erro') {
        clearInterval(pollingTimer);
        toast('Erro na análise: ' + (data.erro || 'desconhecido'), 'error');
        resetUI();
        const btn = document.getElementById('btn-analisar');
        btn.disabled    = false;
        btn.textContent = 'Iniciar Análise';
      }
    } catch { /* retry */ }
  }, 1000);
}

let _previewTimer = null;

function setProgresso(pct, texto, frame, matches) {
  document.getElementById('progresso-fill').style.width  = pct + '%';
  document.getElementById('progresso-pct').textContent   = pct + '%';
  document.getElementById('progresso-texto').textContent = texto;
  document.getElementById('stat-frame').textContent      = (frame || 0).toLocaleString();
  document.getElementById('stat-matches').textContent    = (matches || 0).toLocaleString();

  // Atualizar preview ao vivo
  const img = document.getElementById('preview-frame');
  if (img && pct > 0 && pct < 100) {
    if (!_previewTimer) {
      _previewTimer = setInterval(() => {
        img.src = `/api/atleta/preview?t=${Date.now()}`;
        img.style.display = 'block';
      }, 800);
    }
  } else if (pct >= 100 || pct === 0) {
    clearInterval(_previewTimer);
    _previewTimer = null;
    if (img) img.style.display = 'none';
  }
}

// ─── Mostrar resultado ────────────────────────────────────────────
function mostrarResultado(data) {
  document.getElementById('progresso-section').classList.add('hidden');
  document.getElementById('resultado-idle').classList.add('hidden');
  document.getElementById('heatmap-section').classList.remove('hidden');

  const taxa = data.deteccoes
    ? Math.round((data.matches / data.deteccoes) * 100) + '%'
    : '-';

  document.getElementById('res-matches').textContent = (data.matches || 0).toLocaleString();
  document.getElementById('res-frames').textContent  = (data.total_frames || 0).toLocaleString();
  document.getElementById('res-taxa').textContent    = taxa;

  // ── Atualizar sidebar stats ──
  const sbStats = document.getElementById('sb-stats');
  if (sbStats) {
    const sbMatches = document.getElementById('sb-res-matches');
    const sbTaxa    = document.getElementById('sb-res-taxa');
    const sbFrames  = document.getElementById('sb-res-frames');
    if (sbMatches) sbMatches.textContent = (data.matches || 0).toLocaleString();
    if (sbTaxa)    sbTaxa.textContent    = taxa;
    if (sbFrames)  sbFrames.textContent  = (data.total_frames || 0).toLocaleString();
    sbStats.classList.remove('hidden');
  }

  // ── Navegar para tab resultado ──
  const btnRes = document.getElementById('tab-btn-resultado');
  if (btnRes) mudarTab(btnRes);

  if (data.heatmap) {
    const url = `/static/heatmaps/${encodeURIComponent(data.heatmap)}?t=${Date.now()}`;
    const img = document.getElementById('heatmap-img');
    img.src = url;
    img.style.display = 'block';
    const dl = document.getElementById('btn-baixar');
    dl.href     = url;
    dl.download = data.heatmap;
    dl.style.display = 'inline-flex';
  } else {
    setTimeout(() => {
      fetch('/api/atleta/status').then(r => r.json()).then(d => {
        if (d.heatmap) mostrarResultado(d);
      });
    }, 2000);
  }

  // ── CSV download ──
  if (data.csv) {
    const btnCsv = document.getElementById('btn-baixar-csv');
    if (btnCsv) {
      btnCsv.href     = `/api/atleta/csv/${encodeURIComponent(data.csv)}`;
      btnCsv.download = data.csv;
      btnCsv.style.display = 'inline-flex';
    }
  }

  // ── Zonas 3×3 ──
  if (data.zonas) {
    const zonaKeys = [
      'def_esq','mei_esq','ata_esq',
      'def_cen','mei_cen','ata_cen',
      'def_dir','mei_dir','ata_dir',
    ];
    let maxPct = 0;
    zonaKeys.forEach(k => {
      const pct = (data.zonas[k] || {}).pct || 0;
      if (pct > maxPct) maxPct = pct;
    });
    zonaKeys.forEach(k => {
      const cell = document.getElementById(`z-${k}`);
      if (!cell) return;
      const pct  = (data.zonas[k] || {}).pct || 0;
      const span = cell.querySelector('.zona-pct');
      if (span) span.textContent = pct > 0 ? `${pct}%` : '-';
      cell.classList.toggle('ativa', pct > 0 && pct === maxPct);
    });
  }

  // ── Detecções incertas (near-miss log) ──
  const incertos = data.incertos || [];
  let incBox = document.getElementById('incertos-box');
  if (incertos.length > 0) {
    if (!incBox) {
      incBox = document.createElement('div');
      incBox.id = 'incertos-box';
      incBox.style.cssText = 'margin-top:16px;background:rgba(234,179,8,.1);border:1px solid rgba(234,179,8,.35);border-radius:8px;padding:14px;';
      document.getElementById('zonas-wrap').after(incBox);
    }
    const threshold = data.threshold_usado || 0.65;
    const minSim    = (incertos.reduce((a, b) => Math.min(a, b.sim), 1)).toFixed(3);
    const maxSim    = (incertos.reduce((a, b) => Math.max(a, b.sim), 0)).toFixed(3);
    incBox.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-size:13px;font-weight:600;color:#facc15;">⚠️ ${incertos.length} detecções incertas</span>
        <span style="font-size:11px;color:var(--text-muted);">sim ∈ [${minSim}, ${maxSim}] | limiar ${threshold}</span>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
        Foram detectadas pessoas com similaridade próxima (mas abaixo) do limiar.
        Considere <strong>calibrar o limiar</strong> se o atleta estiver sendo perdido.
      </p>
      <details>
        <summary style="font-size:12px;cursor:pointer;color:var(--text-muted);">Ver log detalhado (${incertos.length} entradas)</summary>
        <div style="max-height:140px;overflow-y:auto;margin-top:8px;">
          <table style="width:100%;font-size:11px;border-collapse:collapse;">
            <thead><tr style="color:var(--text-muted);">
              <th style="padding:4px 8px;text-align:left;">Tempo (s)</th>
              <th style="padding:4px 8px;text-align:right;">Frame</th>
              <th style="padding:4px 8px;text-align:right;">Similaridade</th>
            </tr></thead>
            <tbody>${incertos.slice(0, 100).map(ic =>
              `<tr style="border-top:1px solid var(--border);">
                <td style="padding:3px 8px;">${ic.ts}s</td>
                <td style="padding:3px 8px;text-align:right;">${ic.frame}</td>
                <td style="padding:3px 8px;text-align:right;color:#facc15;">${ic.sim}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </details>`;
    incBox.style.display = 'block';
  } else if (incBox) {
    incBox.style.display = 'none';
  }

  toast('Análise concluída!', 'success');
}

// ─── Reset ────────────────────────────────────────────────────────
function resetUI() {
  document.getElementById('progresso-section').classList.add('hidden');
  document.getElementById('heatmap-section').classList.add('hidden');
  document.getElementById('resultado-idle').classList.remove('hidden');
}

// ─── Extrator de referência do vídeo ─────────────────────────────
let _extratorBoxes  = [];   // boxes originais do último frame
let _extratorSrc    = '';
let _extratorTs     = 0;

function toggleExtrator() {
  const sec  = document.getElementById('extrator-section');
  const btn  = document.getElementById('btn-toggle-extrator');
  const idle = document.getElementById('fotos-idle');
  const open = sec.style.display !== 'none';
  sec.style.display  = open ? 'none' : 'block';
  btn.textContent    = open ? '🎬 Extrair referência direto do vídeo'
                             : '🎬 Fechar extrator';
  // Mostrar/esconder idle conforme extrator
  if (idle) idle.classList.toggle('hidden', !open === false ? true : (
    document.getElementById('captura-refs-revisao').style.display === 'block'
  ));
}

async function extrairFrame() {
  const src = document.getElementById('extrator-src').value.trim();
  const ts  = parseFloat(document.getElementById('extrator-ts').value) || 0;
  const btn = document.getElementById('btn-extrair-frame');
  const st  = document.getElementById('extrator-status');

  if (!src) { st.textContent = '⚠ Informe uma URL ou arquivo.'; return; }

  btn.disabled    = true;
  btn.textContent = 'Extraindo…';
  st.textContent  = 'Aguarde, isso pode levar alguns segundos…';
  document.getElementById('extrator-canvas-wrap').style.display = 'none';

  try {
    const res  = await fetch('/api/atleta/frame', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ src, ts }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);

    _extratorBoxes = data.boxes_orig;
    _extratorSrc   = src;
    _extratorTs    = ts;

    // Desenhar frame no canvas
    const wrap   = document.getElementById('extrator-canvas-wrap');
    const canvas = document.getElementById('extrator-canvas');
    const ctx    = canvas.getContext('2d');

    const img = new Image();
    img.onload = () => {
      canvas.width  = data.w;
      canvas.height = data.h;
      ctx.drawImage(img, 0, 0);

      // Desenhar boxes escaladas
      data.boxes.forEach(b => {
        ctx.strokeStyle = '#4ade80';
        ctx.lineWidth   = 2;
        ctx.strokeRect(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1);
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        ctx.fillRect(b.x1, b.y1, 28, 20);
        ctx.fillStyle   = '#4ade80';
        ctx.font        = 'bold 13px sans-serif';
        ctx.fillText(`#${b.i}`, b.x1 + 4, b.y1 + 14);
      });

      wrap.style.display = 'block';
    };
    img.src = 'data:image/jpeg;base64,' + data.frame_b64;

    st.textContent = `${data.boxes.length} pessoa(s) detectada(s). Clique numa caixa verde.`;

    // Click no canvas → identificar qual box foi clicada
    canvas.onclick = (e) => {
      const rect  = canvas.getBoundingClientRect();
      const scaleX = canvas.width  / rect.width;
      const scaleY = canvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top)  * scaleY;

      // Encontrar box (coordenadas escaladas) que contém o clique
      const clicada = data.boxes.find(b =>
        mx >= b.x1 && mx <= b.x2 && my >= b.y1 && my <= b.y2
      );
      if (clicada) salvarCrop(clicada);
    };

  } catch (e) {
    st.textContent = '❌ ' + e.message;
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Extrair Frame';
  }
}

let _capturaRefsTimer = null;

async function capturarRefs() {
  const nome      = document.getElementById('nome-atleta').value.trim();
  const src       = document.getElementById('extrator-src').value.trim() ||
                    document.getElementById('yt-url-atleta')?.value.trim() || '';
  const threshold = parseFloat(document.getElementById('extrator-threshold')?.value ||
                    document.getElementById('threshold-range')?.value) || 0.65;
  const btn       = document.getElementById('btn-capturar-refs');
  const st        = document.getElementById('extrator-status');

  if (!nome) { toast('Preencha o nome do atleta antes de capturar', 'error'); return; }
  if (!src)  { st.textContent = '⚠ Informe a URL do vídeo no campo acima.'; return; }

  btn.disabled    = true;
  btn.textContent = 'Iniciando…';
  st.textContent  = '';
  document.getElementById('captura-refs-progress').style.display = 'block';
  document.getElementById('captura-refs-bar').style.width = '0%';
  document.getElementById('captura-refs-label').textContent = 'Obtendo URL do stream…';
  document.getElementById('captura-refs-count').textContent = '0 salvos';

  try {
    const res  = await fetch('/api/atleta/capturar_refs', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ nome, src, threshold, max_crops: 40, step_s: 8 }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);

    // Iniciar polling
    if (_capturaRefsTimer) clearInterval(_capturaRefsTimer);
    _capturaRefsTimer = setInterval(_pollCaptura, 1500);
  } catch (e) {
    st.textContent = '❌ ' + e.message;
    btn.disabled    = false;
    btn.textContent = '📸 Capturar Automaticamente';
    document.getElementById('captura-refs-progress').style.display = 'none';
  }
}

async function _pollCaptura() {
  try {
    const res  = await fetch('/api/atleta/capturar_refs/status');
    if (!res.ok) { clearInterval(_capturaRefsTimer); return; }
    const data = await res.json();
    const bar   = document.getElementById('captura-refs-bar');
    const label = document.getElementById('captura-refs-label');
    const count = document.getElementById('captura-refs-count');
    const st    = document.getElementById('extrator-status');
    const btn   = document.getElementById('btn-capturar-refs');

    if (!data.status) { clearInterval(_capturaRefsTimer); return; }

    bar.style.width = (data.progresso || 0) + '%';
    count.textContent = `${data.salvos || 0} salvos`;

    if (data.status === 'rodando' || data.status === 'iniciando') {
      label.textContent = data.ts_atual != null
        ? `Analisando ${data.ts_atual}s / ${data.duracao || '?'}s — ${data.avaliados || 0} pessoas avaliadas`
        : 'Carregando modelo…';
    } else if (data.status === 'aguardando_revisao') {
      clearInterval(_capturaRefsTimer);
      bar.style.width = '100%';
      bar.style.background = '#f59e0b';
      label.textContent = `✅ Captura concluída — revise as ${(data.candidatos || []).length} fotos abaixo`;
      count.textContent = `${(data.candidatos || []).length} candidatos`;
      _mostrarRevisao(data);
      // Esconder idle
      const idle = document.getElementById('fotos-idle');
      if (idle) idle.classList.add('hidden');
    } else if (data.status === 'concluido') {
      clearInterval(_capturaRefsTimer);
      label.textContent = `✅ Concluído!`;
      bar.style.background = '#16a34a';
      st.innerHTML = `<span style="color:#16a34a">✅ ${data.salvos} novas fotos salvas para "${data.nome}".
        Total no banco: ${data.n_total} fotos. Clique em <strong>Gerar Embedding</strong> para atualizar.</span>`;
      btn.disabled    = false;
      btn.textContent = '📸 Capturar Automaticamente';
      document.getElementById('btn-gerar-embedding').disabled = false;
      await carregarAtletas();
    } else if (data.status === 'erro') {
      clearInterval(_capturaRefsTimer);
      label.textContent = '❌ Erro';
      st.textContent = '❌ ' + data.error;
      btn.disabled    = false;
      btn.textContent = '📸 Capturar Automaticamente';
    }
  } catch (_) {}
}

const _COR_CSS = {
  azul: '#3b82f6', branco: '#e5e7eb', vermelho: '#ef4444',
  amarelo: '#eab308', verde: '#22c55e', preto: '#374151',
  roxo: '#a855f7', laranja: '#f97316',
};
const _COR_LABEL = {
  azul: 'Azul', branco: 'Branco', vermelho: 'Vermelho',
  amarelo: 'Amarelo', verde: 'Verde', preto: 'Preto',
  roxo: 'Roxo', laranja: 'Laranja',
};

function _mostrarRevisao(data) {
  const panel = document.getElementById('captura-refs-revisao');
  const grid  = document.getElementById('revisao-grid');
  panel.style.display = 'block';
  grid.innerHTML = '';

  // Coletar cores únicas presentes nos candidatos
  const coresPresentes = new Set();
  (data.candidatos || []).forEach(c => {
    Object.keys(c.cores || {}).forEach(cor => coresPresentes.add(cor));
  });

  // Construir chips de cor
  const chipsDiv = document.getElementById('revisao-cor-chips');
  chipsDiv.innerHTML = '';
  // chip "Todos"
  const chipTodos = document.createElement('span');
  chipTodos.textContent = 'Todos';
  chipTodos.dataset.cor = '';
  chipTodos.className = 'revisao-chip ativo';
  chipTodos.style.cssText = `cursor:pointer;padding:3px 10px;border-radius:20px;font-size:12px;
    border:2px solid var(--accent);background:var(--accent);color:#fff;font-weight:600;`;
  chipTodos.addEventListener('click', (e) => _toggleChip(chipTodos, e));
  chipsDiv.appendChild(chipTodos);

  coresPresentes.forEach(cor => {
    const chip = document.createElement('span');
    chip.textContent = _COR_LABEL[cor] || cor;
    chip.dataset.cor = cor;
    chip.className = 'revisao-chip ativo';
    const bg = _COR_CSS[cor] || '#888';
    chip.style.cssText = `cursor:pointer;padding:3px 10px;border-radius:20px;font-size:12px;
      border:2px solid ${bg};background:${bg};color:${cor === 'branco' || cor === 'amarelo' ? '#000' : '#fff'};font-weight:600;`;
    chip.addEventListener('click', (e) => _toggleChip(chip, e));
    chipsDiv.appendChild(chip);
  });

  // Reset sim slider
  const simRange = document.getElementById('revisao-sim-range');
  if (simRange) {
    simRange.value = 0.65;
    document.getElementById('revisao-sim-val').textContent = '0.65';
  }

  (data.candidatos || []).forEach(c => {
    const wrap = document.createElement('div');
    wrap.dataset.arquivo  = c.arquivo;
    wrap.dataset.selected = '1';
    wrap.dataset.sim      = c.sim;
    wrap.dataset.cores    = Object.keys(c.cores || {}).join(',');
    wrap.style.cssText = `
      position:relative;cursor:pointer;border-radius:6px;overflow:hidden;
      border:3px solid #16a34a;transition:opacity .15s,border-color .15s;
      width:64px;flex-shrink:0;
    `;

    // Barra de cores pequena no topo
    const coresList = Object.entries(c.cores || {}).sort((a,b) => b[1]-a[1]).slice(0,3);
    const coresBar  = coresList.map(([cor, pct]) =>
      `<span style="display:inline-block;width:${Math.round(pct*100)}%;height:4px;
        background:${_COR_CSS[cor] || '#888'};"></span>`
    ).join('');

    wrap.innerHTML = `
      <div style="display:flex;height:4px;width:100%;overflow:hidden;">${coresBar}</div>
      <img src="data:image/jpeg;base64,${c.b64}"
           style="width:64px;display:block;" draggable="false">
      <div style="font-size:10px;background:rgba(0,0,0,.65);color:#fff;
                  text-align:center;padding:1px 0;line-height:1.4;">
        ${c.ts}s · ${c.sim.toFixed(2)}
      </div>
      <div class="revisao-check" style="position:absolute;top:3px;right:3px;
           width:16px;height:16px;background:#16a34a;border-radius:50%;
           display:flex;align-items:center;justify-content:center;
           font-size:10px;">✓</div>
    `;
    wrap.addEventListener('click', () => {
      if (wrap.dataset.selected === '1') {
        wrap.dataset.selected = '0';
        wrap.style.borderColor = '#ef4444';
        wrap.style.opacity = '0.4';
        wrap.querySelector('.revisao-check').style.background = '#ef4444';
        wrap.querySelector('.revisao-check').textContent = '✕';
      } else {
        wrap.dataset.selected = '1';
        wrap.style.borderColor = '#16a34a';
        wrap.style.opacity = '1';
        wrap.querySelector('.revisao-check').style.background = '#16a34a';
        wrap.querySelector('.revisao-check').textContent = '✓';
      }
      _atualizarContadorRevisao();
    });
    grid.appendChild(wrap);
  });

  panel.dataset.nome = data.nome || '';
  _atualizarContadorRevisao();
}

// Chips de cor: clicar numa cor mostra SÓ ela; clicar novamente volta a Todos
// Ctrl+clique adiciona à seleção atual (OR)
function _toggleChip(chip, evt) {
  const todos    = document.querySelector('.revisao-chip[data-cor=""]');
  const allChips = [...document.querySelectorAll('.revisao-chip[data-cor]')]
                     .filter(c => c.dataset.cor);

  if (chip === todos) {
    // Todos: reativar tudo
    allChips.forEach(c => { c.classList.add('ativo'); c.style.opacity = '1'; });
    todos.classList.add('ativo'); todos.style.opacity = '1';
  } else {
    const jaEraUnico = chip.classList.contains('ativo') &&
                       allChips.filter(c => c.classList.contains('ativo')).length === 1;
    if (jaEraUnico) {
      // clicar na única ativa → volta a Todos
      allChips.forEach(c => { c.classList.add('ativo'); c.style.opacity = '1'; });
      todos.classList.add('ativo'); todos.style.opacity = '1';
    } else if (evt && (evt.ctrlKey || evt.metaKey)) {
      // Ctrl+clique → adicionar/remover da seleção atual
      chip.classList.toggle('ativo');
      chip.style.opacity = chip.classList.contains('ativo') ? '1' : '0.30';
      todos.classList.remove('ativo'); todos.style.opacity = '0.30';
      // se nenhum ativo → volta a Todos
      if (!allChips.some(c => c.classList.contains('ativo'))) {
        allChips.forEach(c => { c.classList.add('ativo'); c.style.opacity = '1'; });
        todos.classList.add('ativo'); todos.style.opacity = '1';
      }
    } else {
      // clique simples → mostrar SÓ esta cor
      allChips.forEach(c => { c.classList.remove('ativo'); c.style.opacity = '0.30'; });
      todos.classList.remove('ativo'); todos.style.opacity = '0.30';
      chip.classList.add('ativo'); chip.style.opacity = '1';
    }
  }
  _aplicarFiltrosRevisao();
}

function _aplicarFiltrosRevisao() {
  const simMin     = parseFloat(document.getElementById('revisao-sim-range')?.value || 0.65);
  const todosAtivo = document.querySelector('.revisao-chip[data-cor=""]')?.classList.contains('ativo');
  const coresAtivo = todosAtivo ? null :
    [...document.querySelectorAll('.revisao-chip[data-cor]')]
      .filter(c => c.dataset.cor && c.classList.contains('ativo'))
      .map(c => c.dataset.cor);

  document.querySelectorAll('#revisao-grid [data-arquivo]').forEach(wrap => {
    const sim         = parseFloat(wrap.dataset.sim || 0);
    const coresWrap   = (wrap.dataset.cores || '').split(',').filter(Boolean);
    const passaSim    = sim >= simMin;
    const passaCor    = !coresAtivo || coresAtivo.length === 0 ||
                        coresAtivo.some(c => coresWrap.includes(c));
    wrap.style.display = (passaSim && passaCor) ? '' : 'none';
  });
  _atualizarContadorRevisao();
}

function _selecionarVisiveis(selecionar) {
  document.querySelectorAll('#revisao-grid [data-arquivo]').forEach(wrap => {
    if (wrap.style.display === 'none') return;
    wrap.dataset.selected = selecionar ? '1' : '0';
    wrap.style.borderColor  = selecionar ? '#16a34a' : '#ef4444';
    wrap.style.opacity      = selecionar ? '1' : '0.4';
    const chk = wrap.querySelector('.revisao-check');
    if (chk) { chk.style.background = selecionar ? '#16a34a' : '#ef4444'; chk.textContent = selecionar ? '✓' : '✕'; }
  });
  _atualizarContadorRevisao();
}

function _atualizarContadorRevisao() {
  const sel = document.querySelectorAll('#revisao-grid [data-selected="1"]:not([style*="display: none"]):not([style*="display:none"])').length;
  const vis = document.querySelectorAll('#revisao-grid [data-arquivo]:not([style*="display: none"]):not([style*="display:none"])').length;
  const tot = document.querySelectorAll('#revisao-grid [data-arquivo]').length;
  document.getElementById('revisao-counter').textContent = `${sel} selecionadas / ${vis} visíveis / ${tot} total`;
}

async function confirmarCaptura() {
  const panel  = document.getElementById('captura-refs-revisao');
  const nome   = panel.dataset.nome || document.getElementById('nome-atleta').value.trim();
  const items  = document.querySelectorAll('#revisao-grid [data-arquivo][data-selected="1"]');
  const confirmados = Array.from(items).map(el => el.dataset.arquivo);

  const btn = document.getElementById('btn-confirmar-revisao');
  btn.disabled = true;
  btn.textContent = 'Salvando…';

  try {
    const res  = await fetch('/api/atleta/capturar_refs/confirmar', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ nome, confirmados }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);

    panel.style.display = 'none';
    document.getElementById('captura-refs-progress').style.display = 'none';
    const st = document.getElementById('extrator-status');
    st.innerHTML = `<span style="color:#16a34a">✅ ${data.salvos} fotos confirmadas para "${nome}".
      Total no banco: ${data.n_total} fotos. Clique em <strong>Gerar Embedding</strong> para atualizar.</span>`;
    // Mostrar idle novamente
    const idle = document.getElementById('fotos-idle');
    if (idle) idle.classList.remove('hidden');
    document.getElementById('btn-capturar-refs').disabled = false;
    document.getElementById('btn-capturar-refs').textContent = '📸 Capturar Automaticamente';
    document.getElementById('btn-gerar-embedding').disabled = false;
    await carregarAtletas();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = '✅ Confirmar Selecionadas';
    toast('Erro ao confirmar: ' + e.message, 'error');
  }
}

async function cancelarCaptura() {
  const panel = document.getElementById('captura-refs-revisao');
  const nome  = panel.dataset.nome || document.getElementById('nome-atleta').value.trim();
  // confirm without any selected = discard all
  await fetch('/api/atleta/capturar_refs/confirmar', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ nome, confirmados: [] }),
  });
  panel.style.display = 'none';
  document.getElementById('captura-refs-progress').style.display = 'none';
  document.getElementById('btn-capturar-refs').disabled = false;
  document.getElementById('btn-capturar-refs').textContent = '📸 Capturar Automaticamente';
  document.getElementById('extrator-status').textContent = 'Captura descartada.';
  // Mostrar idle novamente
  const idle = document.getElementById('fotos-idle');
  if (idle) idle.classList.remove('hidden');
}

async function testarRastreamento() {  const nome      = document.getElementById('nome-atleta').value.trim();
  const src       = document.getElementById('extrator-src').value.trim();
  const ts        = parseFloat(document.getElementById('extrator-ts').value) || 0;
  const threshold = parseFloat(document.getElementById('extrator-threshold')?.value ||
                    document.getElementById('threshold-range')?.value) || 0.65;
  const btn = document.getElementById('btn-testar-rastreamento');
  const st  = document.getElementById('extrator-status');

  if (!nome) { toast('Preencha o nome do atleta antes de testar', 'error'); return; }
  if (!src)  { st.textContent = '⚠ Informe a URL ou arquivo.'; return; }

  btn.disabled    = true;
  btn.textContent = 'Processando…';
  st.textContent  = '⏳ Baixando frame e rodando ReID (pode levar ~10s)…';
  document.getElementById('extrator-canvas-wrap').style.display = 'none';

  try {
    const res  = await fetch('/api/atleta/testar', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ nome, src, ts, threshold }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);

    const wrap   = document.getElementById('extrator-canvas-wrap');
    const canvas = document.getElementById('extrator-canvas');
    const ctx    = canvas.getContext('2d');
    canvas.onclick = null;   // modo visualização — sem click-to-crop

    const img = new Image();
    img.onload = () => {
      canvas.width  = data.w;
      canvas.height = data.h;
      ctx.drawImage(img, 0, 0);
      wrap.style.display = 'block';
      // Substituir hint
      const hint = document.getElementById('extrator-hint');
      if (hint) hint.style.display = 'none';
    };
    img.src = 'data:image/jpeg;base64,' + data.frame_b64;

    if (data.matches > 0) {
      st.innerHTML = `<span style="color:#d97706">✅ ${data.matches} detecção(ões) de "${nome}" em ${data.total} pessoas detectadas — caixas âmbar = match</span>`;
    } else {
      st.innerHTML = `<span style="color:#ef4444">⚠ Nenhuma detecção acima do limiar ${threshold} (${data.total} pessoas avaliadas). Tente reduzir o limiar ou mudar o timestamp.</span>`;
    }
  } catch (e) {
    st.textContent = '❌ ' + e.message;
  } finally {
    btn.disabled    = false;
    btn.textContent = '🎯 Testar Rastreamento';
  }
}

async function salvarCrop(boxScaled) {
  const nome = document.getElementById('nome-atleta').value.trim();
  if (!nome) { toast('Preencha o nome do atleta antes de salvar o crop', 'error'); return; }

  // Encontrar box original pelo índice
  const boxOrig = _extratorBoxes.find(b => b.i === boxScaled.i);
  if (!boxOrig) return;

  const st = document.getElementById('extrator-status');
  st.textContent = `Salvando pessoa #${boxOrig.i}…`;

  try {
    const res  = await fetch('/api/atleta/crop', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        nome,
        src:  _extratorSrc,
        ts:   _extratorTs,
        box:  { x1: boxOrig.x1, y1: boxOrig.y1, x2: boxOrig.x2, y2: boxOrig.y2 },
      }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);

    st.textContent = `✓ Crop #${boxOrig.i} salvo! Total: ${data.n_fotos} foto(s)`;
    toast(`Pessoa #${boxOrig.i} adicionada como referência`, 'success');

    // Miniatura no painel de crops
    const canvas = document.getElementById('extrator-canvas');
    const ctx    = canvas.getContext('2d');
    const mini   = document.createElement('canvas');
    const scaleX = canvas.width  / canvas.getBoundingClientRect().width  * (canvas.getBoundingClientRect().width  / canvas.width);
    mini.width  = 54; mini.height = 80;
    const mc = mini.getContext('2d');
    // recortar do canvas atual (já tem imagem desenhada)
    mc.drawImage(canvas,
      boxScaled.x1, boxScaled.y1,
      boxScaled.x2 - boxScaled.x1, boxScaled.y2 - boxScaled.y1,
      0, 0, 54, 80
    );
    const thumb = document.createElement('img');
    thumb.src   = mini.toDataURL();
    thumb.title = `Pessoa #${boxOrig.i}`;
    thumb.style.cssText = 'width:54px;height:80px;object-fit:cover;border-radius:6px;' +
                          'border:2px solid #4ade80;';
    document.getElementById('extrator-crops').appendChild(thumb);

    // Habilitar botão de gerar embedding
    fotosFiles = [];   // limpar fotos mas o backend já tem os crops
    document.getElementById('btn-gerar-embedding').disabled = false;
    await carregarAtletas();

  } catch (e) {
    st.textContent = '❌ ' + e.message;
    toast('Erro: ' + e.message, 'error');
  }
}

// ─── FOTOS SALVAS DO ATLETA ──────────────────────────────────────
let _fotosSalvasAtleta = null;

function _atualizarBotaoFotosSalvas(nome, nFotos) {
  const btn   = document.getElementById('btn-ver-fotos-salvas');
  const label = document.getElementById('btn-ver-fotos-label');
  if (!btn) return;
  if (nome) {
    btn.style.display = '';
    _fotosSalvasAtleta = nome;
    if (nFotos > 0) {
      _fotosSalvasTotal = nFotos;
      label.textContent = `Ver ${nFotos} foto${nFotos !== 1 ? 's' : ''} salvas`;
    } else {
      // nFotos === -1 significa "não contado ainda"
      if (nFotos === 0) _fotosSalvasTotal = 0;
      label.textContent = 'Ver fotos salvas';
    }
  } else {
    btn.style.display = 'none';
    _fotosSalvasAtleta = null;
    _fotosSalvasTotal  = 0;
  }
  validarBotaoEmbed();
}

let _fotosSalvasPage = 1;
let _fotosSalvasTotal = 0;
let _fotosSalvasNome  = '';

async function verFotosSalvas() {
  const nome = _fotosSalvasAtleta ||
               document.getElementById('nome-atleta').value.trim();
  if (!nome) { toast('Selecione ou nomeie um atleta primeiro', 'error'); return; }

  _fotosSalvasNome  = nome;
  _fotosSalvasPage  = 1;

  // Esconder idle e revisao, mostrar fotos-salvas
  document.getElementById('fotos-idle').classList.add('hidden');
  document.getElementById('captura-refs-revisao').style.display = 'none';
  const sec = document.getElementById('fotos-salvas-section');
  sec.style.display = 'flex';

  const grid = document.getElementById('fotos-salvas-grid');
  grid.innerHTML = '<div style="color:var(--text-muted);font-size:13px;">Carregando…</div>';

  await _carregarPaginaFotos(nome, 1, true);
}

async function _carregarPaginaFotos(nome, page, reset) {
  const grid = document.getElementById('fotos-salvas-grid');
  try {
    const res  = await fetch(`/api/atleta/refs/${encodeURIComponent(nome)}?page=${page}&per=80`);
    const data = await res.json();

    _fotosSalvasTotal = data.total;
    if (reset) grid.innerHTML = '';
    else {
      const loadMore = grid.querySelector('.load-more-btn');
      if (loadMore) loadMore.remove();
    }

    document.getElementById('fotos-salvas-counter').textContent =
      `${data.total} foto${data.total !== 1 ? 's' : ''}`;

    if (data.total === 0) {
      grid.innerHTML = '<div style="color:var(--text-muted);font-size:13px;">Nenhuma foto salva ainda.</div>';
      return;
    }

    data.fotos.forEach(f => {
      const item = document.createElement('div');
      item.className = 'gallery-item';
      item.dataset.nome = f.nome;
      item.innerHTML = `
        <img src="${f.url}" alt="${f.nome}" loading="lazy">
        <div class="gallery-item-label">${f.nome.substring(0, 18)}</div>
        <div class="gallery-item-del" title="Deletar foto"
             onclick="deletarFotoSalva('${nome}','${f.nome}',this.parentElement)">
          ×
        </div>`;
      grid.appendChild(item);
    });

    // Botão "carregar mais" se houver mais páginas
    const loaded = page * data.per;
    if (loaded < data.total) {
      const btn = document.createElement('div');
      btn.className = 'load-more-btn';
      btn.style.cssText = 'width:100%;text-align:center;padding:12px;cursor:pointer;color:var(--accent);font-size:13px;font-weight:600;';
      btn.textContent = `Carregar mais (${data.total - loaded} restantes…)`;
      btn.onclick = () => {
        _fotosSalvasPage++;
        _carregarPaginaFotos(_fotosSalvasNome, _fotosSalvasPage, false);
      };
      grid.appendChild(btn);
    }

  } catch (e) {
    grid.innerHTML = `<div style="color:#dc2626;font-size:13px;">❌ ${e.message}</div>`;
  }
}

async function deletarFotoSalva(nome, arquivo, el) {
  if (!confirm(`Deletar "${arquivo}"?`)) return;
  el.classList.add('deletando');
  try {
    const res  = await fetch(
      `/api/atleta/refs/${encodeURIComponent(nome)}/${encodeURIComponent(arquivo)}`,
      { method: 'DELETE' }
    );
    const data = await res.json();
    if (data.ok) {
      el.remove();
      document.getElementById('fotos-salvas-counter').textContent =
        `${data.restantes} foto${data.restantes !== 1 ? 's' : ''}`;
      _atualizarBotaoFotosSalvas(nome, data.restantes);
      toast('Foto deletada', 'success');
    } else {
      el.classList.remove('deletando');
      toast('Erro ao deletar: ' + data.erro, 'error');
    }
  } catch (e) {
    el.classList.remove('deletando');
    toast('Erro: ' + e.message, 'error');
  }
}

function fecharFotosSalvas() {
  document.getElementById('fotos-salvas-section').style.display = 'none';
  document.getElementById('classif-rapida-section').style.display = 'none';
  const revisaoAberta  = document.getElementById('captura-refs-revisao').style.display !== 'none';
  const extratorAberto = document.getElementById('extrator-section').style.display !== 'none';
  if (!revisaoAberta && !extratorAberto) {
    document.getElementById('fotos-idle').classList.remove('hidden');
  }
}

// ─── FILTRO AUTO (Laplacian + Canny) ───────────────────────────────

async function filtrarBorradasAuto() {
  const nome = _fotosSalvasNome || _fotosSalvasAtleta ||
               document.getElementById('nome-atleta').value.trim();
  if (!nome) { toast('Selecione um atleta primeiro', 'error'); return; }

  const btn = document.getElementById('btn-filtro-auto');
  btn.disabled = true;
  btn.textContent = '🔄 Analisando…';

  try {
    const res  = await fetch(`/api/atleta/refs/${encodeURIComponent(nome)}/qualidade`);
    const data = await res.json();
    const ruins = data.ruins || [];

    btn.disabled = false;
    btn.textContent = '🔍 Filtrar borradas';

    if (ruins.length === 0) {
      toast(`✅ Todas as ${data.total_pasta} fotos passaram no filtro de qualidade!`, 'success');
      return;
    }

    // Marca fotos ruins com overlay vermelho no grid atual
    const grid = document.getElementById('fotos-salvas-grid');
    let marcadas = 0;
    ruins.forEach(r => {
      const item = [...grid.querySelectorAll('.gallery-item')]
        .find(el => el.dataset.nome === r.arquivo);
      if (item) {
        item.style.outline = '2px solid #dc2626';
        item.title = `Baixa qualidade: ${r.motivo} (score ${r.score})`;
        marcadas++;
      }
    });

    const confirmar = confirm(
      `🔍 Filtro clássico (Laplacian + Canny) encontrou:\n\n` +
      `  • ${ruins.length} fotos com baixa qualidade (de ${data.total_pasta} total)\n` +
      `  • ${marcadas} visíveis no grid atual\n\n` +
      `Motivos mais comuns:\n` +
      [...new Set(ruins.slice(0,5).map(r => '  • ' + r.motivo))].join('\n') +
      `\n\nDeletar todas as fotos de baixa qualidade?`
    );

    if (!confirmar) return;

    const res2  = await fetch(
      `/api/atleta/refs/${encodeURIComponent(nome)}/qualidade/deletar_ruins`,
      { method: 'POST' }
    );
    const data2 = await res2.json();
    toast(`🗑️ ${data2.deletadas} fotos ruins deletadas. Restam ${data2.restantes}.`, 'success');
    _atualizarBotaoFotosSalvas(nome, data2.restantes);
    await verFotosSalvas();  // Recarrega grid

  } catch(e) {
    btn.disabled = false;
    btn.textContent = '🔍 Filtrar borradas';
    toast('Erro no filtro: ' + e.message, 'error');
  }
}

// ─── CLASSIFICAÇÃO RÁPIDA ────────────────────────────────────────
const _cr = {
  fotos: [], index: 0, page: 1, pages: 1,
  nome: '', mantidas: 0, deletadas: 0,
  busy: false
};

async function iniciarClassificacaoRapida() {
  const nome = _fotosSalvasNome || _fotosSalvasAtleta ||
               document.getElementById('nome-atleta').value.trim();
  if (!nome) { toast('Nenhum atleta selecionado', 'error'); return; }

  _cr.fotos = []; _cr.index = 0; _cr.page = 1; _cr.pages = 1;
  _cr.nome = nome; _cr.mantidas = 0; _cr.deletadas = 0; _cr.busy = false;

  document.getElementById('fotos-salvas-section').style.display  = 'none';
  document.getElementById('classif-rapida-section').style.display = 'flex';
  document.getElementById('classif-titulo').textContent = `⚡ ${nome}`;
  document.getElementById('classif-img').src = '';
  document.getElementById('classif-nome').textContent = 'Carregando…';

  await _crCarregarPagina(1);
  _crMostrar();
}

async function _crCarregarPagina(page) {
  const res  = await fetch(`/api/atleta/refs/${encodeURIComponent(_cr.nome)}?page=${page}&per=80`);
  const data = await res.json();
  _cr.pages = data.pages;
  data.fotos.forEach(f => _cr.fotos.push(f));
}

function _crMostrar() {
  if (_cr.fotos.length === 0) {
    document.getElementById('classif-nome').textContent = 'Nenhuma foto encontrada.';
    return;
  }
  const f    = _cr.fotos[_cr.index];
  const img  = document.getElementById('classif-img');
  img.className = '';
  img.src = f.url;
  document.getElementById('classif-nome').textContent = f.nome;

  const total = _cr.fotos.length;
  const pos   = _cr.index + 1;
  document.getElementById('classif-progresso').textContent = `${pos} / ${total}`;
  document.getElementById('classif-stats').textContent = `✓ ${_cr.mantidas}   ✗ ${_cr.deletadas}`;
  document.getElementById('classif-barra').style.width = `${Math.round(pos / total * 100)}%`;

  // Pré-carregar próxima
  if (_cr.index + 1 < _cr.fotos.length) {
    document.getElementById('classif-img-preload').src = _cr.fotos[_cr.index + 1].url;
  }

  // Carregar próxima página antecipadamente
  const loadedPages = Math.ceil(_cr.fotos.length / 80);
  if (_cr.index >= _cr.fotos.length - 20 && loadedPages < _cr.pages) {
    _crCarregarPagina(loadedPages + 1);
  }
}

async function _classifManter() {
  if (_cr.busy || _cr.fotos.length === 0) return;
  const img = document.getElementById('classif-img');
  img.className = 'ok';
  _cr.mantidas++;
  _crAvancar();
}

async function _classifDeletar() {
  if (_cr.busy || _cr.fotos.length === 0) return;
  _cr.busy = true;
  const img = document.getElementById('classif-img');
  img.className = 'del';
  const f   = _cr.fotos[_cr.index];
  try {
    await fetch(
      `/api/atleta/refs/${encodeURIComponent(_cr.nome)}/${encodeURIComponent(f.nome)}`,
      { method: 'DELETE' }
    );
  } catch(e) { /* silencioso */ }
  _cr.fotos.splice(_cr.index, 1);
  _cr.deletadas++;
  _cr.busy = false;
  if (_cr.index >= _cr.fotos.length) _cr.index = Math.max(0, _cr.fotos.length - 1);
  if (_cr.fotos.length === 0) {
    document.getElementById('classif-nome').textContent = '✅ Todas as fotos revisadas!';
    document.getElementById('classif-img').src = '';
    document.getElementById('classif-barra').style.width = '100%';
    document.getElementById('classif-progresso').textContent = `0 restantes`;
    document.getElementById('classif-stats').textContent = `✓ ${_cr.mantidas}   ✗ ${_cr.deletadas}`;
    _atualizarBotaoFotosSalvas(_cr.nome, 0);
    return;
  }
  _crMostrar();
}

function _crAvancar() {
  _cr.index++;
  if (_cr.index >= _cr.fotos.length) {
    document.getElementById('classif-nome').textContent = '✅ Classificação concluída!';
    document.getElementById('classif-img').src = '';
    document.getElementById('classif-barra').style.width = '100%';
    document.getElementById('classif-progresso').textContent = 'Concluído';
    document.getElementById('classif-stats').textContent = `✓ ${_cr.mantidas}   ✗ ${_cr.deletadas}`;
    _atualizarBotaoFotosSalvas(_cr.nome, _cr.fotos.length);
    return;
  }
  _crMostrar();
}

function _classifSair() {
  document.getElementById('classif-rapida-section').style.display = 'none';
  verFotosSalvas();
}

// Atalhos de teclado para classificação rápida
document.addEventListener('keydown', e => {
  const sec = document.getElementById('classif-rapida-section');
  if (!sec || sec.style.display === 'none') return;
  if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); _classifManter(); }
  if (e.key === 'ArrowLeft'  || e.key === 'Delete') { e.preventDefault(); _classifDeletar(); }
});

// ─── CALIBRAÇÃO DE THRESHOLD ───────────────────────────────────────
async function calibrarThreshold() {
  const nome = document.getElementById('nome-atleta').value.trim();
  if (!nome) { toast('Informe o nome do atleta primeiro', 'error'); return; }

  const painel = document.getElementById('calibrar-painel');
  const loading = document.getElementById('calibrar-loading');
  const resultado = document.getElementById('calibrar-resultado');
  const btn = document.getElementById('btn-calibrar-limiar');

  painel.classList.remove('hidden');
  loading.style.display = 'block';
  resultado.classList.add('hidden');
  btn.disabled = true;
  btn.textContent = '🔄 Calculando…';
  painel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const res  = await fetch(`/api/atleta/${encodeURIComponent(nome)}/calibrar_threshold`);
    const data = await res.json();
    if (data.erro) { toast(data.erro, 'error'); loading.style.display = 'none'; return; }

    // ─ stats principais
    document.getElementById('cal-best-t').textContent = data.best_threshold.toFixed(2);
    document.getElementById('cal-best-f1').textContent = (data.best_f1 * 100).toFixed(1) + '%';
    document.getElementById('cal-n-pos').textContent   = data.n_positivos;

    // ─ aviso se sem negativos reais
    const avisoNeg = document.getElementById('cal-aviso-neg');
    if (data.n_negativos < 20) { avisoNeg.classList.remove('hidden'); }
    else                       { avisoNeg.classList.add('hidden'); }

    // ─ tabela P/R/F1
    const tbody = document.getElementById('cal-tabela-body');
    tbody.innerHTML = '';
    const currentThreshold = parseFloat(
      (document.getElementById('threshold-slider') || {}).value || 0.65
    );

    data.thresholds.forEach((t, i) => {
      const isBest    = t === data.best_threshold;
      const isCurrent = Math.abs(t - currentThreshold) < 0.015;
      const bg = isBest ? 'background:rgba(34,197,94,.15);font-weight:700;'
               : isCurrent ? 'background:rgba(250,204,21,.12);'
               : '';
      tbody.innerHTML += `
        <tr style="border-top:1px solid var(--border);${bg}">
          <td style="padding:6px 10px;">
            ${t.toFixed(2)}
            ${isBest    ? ' <span style="color:#22c55e;font-size:11px;">&#x2605; melhor</span>' : ''}
            ${isCurrent ? ' <span style="color:#facc15;font-size:11px;">(atual)</span>' : ''}
          </td>
          <td style="padding:6px 10px;text-align:right;">${(data.precision[i]*100).toFixed(1)}%</td>
          <td style="padding:6px 10px;text-align:right;">${(data.recall[i]*100).toFixed(1)}%</td>
          <td style="padding:6px 10px;text-align:right;">${(data.f1[i]*100).toFixed(1)}%</td>
        </tr>`;
    });

    loading.style.display = 'none';
    resultado.classList.remove('hidden');
    toast(`📈 Threshold ótimo: ${data.best_threshold.toFixed(2)} (F1=${(data.best_f1*100).toFixed(1)}%)`, 'success');

  } catch(e) {
    toast('Erro ao calibrar: ' + e.message, 'error');
    loading.style.display = 'none';
  } finally {
    btn.disabled = false;
    btn.textContent = '📈 Calibrar limiar';
  }
}


// ─── MATRIZ DE CONFUSÃO ───────────────────────────────────────────
async function mostrarMatrizConfusao() {
  const painel  = document.getElementById('matriz-painel');
  const loading = document.getElementById('matriz-loading');
  const resultado = document.getElementById('matriz-resultado');
  const btn     = document.getElementById('btn-matriz-confusao');

  painel.classList.remove('hidden');
  loading.style.display = 'block';
  resultado.classList.add('hidden');
  btn.disabled = true;
  btn.textContent = '🔄 Calculando…';
  painel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const res  = await fetch('/api/atleta/matriz_confusao');
    const data = await res.json();
    if (data.erro) { toast(data.erro, 'error'); loading.style.display = 'none'; return; }
    if (data.aviso) { toast(data.aviso, 'info'); loading.style.display = 'none'; return; }

    const { atletas, matrix } = data;
    const n = atletas.length;

    // Construir tabela HTML
    let html = '<table style="border-collapse:collapse;font-size:12px;width:100%;">';

    // cabeçalho
    html += '<thead><tr><th style="padding:6px 10px;text-align:left;"></th>';
    atletas.forEach(a => {
      html += `<th style="padding:6px 10px;text-align:center;color:var(--text-muted);white-space:nowrap;">${a}</th>`;
    });
    html += '</tr></thead><tbody>';

    // linhas
    matrix.forEach((row, i) => {
      html += `<tr><td style="padding:6px 10px;font-weight:600;white-space:nowrap;">${atletas[i]}</td>`;
      row.forEach((val, j) => {
        const isDiag  = i === j;
        const isHigh  = !isDiag && val >= 0.50;
        const pct     = (val * 100).toFixed(1);
        // mapeamento de cor: diagonal = verde, alto fora da diagonal = laranja, normal = escala cinza
        let bg, color;
        if (isDiag)  { bg = `rgba(34,197,94,${Math.min(val, 0.9)})`;   color = '#fff'; }
        else if (isHigh) { bg = `rgba(249,115,22,${val * 0.7})`;        color = '#fff'; }
        else         { bg = `rgba(100,116,139,${val * 0.5})`;           color = 'var(--text-muted)'; }
        html += `<td style="padding:8px 10px;text-align:center;background:${bg};color:${color};border:1px solid var(--border);">${pct}%</td>`;
      });
      html += '</tr>';
    });

    html += '</tbody></table>';
    document.getElementById('matriz-tabela-wrap').innerHTML = html;

    loading.style.display = 'none';
    resultado.classList.remove('hidden');
    toast(`🔀 Matriz calculada para ${n} atleta${n !== 1 ? 's' : ''}`, 'success');

  } catch(e) {
    toast('Erro ao calcular matriz: ' + e.message, 'error');
    loading.style.display = 'none';
  } finally {
    btn.disabled = false;
    btn.textContent = '🔀 Matriz de confusão';
  }
}
