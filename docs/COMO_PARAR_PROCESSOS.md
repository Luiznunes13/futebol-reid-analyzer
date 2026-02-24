# Guia: Como Parar Processos - Sistema Terça Nobre

**Data:** 14 de fevereiro de 2026  
**Problema corrigido:** Processos não encerravam (script.py, etc.)

---

## ❌ Problema Original

Quando você executava "Capturar Imagens" (script.py):
- ❌ Processava vídeo inteiro sem poder cancelar
- ❌ Consumia 400%+ CPU indefinidamente 
- ❌ Não respondia a tentativas de cancelamento
- ❌ Janela CV2 ficava aguardando 'q' que nunca vinha (via web)

---

## ✅ Solução Implementada

### 1. script.py Agora é Interrompível

**Adicionado:**
```python
# Signal handlers para Ctrl+C e SIGTERM
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Flag de parada global
STOP_FLAG = False

# Verificação a cada 30 frames (~1 segundo)
if frame_count % 30 == 0:
    check_stop_flag()
    if STOP_FLAG:
        break
```

**Benefícios:**
- ✅ Responde a Ctrl+C instantaneamente
- ✅ Verifica arquivo `.stop_script` a cada segundo
- ✅ Pode ser morto pelo sistema de gerenciamento

---

### 2. Modo Headless (Sem Janela)

**Quando executado via API:**
```python
HEADLESS_MODE = '--headless' in sys.argv or os.environ.get('HEADLESS', '0') == '1'

if not HEADLESS_MODE:
    cv2.imshow("Video", frame)  # Só mostra se tiver interface
```

**Benefícios:**
- ✅ Não trava aguardando janela que nunca abre
- ✅ Executa em background perfeitamente
- ✅ Mostra progresso no terminal: `Progresso: 1500/5000 frames (30%)`

---

### 3. Timeouts Inteligentes

| Tipo de Script | Timeout | Motivo |
|----------------|---------|--------|
| Scripts rápidos | 10 min | Análises estatísticas |
| Processamento de vídeo | 1 hora | script.py, reconhecimento |
| Treinamento | 2 horas | treinar_reid_model.py |

**Implementação:**
```python
if script_name in ['script.py', 'reconhecer_por_time.py']:
    timeout = 3600  # 1 hora
elif script_name == 'treinar_reid_model.py':
    timeout = 7200  # 2 horas
```

---

### 4. Sistema de Controle Unificado

**Executor rastreia todos os processos:**
```python
# Dicionário de processos ativos
self.active_processes: Dict[str, subprocess.Popen] = {}

# Verificação antes de executar
if script_name in self.active_processes:
    return "Erro: Script já está em execução!"
```

---

## 🎯 Como Usar Corretamente

### Via Dashboard (Recomendado)

**1. Executar Script:**
- Clicar no botão "Capturar Imagens"
- Modal aparece mostrando progresso
- Se já estiver rodando, oferece cancelar o anterior

**2. Cancelar Durante Execução:**
- Botão "❌ Cancelar" aparece no modal
- Clique para interromper imediatamente
- Processo é finalizado graciosamente

**3. Emergência - Matar Todos:**
```javascript
// No console do browser:
fetch('/api/processos/matar-todos', {method: 'POST'})
  .then(r => r.json())
  .then(data => console.log(data.message))
```

---

### Via Terminal

**Executar com possibilidade de cancelar:**
```bash
# Com Ctrl+C funciona agora
python scripts/script.py
# Pressione Ctrl+C para parar

# Ou em modo headless explícito
python scripts/script.py --headless
```

**Cancelar de outro terminal:**
```bash
# Cria flag de parada
touch .stop_script

# O script detecta em ~1 segundo e para
```

**Matar processo específico:**
```bash
# Via API
curl -X POST http://localhost:5001/api/processos/matar \
  -H "Content-Type: application/json" \
  -d '{"script":"script.py"}'

# Via sistema
ps aux | grep script.py
kill -15 <PID>  # Graceful (recomendado)
kill -9 <PID>   # Forçado (emergência)
```

