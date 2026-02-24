/* ============================================================
   VIDEOS.JS — Terça Nobre
   ============================================================ */

// Estado de seleção de vídeo por câmera
const selecionado = { esq: null, dir: null };

// -------- Toast --------
function mostrarToast(msg, tipo = 'ok') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (tipo === 'error' ? ' error' : '');
  t.classList.remove('hidden');
  setTimeout(() => t.classList.add('hidden'), 4000);
}

// -------- Source tabs --------
function setSource(cam, source) {
  // Atualiza botões
  document.querySelectorAll(`.source-tab[data-cam="${cam}"]`).forEach(btn => {
    btn.classList.toggle('active', btn.dataset.source === source);
  });
  // Mostra/oculta painéis
  document.getElementById(`${cam}-panel-youtube`).classList.toggle('hidden', source !== 'youtube');
  document.getElementById(`${cam}-panel-local`).classList.toggle('hidden',   source !== 'local');

  if (source === 'local') { /* painel local sem lista pré-carregada, usa zenity */ }
}

// -------- Buscar info YouTube --------
async function buscarInfo(cam) {
  const url = document.getElementById(`${cam}-url`).value.trim();
  if (!url) { mostrarToast('Cole uma URL do YouTube primeiro', 'error'); return; }

  const btn = document.querySelector(`.camera-card#card-${cam} .btn-buscar`);
  btn.disabled = true;
  btn.textContent = '⏳';
  ocultarInfo(cam);

  try {
    const res  = await fetch('/api/videos/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erro desconhecido');

    document.getElementById(`${cam}-thumb`).src       = data.thumbnail || '';
    document.getElementById(`${cam}-title`).textContent    = data.title || '';
    document.getElementById(`${cam}-uploader`).textContent = data.uploader || '';
    document.getElementById(`${cam}-duration`).textContent = formatarDuracao(data.duration);
    document.getElementById(`${cam}-info`).classList.remove('hidden');

    document.getElementById(`${cam}-btn-stream`).disabled = false;
    mostrarToast(`Vídeo encontrado: ${data.title}`);
  } catch (e) {
    mostrarToast('Erro ao buscar: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Buscar';
  }
}

function ocultarInfo(cam) {
  document.getElementById(`${cam}-info`).classList.add('hidden');
  document.getElementById(`${cam}-btn-stream`).disabled = true;
}

function formatarDuracao(segundos) {
  if (!segundos) return '';
  const h = Math.floor(segundos / 3600);
  const m = Math.floor((segundos % 3600) / 60);
  const s = segundos % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// -------- Stream sem download --------
async function usarStream(cam) {
  const url = document.getElementById(`${cam}-url`).value.trim();
  if (!url) return;

  const btn = document.getElementById(`${cam}-btn-stream`);
  btn.disabled = true;
  btn.textContent = '⏳';
  mostrarToast('Obtendo URL de stream…');

  try {
    const res  = await fetch('/api/videos/stream-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Falha ao obter stream');

    const title = document.getElementById(`${cam}-title`).textContent || url;
    marcarSelecionado(cam, data.stream_url, `▶ ${title} (stream)`);
    mostrarToast('✅ Stream pronto!');
  } catch (e) {
    mostrarToast('Erro no stream: ' + e.message, 'error');
    btn.disabled = false;
  } finally {
    btn.textContent = '▶ Usar stream';
    btn.disabled = false;
  }
}

// -------- Baixar vídeo --------
async function baixarVideo(cam) {
  const url  = document.getElementById(`${cam}-url`).value.trim();
  const nome = (document.getElementById(`${cam}-title`).textContent || '').replace(/[/\\]/g, '_');
  if (!url) return;

  document.getElementById(`${cam}-btn-dl`).disabled = true;
  document.getElementById(`${cam}-dl-progress`).classList.remove('hidden');
  mostrarToast('Download iniciado…');

  try {
    const res  = await fetch('/api/videos/baixar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, nome }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Falha no download');

    mostrarToast('✅ Download concluído!');
    // Seleciona automaticamente o arquivo baixado
    if (data.path) {
      const filename = data.path.split('/').pop();
      marcarSelecionado(cam, data.path, filename);
    }
    // Atualiza lista
    carregarLista();
  } catch (e) {
    mostrarToast('Erro no download: ' + e.message, 'error');
    document.getElementById(`${cam}-btn-dl`).disabled = false;
  } finally {
    document.getElementById(`${cam}-dl-progress`).classList.add('hidden');
  }
}

// -------- Lista local por câmera --------
async function carregarListaCam(cam) {
  const wrap = document.getElementById(`${cam}-local-list`);
  wrap.innerHTML = '<div class="no-videos">Carregando…</div>';
  try {
    const res  = await fetch('/api/videos/lista');
    const data = await res.json();
    if (!data.success || !data.videos.length) {
      wrap.innerHTML = '<div class="no-videos">Nenhum vídeo na pasta videos/</div>';
      return;
    }
    wrap.innerHTML = data.videos.map(v => `
      <div class="local-item ${selecionado[cam] === v.path ? 'selected' : ''}"
           onclick="selecionarVideo('${cam}', '${v.path.replace(/'/g,"\\'")}', '${v.name.replace(/'/g,"\\'")}')">
        <span class="local-item-name">${v.name}</span>
        <span class="local-item-size">${v.size_mb} MB</span>
      </div>
    `).join('');
  } catch {
    wrap.innerHTML = '<div class="no-videos">Erro ao carregar lista</div>';
  }
}

// -------- Selecionar / limpar --------
function selecionarVideo(cam, path, name) {
  marcarSelecionado(cam, path, name);
  // Atualiza highlight na lista
  document.querySelectorAll(`#${cam}-local-list .local-item`).forEach(el => {
    el.classList.toggle('selected', el.querySelector('.local-item-name').textContent === name);
  });
}

function marcarSelecionado(cam, path, name) {
  selecionado[cam] = path;
  document.getElementById(`${cam}-selected-name`).textContent = name;
  document.getElementById(`${cam}-selected`).classList.remove('hidden');
  const label = cam === 'esq' ? 'Câmera 1' : 'Câmera 2';
  mostrarToast(`${label} → ${name}`);
  atualizarBtnProcessar();
}

function limparSelecao(cam) {
  selecionado[cam] = null;
  document.getElementById(`${cam}-selected`).classList.add('hidden');
  atualizarBtnProcessar();
}

function atualizarBtnProcessar() {
  const isDual = document.getElementById('toggle-dual-cam').checked;
  const ok = isDual
    ? (selecionado.esq && selecionado.dir)
    : selecionado.esq;
  const btn = document.getElementById('btn-processar');
  if (btn) btn.disabled = !ok;
}

// -------- Toggle dual-cam --------
function toggleDualCam(isDual) {
  const grid    = document.getElementById('cameras-grid');
  const cardDir = document.getElementById('card-dir');
  const hint    = document.getElementById('dual-cam-hint');

  if (isDual) {
    grid.classList.remove('single-cam');
    cardDir.classList.remove('hidden');
    hint.innerHTML = 'Modo atual: <strong>2 vídeos</strong> (Câmera 1 e Câmera 2 independentes)';
  } else {
    grid.classList.add('single-cam');
    cardDir.classList.add('hidden');
    limparSelecao('dir');
    hint.innerHTML = 'Modo atual: <strong>1 vídeo</strong> (mesmo arquivo para Câmera 1 e 2)';
  }
  atualizarBtnProcessar();
}

// -------- Processar --------
let _pollInterval = null;

async function processarVideos() {
  const isDual = document.getElementById('toggle-dual-cam').checked;
  const ve = selecionado.esq;
  const vd = isDual ? selecionado.dir : null;

  if (!ve) {
    mostrarToast('Selecione ao menos um vídeo antes de processar', 'error');
    return;
  }
  if (isDual && !vd) {
    mostrarToast('No modo 2 vídeos selecione também o vídeo da Câmera 2', 'error');
    return;
  }

  const btn = document.getElementById('btn-processar');
  btn.disabled = true;

  const statusBox = document.getElementById('status-box');
  statusBox.className = 'status-box';
  statusBox.classList.remove('hidden');
  document.getElementById('status-icon').textContent  = '⚙️';
  document.getElementById('status-title').textContent = 'Iniciando captura…';
  document.getElementById('status-msg').textContent   = 'Aguardando inicialização do script (pode levar ~15s para o stream iniciar)…';
  document.getElementById('status-counters').classList.add('hidden');
  document.getElementById('status-log-wrap').classList.add('hidden');
  document.getElementById('status-badge').classList.add('hidden');

  try {
    const model      = document.getElementById('cfg-model').value;
    const confidence = parseFloat(document.getElementById('cfg-confidence').value);
    const outputDir  = document.getElementById('cfg-output').value.trim() || 'jogadores_terca';

    const res  = await fetch('/api/videos/processar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_esq:  ve || '',
        video_dir:  vd || '',
        model,
        confidence,
        output_dir: outputDir,
      }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Erro ao iniciar');

    mostrarToast(`Script iniciado (PID ${data.pid})`);
    document.getElementById('btn-processar').classList.add('hidden');
    document.getElementById('btn-parar').classList.remove('hidden');
    iniciarPolling();
  } catch (e) {
    statusBox.classList.add('error');
    document.getElementById('status-icon').textContent  = '❌';
    document.getElementById('status-title').textContent = 'Erro ao iniciar captura';
    document.getElementById('status-msg').textContent   = e.message;
    mostrarToast('Erro: ' + e.message, 'error');
    btn.disabled = false;
    document.getElementById('btn-parar').classList.add('hidden');
    document.getElementById('btn-processar').classList.remove('hidden');
  }
}

async function pararCaptura() {
  const btnParar = document.getElementById('btn-parar');
  btnParar.disabled = true;
  btnParar.textContent = '⏳ Parando…';
  try {
    const res  = await fetch('/api/videos/parar', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      mostrarToast('⏹ Captura interrompida pelo usuário', 'warn');
    } else {
      mostrarToast('Erro ao parar: ' + (data.error || 'desconhecido'), 'error');
    }
  } catch (e) {
    mostrarToast('Erro: ' + e.message, 'error');
  } finally {
    btnParar.disabled = false;
    btnParar.textContent = '⏹ Parar Captura';
  }
}

function iniciarPolling() {
  if (_pollInterval) clearInterval(_pollInterval);
  _pollInterval = setInterval(atualizarStatus, 3000);
  atualizarStatus(); // imediato
}

async function atualizarStatus() {
  try {
    const res  = await fetch('/api/videos/status');
    const data = await res.json();

    const statusBox = document.getElementById('status-box');
    const badge     = document.getElementById('status-badge');

    // Counters
    document.getElementById('status-counters').classList.remove('hidden');
    document.getElementById('counter-new').textContent   = data.imgs_new  ?? '—';
    document.getElementById('counter-total').textContent = data.imgs_total ?? '—';

    // Badge running/stopped
    badge.classList.remove('hidden');
    if (data.running) {
      badge.textContent = '● rodando';
      badge.className   = 'status-badge running';
      statusBox.className = 'status-box';
      document.getElementById('status-icon').textContent  = '⚙️';
      document.getElementById('status-title').textContent =
        `Capturando… (PID: ${data.pid})`;
      document.getElementById('btn-processar').classList.add('hidden');
      document.getElementById('btn-parar').classList.remove('hidden');
    } else {
      badge.textContent = '■ finalizado';
      badge.className   = 'status-badge stopped';
      statusBox.classList.add('success');
      document.getElementById('status-icon').textContent  = '✅';
      document.getElementById('status-title').textContent = 'Captura finalizada';
      document.getElementById('btn-processar').disabled = false;
      document.getElementById('btn-processar').classList.remove('hidden');
      document.getElementById('btn-parar').classList.add('hidden');
      atualizarBtnProcessar();
      clearInterval(_pollInterval);
      _pollInterval = null;
      mostrarToast(`✅ Captura encerrada — ${data.imgs_new} novas imagens`);
      carregarHistorico(true);
    }

    // Log
    if (data.log && data.log.length) {
      document.getElementById('status-log-wrap').classList.remove('hidden');
      document.getElementById('status-msg').textContent = '';
      const logEl = document.getElementById('status-log');
      logEl.textContent = data.log.join('\n');
      if (document.getElementById('log-autoscroll').checked) {
        logEl.scrollTop = logEl.scrollHeight;
      }
    }
  } catch {
    // silencia erros de rede temporários
  }
}

// -------- Lista de vídeos (colapsável) --------
function toggleVideosList() {
  const body    = document.getElementById('videos-table-wrap');
  const chevron = document.getElementById('lista-chevron');
  const isOpen  = !body.classList.contains('collapsed');
  if (isOpen) {
    body.classList.add('collapsed');
    chevron.classList.remove('open');
  } else {
    body.classList.remove('collapsed');
    chevron.classList.add('open');
  }
}

async function carregarLista(autoExpand = false) {
  const wrap = document.getElementById('videos-table-wrap');
  wrap.innerHTML = '<div class="loading-row">Carregando…</div>';
  try {
    const res  = await fetch('/api/videos/lista');
    const data = await res.json();

    if (!data.success || !data.videos.length) {
      wrap.innerHTML = '<div class="loading-row">Nenhum vídeo encontrado na pasta videos/</div>';
      document.getElementById('videos-lista-count').textContent = '';
      return;
    }

    document.getElementById('videos-lista-count').textContent = `(${data.videos.length})`;
    if (autoExpand) {
      document.getElementById('videos-table-wrap').classList.remove('collapsed');
      document.getElementById('lista-chevron').classList.add('open');
    }

    wrap.innerHTML = `
      <table class="videos-table">
        <thead>
          <tr>
            <th>Nome</th>
            <th>Tamanho</th>
            <th>Usar como</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${data.videos.map(v => `
            <tr>
              <td class="tbl-name">${v.name}</td>
              <td>${v.size_mb} MB</td>
              <td>
                <div class="tbl-actions">
                  <button class="btn-usar" onclick="selecionarVideo('esq', '${v.path.replace(/'/g,"\\'")}', '${v.name.replace(/'/g,"\\'")}')">🔵 ESQ</button>
                  <button class="btn-usar" onclick="selecionarVideo('dir', '${v.path.replace(/'/g,"\\'")}', '${v.name.replace(/'/g,"\\'")}')">⚫ DIR</button>
                </div>
              </td>
              <td>
                <button class="btn-del" onclick="deletarVideo('${v.name.replace(/'/g,"\\'")}')">🗑</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;
  } catch {
    wrap.innerHTML = '<div class="loading-row">Erro ao carregar lista</div>';
  }
}

