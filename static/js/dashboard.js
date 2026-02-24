// ============================================
// GERENCIAMENTO DE PROCESSOS
// ============================================

async function listarProcessos() {
    try {
        const response = await fetch('/api/processos');
        const data = await response.json();
        
        if (data.success) {
            return data.processes;
        }
        return [];
    } catch (error) {
        console.error('Erro ao listar processos:', error);
        return [];
    }
}

async function matarProcesso(scriptName) {
    try {
        const response = await fetch('/api/processos/matar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                script: scriptName
            })
        });
        
        const result = await response.json();
        return result.success;
    } catch (error) {
        console.error('Erro ao matar processo:', error);
        return false;
    }
}

async function matarTodosProcessos() {
    if (!confirm('⚠️ Encerrar TODOS os processos em execução?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/processos/matar-todos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(`✅ ${result.count} processo(s) encerrado(s)`);
        } else {
            alert('❌ Erro ao encerrar processos');
        }
    } catch (error) {
        alert('❌ Erro de comunicação: ' + error.message);
    }
}

// ============================================
// GERENCIAMENTO DO MODAL
// ============================================

function abrirModal(titulo, status) {
    const modal = document.getElementById('executionModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalStatus = document.getElementById('modalStatus');
    const outputContainer = document.getElementById('modalOutput');
    
    // Configura o modal
    modalTitle.textContent = titulo;
    modalStatus.textContent = status;
    outputContainer.textContent = '';
    outputContainer.classList.remove('active');
    
    // Mostra o spinner
    document.querySelector('.progress-container').style.display = 'block';
    
    // Abre o modal
    modal.classList.add('active');
}

function fecharModal() {
    const modal = document.getElementById('executionModal');
    modal.classList.remove('active');
}

function atualizarModal(status, output = null, hideSpinner = false) {
    const modalStatus = document.getElementById('modalStatus');
    const outputContainer = document.getElementById('modalOutput');
    const progressContainer = document.querySelector('.progress-container');
    
    modalStatus.textContent = status;
    
    if (hideSpinner) {
        progressContainer.style.display = 'none';
    }
    
    if (output) {
        outputContainer.textContent = output;
        outputContainer.classList.add('active');
    }
}

// Fecha modal ao clicar fora
window.onclick = function(event) {
    const modal = document.getElementById('executionModal');
    if (event.target === modal) {
        fecharModal();
    }
}

// ============================================
// EXECUÇÃO DE SCRIPTS
// ============================================

let scriptAtual = null;
let executandoScript = false; // Lock para prevenir cliques múltiplos

async function executarScript(scriptName) {
    // PROTEÇÃO 1: Bloqueia se já está iniciando
    if (executandoScript) {
        alert('⚠️ Aguarde! Um script já está sendo iniciado...');
        return;
    }
    
    const scriptsInfo = {
        'script.py': 'Capturando imagens dos vídeos...',
        'setup_times.py': 'Configurando times...',
        'exportar_reid.py': 'Exportando dataset para ReID...',
        'treinar_reid_model.py': 'Treinando modelo ReID...',
        'reconhecer_por_time.py': 'Reconhecendo jogadores (histograma)...',
        'reconhecer_com_reid.py': 'Reconhecendo jogadores (ReID)...',
        'analisar_trajetoria.py': 'Analisando trajetórias...',
        'sincronizar_cameras.py': 'Sincronizando câmeras...',
        'analisar_balanceamento.py': 'Analisando balanceamento...'
    };
    
    // Ativa o lock
    executandoScript = true;
    
    // PROTEÇÃO 2: Verifica se já está executando
    const processos = await listarProcessos();
    const jaExecutando = processos.find(p => p.script === scriptName && p.running);
    
    if (jaExecutando) {
        executandoScript = false; // Libera o lock
        
        const cancelar = confirm(
            `⚠️ O script "${scriptName}" já está em execução!\n\n` +
            `PID: ${jaExecutando.pid}\n\n` +
            `Deseja cancelar a execução atual?`
        );
        
        if (cancelar) {
            const sucesso = await matarProcesso(scriptName);
            if (sucesso) {
                alert('✅ Processo cancelado com sucesso!');
            } else {
                alert('❌ Erro ao cancelar processo');
            }
        }
        return;
    }
    
    const titulo = `🚀 Executando ${scriptName}`;
    const status = scriptsInfo[scriptName] || 'Executando script...';
    
    scriptAtual = scriptName;
    abrirModal(titulo, status);
    
    // Adiciona botão de cancelar
    const modalFooter = document.querySelector('.modal-footer');
    const btnCancelar = document.createElement('button');
    btnCancelar.className = 'btn btn-danger';
    btnCancelar.textContent = '❌ Cancelar';
    btnCancelar.onclick = async () => {
        if (confirm('⚠️ Cancelar execução?')) {
            await matarProcesso(scriptAtual);
            fecharModal();
        }
    };
    modalFooter.insertBefore(btnCancelar, modalFooter.firstChild);
    
    try {
        const response = await fetch('/api/executar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                script: scriptName
            })
        });
        
        const result = await response.json();
        
        // Remove botão de cancelar
        btnCancelar.remove();
        
        if (result.success) {
            if (result.background) {
                // Script longo rodando em background
                atualizarModal(
                    `⏳ Script iniciado em background (PID: ${result.pid})`,
                    `O script está rodando em segundo plano.\nAcompanhe o progresso pelo terminal ou aguarde a conclusão.\n\n${result.message}`,
                    true
                );
            } else {
                // Script síncrono — mostra saída completa
                atualizarModal(
                    '✅ Script executado com sucesso!',
                    result.output || '(sem saída)',
                    true
                );
            }
        } else {
            atualizarModal(
                '❌ Erro ao executar script',
                result.error || 'Erro desconhecido',
                true
            );
        }
    } catch (error) {
        btnCancelar.remove();
        atualizarModal(
            '❌ Erro de comunicação',
            `Erro: ${error.message}`,
            true
        );
    } finally {
        scriptAtual = null;
        executandoScript = false; // Libera o lock sempre
    }
}

// ============================================
// ATUALIZAÇÃO DE STATUS
// ============================================

async function atualizarStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        // Atualiza os cards de status se existirem
        const elements = {
            'total_images': data.total_images,
            'total_classified': data.total_classified,
            'total_players': data.total_players,
            'model_status': data.model_status
        };
        
        // Atualiza cada elemento (se existir na página)
        for (const [key, value] of Object.entries(elements)) {
            const element = document.querySelector(`.status-value[data-status="${key}"]`);
            if (element && value !== undefined) {
                element.textContent = value;
            }
        }
    } catch (error) {
        console.error('Erro ao atualizar status:', error);
    }
}

// ============================================
// INICIALIZAÇÃO
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard carregado!');
    
    // Atualiza status inicial
    // atualizarStatus();
    
    // Atualiza status a cada 30 segundos (descomente se necessário)
    // setInterval(atualizarStatus, 30000);
});

// ============================================
// KEYBOARD SHORTCUTS
// ============================================

document.addEventListener('keydown', function(e) {
    // ESC fecha o modal
    if (e.key === 'Escape') {
        fecharModal();
    }
});