**Emergência - Matar TUDO:**
```bash
# Via API
curl -X POST http://localhost:5001/api/processos/matar-todos

# Via sistema
pkill -9 -f "python.*scripts/"
```

---

### Via Python

```python
from api.executor import ScriptExecutor

executor = ScriptExecutor()

# Listar processos ativos
processos = executor.get_active_processes()
for p in processos:
    print(f"{p['script']}: PID {p['pid']}, rodando={p['running']}")

# Matar específico
executor.kill_process('script.py')

# Matar todos (emergência)
count = executor.kill_all_processes()
print(f"{count} processos encerrados")
```

---

## 📊 Indicadores de Progresso

### No Dashboard:
```
Modal mostra:
🚀 Executando script.py
⏳ Capturando imagens dos vídeos...
[Spinner animado]
❌ Cancelar  [Fechar]
```

### No Terminal:
```
Iniciando processamento...
✓ Modo sem janela (headless)
✓ Salvando todas as imagens
✓ Total de frames: 5000

Progresso: 1500/5000 frames (30.0%)

✅ Processamento finalizado!
Frames processados: 5000/5000
Imagens salvas em: jogadores_terca/
```

---

## 🔍 Diagnóstico de Problemas

### Processo não está parando?

**1. Verificar se está realmente rodando:**
```bash
ps aux | grep script.py | grep -v grep
```

**2. Verificar qual versão:**
```bash
# Deve ter signal handlers
head -30 scripts/script.py | grep signal
```

**3. Tentar parada graceful:**
```bash
# Via flag
touch .stop_script
sleep 2
ls .stop_script  # Deve ter sumido

# Via signal
kill -15 <PID>
```

**4. Último recurso:**
```bash
kill -9 <PID>
```

---

### Script não executa via web?

**Verificar:**
```bash
# 1. Servidor Flask rodando?
curl http://localhost:5001/api/status

# 2. Processos ativos?
curl http://localhost:5001/api/processos

# 3. Logs do Flask
# (ver terminal onde Flask está rodando)
```

---

## ✅ Checklist de Garantia

Antes de executar processamento pesado:

- [ ] Verificar se já não está rodando: `GET /api/processos`
- [ ] Confirmar timeout adequado (script pesado = 1h+)
- [ ] Dashboard aberto para acompanhar progresso
- [ ] Saber como cancelar se necessário

Durante execução:

- [ ] Monitor progresso no modal ou terminal
- [ ] CPU/memória em níveis aceitáveis
- [ ] Botão "Cancelar" visível e funcional

Após execução:

- [ ] Processo removido da lista: `GET /api/processos`
- [ ] Recursos liberados (CPU/memória baixas)
- [ ] Resultados salvos corretamente

---

## 🎓 Boas Práticas

**✅ SEMPRE:**
- Execute scripts pesados pelo dashboard (controle visual)
- Use Ctrl+C para parar scripts no terminal
- Verifique processos ativos antes de executar novamente
- Monitore progresso durante execução longa

**❌ NUNCA:**
- Feche terminal com Ctrl+Z (pausa mas não mata)
- Execute mesmo script 2x simultaneamente
- Ignore aviso "já está em execução"
- Force kill (-9) sem tentar graceful (-15) antes

---

## 📈 Melhorias Futuras (FASE 2)

- [ ] Progresso em tempo real (WebSocket)
- [ ] ETA (tempo restante estimado)
- [ ] Histórico de execuções
- [ ] Logs persistentes
- [ ] Notificação quando terminar

---

**Status:** ✅ IMPLEMENTADO E TESTADO  
**Última atualização:** 14/02/2026  
**Arquivos modificados:**
- scripts/script.py (signal handlers + headless)
- api/executor.py (timeouts específicos + env vars)
- app_times.py (rotas de gerenciamento)
- static/js/dashboard.js (botão cancelar)
