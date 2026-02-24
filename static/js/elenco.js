// ============================================
// GERENCIAMENTO DE ELENCO
// ============================================

// Estado global
let timeAtual = null;

// ============================================
// INICIALIZAÇÃO
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('📋 Sistema de gerenciamento de elenco carregado');
    
    // Permite Enter no input para adicionar
    const inputNome = document.getElementById('nomeJogador');
    if (inputNome) {
        inputNome.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                adicionarJogador();
            }
        });
    }
});

// ============================================
// MODAL
// ============================================

function abrirModalAdicionar(time) {
    const modal = document.getElementById('modalAdicionar');
    const modalTitle = document.getElementById('modalTitle');
    const timeDestino = document.getElementById('timeDestino');
    const inputNome = document.getElementById('nomeJogador');
    
    timeAtual = time;
    timeDestino.value = time;
    
    const emoji = time === 'azul' ? '🔵' : '⚫';
    const nomeTime = time === 'azul' ? 'Azul' : 'Preto';
    
    modalTitle.textContent = `${emoji} Adicionar ao Time ${nomeTime}`;
    inputNome.value = '';
    
    modal.classList.add('active');
    inputNome.focus();
}

function fecharModal() {
    const modal = document.getElementById('modalAdicionar');
    modal.classList.remove('active');
    timeAtual = null;
}

// Fecha modal ao clicar fora
window.onclick = function(event) {
    const modal = document.getElementById('modalAdicionar');
    if (event.target === modal) {
        fecharModal();
    }
};

// ============================================
// CRUD DE JOGADORES
// ============================================

async function adicionarJogador() {
    const inputNome = document.getElementById('nomeJogador');
    const nome = inputNome.value.trim();
    const time = document.getElementById('timeDestino').value;
    
    if (!nome) {
        mostrarToast('⚠️ Digite o nome do jogador', 'warning');
        inputNome.focus();
        return;
    }
    
    try {
        const response = await fetch('/api/elenco/jogador', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ nome, time })
        });
        
        const result = await response.json();
        
        if (result.success) {
            mostrarToast(`✅ ${result.message}`, 'success');
            fecharModal();
            await recarregarElenco();
        } else {
            mostrarToast(`❌ ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Erro ao adicionar jogador:', error);
        mostrarToast('❌ Erro ao adicionar jogador', 'error');
    }
}

async function removerJogador(nome, time) {
    try {
        const response = await fetch('/api/elenco/jogador', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ nome, time })
        });
        
        const result = await response.json();
        
        if (result.success) {
            mostrarToast(`✅ ${result.message}`, 'success');
            await recarregarElenco();
        } else {
            mostrarToast(`❌ ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Erro ao remover jogador:', error);
        mostrarToast('❌ Erro ao remover jogador', 'error');
    }
}

async function moverJogador(nome, timeOrigem, timeDestino) {
    const emojiOrigem = timeOrigem === 'azul' ? '●' : '○';
    const emojiDestino = timeDestino === 'azul' ? '●' : '○';
    const nomeTimeDestino = timeDestino === 'azul' ? '1' : '2';
    
    const confirmar = confirm(
        `${emojiOrigem} → ${emojiDestino} Mover "${nome}" para Time ${nomeTimeDestino}?`
    );
    
    if (!confirmar) return;
    
    try {
        const response = await fetch('/api/elenco/jogador/mover', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                nome,
                time_origem: timeOrigem,
                time_destino: timeDestino
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            mostrarToast(`✅ ${result.message}`, 'success');
            await recarregarElenco();
        } else {
            mostrarToast(`❌ ${result.error}`, 'error');
        }
    } catch (error) {
        console.error('Erro ao mover jogador:', error);
        mostrarToast('❌ Erro ao mover jogador', 'error');
    }
}

function confirmarRemover(nome, time) {
    const emoji = time === 'azul' ? '●' : '○';
    const nomeTime = time === 'azul' ? '1' : '2';
    
    const confirmar = confirm(
        `🗑️ Remover "${nome}" do Time ${nomeTime}?\n\n` +
        `⚠️ Esta ação não pode ser desfeita!`
    );
    
    if (confirmar) {
        removerJogador(nome, time);
    }
}

// ============================================
// RECARREGAR ELENCO
// ============================================

async function recarregarElenco() {
    try {
        const response = await fetch('/api/elenco/jogadores');
        const result = await response.json();
        
        if (result.success) {
            atualizarListaJogadores('azul', result.time_azul);
            atualizarListaJogadores('preto', result.time_preto);
            atualizarEstatisticas(result.time_azul.length, result.time_preto.length);
        }
    } catch (error) {
        console.error('Erro ao recarregar elenco:', error);
        mostrarToast('❌ Erro ao recarregar elenco', 'error');
    }
}

function atualizarListaJogadores(time, jogadores) {
    const lista = document.getElementById(`list-${time}`);
    
    if (!lista) return;
    
    // Limpa a lista
    lista.innerHTML = '';
    
    // Adiciona cada jogador
    jogadores.forEach(nome => {
        const card = criarCardJogador(nome, time);
        lista.appendChild(card);
    });
    
    // Se vazio, mostra mensagem
    if (jogadores.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.style.padding = '2rem';
        empty.style.textAlign = 'center';
        empty.style.color = 'var(--color-text-muted)';
        empty.innerHTML = `
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">👤</div>
            <div>Nenhum jogador cadastrado</div>
        `;
        lista.appendChild(empty);
    }
}

function criarCardJogador(nome, time) {
    const card = document.createElement('div');
    card.className = 'player-card';
    card.setAttribute('data-nome', nome);
    card.setAttribute('data-time', time);
    
    const timeOposto = time === 'azul' ? 'preto' : 'azul';
    const setaMove = time === 'azul' ? '➡️' : '⬅️';
    
    card.innerHTML = `
        <div class="player-info">
            <div class="player-avatar">${nome[0]}</div>
            <div class="player-name">${nome}</div>
        </div>
        <div class="player-actions">
            <button class="btn-icon btn-move" onclick="moverJogador('${nome}', '${time}', '${timeOposto}')" title="Mover para outro time">
                <span>${setaMove}</span>
            </button>
            <button class="btn-icon btn-delete" onclick="confirmarRemover('${nome}', '${time}')" title="Remover">
                <span>🗑️</span>
            </button>
        </div>
    `;
    
    return card;
}

function atualizarEstatisticas(totalAzul, totalPreto) {
    const statAzul = document.getElementById('stat-azul');
    const statPreto = document.getElementById('stat-preto');
    const statTotal = document.getElementById('stat-total');
    
    if (statAzul) statAzul.textContent = totalAzul;
    if (statPreto) statPreto.textContent = totalPreto;
    if (statTotal) statTotal.textContent = totalAzul + totalPreto;
}

// ============================================
// TOAST (NOTIFICAÇÕES)
// ============================================

function mostrarToast(mensagem, tipo = 'info') {
    const toast = document.getElementById('toast');
    
    toast.textContent = mensagem;
    toast.className = `toast ${tipo}`;
    
    // Mostra o toast
    setTimeout(() => {
        toast.classList.add('show');
    }, 100);
    
    // Esconde após 3 segundos
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// ============================================
// ATALHOS DE TECLADO
// ============================================

document.addEventListener('keydown', (e) => {
    // ESC fecha modal
    if (e.key === 'Escape') {
        fecharModal();
    }
});