async function deletarVideo(nome) {
  if (!confirm(`Remover "${nome}"?`)) return;
  try {
    const res  = await fetch('/api/videos/deletar', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    mostrarToast(`${nome} removido`);
    carregarLista();
    // Limpa seleção se era este vídeo
    ['esq', 'dir'].forEach(cam => {
      if (selecionado[cam] && selecionado[cam].endsWith(nome)) limparSelecao(cam);
    });
  } catch (e) {
    mostrarToast('Erro: ' + e.message, 'error');
  }
}

// -------- Histórico de capturas --------
function toggleHistorico() {
  const body    = document.getElementById('historico-wrap');
  const chevron = document.getElementById('historico-chevron');
  const isOpen  = !body.classList.contains('collapsed');
  if (isOpen) {
    body.classList.add('collapsed');
    chevron.classList.remove('open');
  } else {
    body.classList.remove('collapsed');
    chevron.classList.add('open');
    // Lazy: carrega apenas quando abrir pela primeira vez
    if (body.querySelector('.loading-row')) carregarHistorico(false);
  }
}

async function carregarHistorico(autoExpand = false) {
  const wrap = document.getElementById('historico-wrap');
  try {
    const res  = await fetch('/api/videos/historico');
    const data = await res.json();
    const hist = data.historico || [];

    document.getElementById('historico-count').textContent = hist.length ? `(${hist.length})` : '';

    if (!hist.length) {
      wrap.innerHTML = '<div class="loading-row">Nenhuma captura registrada ainda</div>';
      return;
    }

    wrap.innerHTML = `
      <table class="videos-table hist-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Data</th>
              <th>Câm. 1</th>
            <th>Câm. 2</th>
            <th>Modelo</th>
            <th>Conf.</th>
            <th>Novas</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          ${hist.map(h => `
            <tr>
              <td>${h.id}</td>
              <td class="hist-data">${h.data_inicio?.replace('T',' ') ?? '—'}</td>
              <td class="hist-video" title="${h.video_esq}">${baseName(h.video_esq)}</td>
              <td class="hist-video" title="${h.video_dir}">${baseName(h.video_dir)}</td>
              <td><code>${h.model ?? '—'}</code></td>
              <td>${h.confidence ?? '—'}</td>
              <td class="hist-new">${h.imgs_novas ?? '—'}</td>
              <td>${h.imgs_total ?? '—'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    if (autoExpand) {
      wrap.classList.remove('collapsed');
      document.getElementById('historico-chevron').classList.add('open');
    }
  } catch {
    wrap.innerHTML = '<div class="loading-row">Erro ao carregar histórico</div>';
  }
}

function baseName(p) {
  if (!p || p === '(padrão)') return p || '—';
  return p.split('/').pop() || p;
}

// -------- Init --------
document.addEventListener('DOMContentLoaded', () => {
  // Inicia em modo câmera única
  toggleDualCam(false);

  carregarHistorico(false);
  // Permite Buscar com Enter nos inputs
  ['esq', 'dir'].forEach(cam => {
    document.getElementById(`${cam}-url`).addEventListener('keydown', e => {
      if (e.key === 'Enter') buscarInfo(cam);
    });
  });

  // Auto-recover: se já houver uma captura ativa ao abrir a página, mostra painel e inicia polling
  fetch('/api/videos/status').then(r => r.json()).then(data => {
    if (data.running) {
      document.getElementById('status-box').classList.remove('hidden');
      document.getElementById('btn-processar').classList.add('hidden');
      document.getElementById('btn-parar').classList.remove('hidden');
      iniciarPolling();
      mostrarToast('⚙️ Captura em andamento detectada (PID ' + data.pid + ')');
    }
  }).catch(() => {});
});

// -------- Arquivo local: navegação via zenity --------
async function escolherArquivo(cam) {
  const btn = document.getElementById(`${cam}-btn-browse`);
  btn.disabled = true;
  btn.textContent = '⏳ Abrindo…';
  try {
    const res  = await fetch('/api/videos/browse');
    const data = await res.json();
    if (data.success) {
      marcarSelecionado(cam, data.path, data.name);
      mostrarToast(`📂 ${data.name} selecionado`);
    } else if (data.error !== 'Seleção cancelada') {
      mostrarToast('Erro: ' + data.error, 'error');
    }
  } catch (e) {
    mostrarToast('Erro ao abrir seletor: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '📂 Procurar no computador…';
  }
}
