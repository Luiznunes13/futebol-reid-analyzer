from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
import json
import os
import subprocess
import re
import time
import tempfile
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from api.executor import ScriptExecutor

app = Flask(__name__)

# Inicializar executor de scripts
executor = ScriptExecutor()

# Carregar configuração de times
if os.path.exists('times.json'):
    with open('times.json', 'r', encoding='utf-8') as f:
        TIMES = json.load(f)
else:
    print("\n⚠️  Arquivo times.json não encontrado!")
    print("   Execute primeiro: python setup_times.py\n")
    exit(1)

# Extrair lista de jogadores dos times
JOGADORES = TIMES.get('time_azul', []) + TIMES.get('time_preto', [])

IMG_DIR = Path('jogadores_terca')
VIDEOS_DIR = Path('videos')
VIDEOS_DIR.mkdir(exist_ok=True)

ATLETA_REFS_DIR = Path('atleta_refs')
ATLETA_REFS_DIR.mkdir(exist_ok=True)

HEATMAPS_DIR = Path('static/heatmaps')
HEATMAPS_DIR.mkdir(exist_ok=True)

ATLETA_STATE_FILE = HEATMAPS_DIR / '.atleta_state.json'

CAPTURA_LOG = Path('/tmp/captura_script.log')
HISTORICO_FILE = Path('historico_capturas.json')

# Estado global da captura em andamento
_captura_state: dict = {}

# Estado global da análise de atleta — carregado do disco se existir
def _carregar_estado_atleta() -> dict:
    try:
        if ATLETA_STATE_FILE.exists():
            return json.loads(ATLETA_STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}

def _salvar_estado_atleta():
    try:
        ATLETA_STATE_FILE.write_text(
            json.dumps(_atleta_state, ensure_ascii=False), encoding='utf-8'
        )
    except Exception:
        pass

_atleta_state: dict = _carregar_estado_atleta()
_captura_refs_state: dict = {}


def _recuperar_revisao_do_disco() -> dict:
    """Ao iniciar o Flask, verifica se existe .revisao/ com candidatos salvos e reconstrói o estado."""
    import base64 as _b64
    import re as _re
    for atleta_dir in ATLETA_REFS_DIR.iterdir():
        if not atleta_dir.is_dir():
            continue
        revisao_dir = atleta_dir / '.revisao'
        if not revisao_dir.exists():
            continue
        arquivos = sorted(revisao_dir.glob('cand_*.jpg'))
        if not arquivos:
            continue
        candidatos = []
        for arq in arquivos:
            try:
                crop = cv2.imread(str(arq))
                if crop is None:
                    continue
                # Extrair ts e sim do nome: cand_NNN_tsXX_simY.YY.jpg
                m = _re.search(r'_ts(\d+)_sim(\d+\.\d+)', arq.name)
                ts_val  = int(m.group(1))  if m else 0
                sim_val = float(m.group(2)) if m else 0.0
                thumb   = cv2.resize(crop, (64, 96))
                _, buf  = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
                b64     = _b64.b64encode(buf).decode()
                try:
                    cores = _detectar_cores_crop(crop)
                except Exception:
                    cores = {}
                candidatos.append({
                    'idx':     len(candidatos) + 1,
                    'ts':      ts_val,
                    'sim':     sim_val,
                    'arquivo': arq.name,
                    'b64':     b64,
                    'cores':   cores,
                })
            except Exception:
                continue
        if candidatos:
            return {
                'status':     'aguardando_revisao',
                'progresso':  100,
                'candidatos': candidatos,
                'salvos':     len(candidatos),
                'nome':       atleta_dir.name,
            }
    return {}


_captura_refs_state = {}


# Obter IDs únicos
ids_dict = defaultdict(list)
for img_path in IMG_DIR.glob('*.jpg'):
    id_num = img_path.stem.split('_id_')[1]
    ids_dict[id_num].append(img_path.name)

IDS_SORTED = sorted(ids_dict.keys(), key=int)

# Carregar classificações existentes
CLASSIFICACOES_FILE = 'jogadores_com_ids.json'
if os.path.exists(CLASSIFICACOES_FILE):
    with open(CLASSIFICACOES_FILE, 'r', encoding='utf-8') as f:
        classificacoes = json.load(f)
else:
    classificacoes = {}

@app.route('/')
def dashboard():
    """Página principal do dashboard."""
    # Estatísticas do sistema
    total_images = len(list(IMG_DIR.glob('*.jpg')))
    total_classified = len(classificacoes)
    total_players = len(JOGADORES)
    
    # Verifica se existe modelo ReID treinado
    model_path = Path('modelo_reid_terca.pth')
    model_status = '✅ Treinado' if model_path.exists() else '❌ Não treinado'
    
    return render_template('dashboard.html',
                         total_images=total_images,
                         total_classified=total_classified,
                         total_players=total_players,
                         model_status=model_status)

@app.route('/elenco')
def elenco():
    """Página de gerenciamento de elenco."""
    return render_template('elenco.html',
                         time_azul=TIMES['time_azul'],
                         time_preto=TIMES['time_preto'])

@app.route('/classificar')
def classificar_times():
    """Interface de classificação de jogadores."""
    ids_data = []
    for id_num in IDS_SORTED:
        ids_data.append({
            'id': id_num,
            'imgs': ids_dict[id_num],
            'nome': classificacoes.get(id_num, '')
        })
    
    # Estatísticas por time
    stats_azul = sum(1 for nome in classificacoes.values() if nome in TIMES['time_azul'])
    stats_preto = sum(1 for nome in classificacoes.values() if nome in TIMES['time_preto'])
    stats_descartados = sum(1 for nome in classificacoes.values() if nome == 'DESCARTADO')
    # Conta arquivos fisicamente na pasta _descartados
    descartados_dir = IMG_DIR / '_descartados'
    stats_descartados_files = len(list(descartados_dir.glob('*'))) if descartados_dir.exists() else 0

    return render_template('classificar_times.html',
                         ids_data=ids_data,
                         time_azul=TIMES['time_azul'],
                         time_preto=TIMES['time_preto'],
                         total=len(IDS_SORTED),
                         classificados=len(classificacoes),
                         stats_azul=stats_azul,
                         stats_preto=stats_preto,
                         stats_descartados=stats_descartados,
                         stats_descartados_files=stats_descartados_files)

@app.route('/salvar', methods=['POST'])
def salvar():
    global classificacoes
    data = request.json
    id_num = data['id']
    nome = data['nome']

    if nome:
        classificacoes[id_num] = nome
    elif id_num in classificacoes:
        del classificacoes[id_num]

    with open(CLASSIFICACOES_FILE, 'w', encoding='utf-8') as f:
        json.dump(classificacoes, f, ensure_ascii=False, indent=4)

    # Mover arquivos para pasta de descartados
    moved = 0
    if nome == 'DESCARTADO':
        descartados_dir = IMG_DIR / '_descartados'
        descartados_dir.mkdir(exist_ok=True)
        for img in IMG_DIR.glob(f'*_id_{id_num}.*'):
            img.rename(descartados_dir / img.name)
            moved += 1

    return jsonify({'success': True, 'total': len(classificacoes), 'moved': moved})


@app.route('/api/descartados/limpar', methods=['POST'])
def limpar_descartados():
    global classificacoes
    descartados_dir = IMG_DIR / '_descartados'
    count = 0
    if descartados_dir.exists():
        for f in descartados_dir.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
        try:
            descartados_dir.rmdir()
        except OSError:
            pass
    # Remove entradas DESCARTADO das classificacoes salvas
    classificacoes = {k: v for k, v in classificacoes.items() if v != 'DESCARTADO'}
    with open(CLASSIFICACOES_FILE, 'w', encoding='utf-8') as f:
        json.dump(classificacoes, f, ensure_ascii=False, indent=4)
    return jsonify({'success': True, 'deletados': count})

@app.route('/reset', methods=['POST'])
def reset():
    global classificacoes
    classificacoes = {}
    
    with open(CLASSIFICACOES_FILE, 'w', encoding='utf-8') as f:
        json.dump(classificacoes, f, ensure_ascii=False, indent=4)
    
    return jsonify({'success': True, 'message': 'Todas as classificações foram resetadas'})

@app.route('/jogadores_terca/<filename>')
def serve_image(filename):
    return send_from_directory('jogadores_terca', filename)

@app.route('/api/executar', methods=['POST'])
def executar_script():
    """Executa um script Python via API."""
    try:
        data = request.json
        script_name = data.get('script')
        background = data.get('background', False)  # Por padrão, aguarda saída (scripts rápidos)
        
        if not script_name:
            return jsonify({'success': False, 'error': 'Nome do script não fornecido'}), 400
        
        # Scripts longos SEMPRE em background (processam vídeo ou treinam modelo)
        long_running_scripts = [
            'script.py',
            'reconhecer_por_time.py',
            'reconhecer_com_reid.py',
            'treinar_reid_model.py',
            'analisar_trajetoria.py',  # processa frames de vídeo com YOLO
            'exportar_reid.py',        # copia ~1500 imagens
        ]
        if script_name in long_running_scripts:
            background = True
        
        if background:
            # Executa em background e retorna imediatamente
            process = executor.execute_script_async(script_name)
            
            return jsonify({
                'success': True,
                'message': f'Script {script_name} iniciado em background',
                'script': script_name,
                'pid': process.pid,
                'background': True
            })
        else:
            # Executa e aguarda (scripts rápidos)
            exit_code, stdout, stderr = executor.execute_script(script_name, timeout=60)
            
            if exit_code == 0:
                return jsonify({
                    'success': True,
                    'output': stdout,
                    'script': script_name,
                    'background': False
                })
            else:
                return jsonify({
                    'success': False,
                    'error': stderr or 'Erro desconhecido',
                    'output': stdout,
                    'exit_code': exit_code
                }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Retorna estatísticas do sistema."""
    try:
        total_images = len(list(IMG_DIR.glob('*.jpg')))
        total_classified = len(classificacoes)
        total_players = len(JOGADORES)
        
        # Verifica modelo ReID
        model_path = Path('modelo_reid_terca.pth')
        model_status = '✅ Treinado' if model_path.exists() else '❌ Não treinado'
        
        # Scripts disponíveis
        scripts = executor.list_available_scripts()
        
        # Processos ativos
        active_processes = executor.get_active_processes()
        
        return jsonify({
            'success': True,
            'total_images': total_images,
            'total_classified': total_classified,
            'total_players': total_players,
            'model_status': model_status,
            'scripts': scripts,
            'active_processes': len(active_processes)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/processos', methods=['GET'])
def listar_processos():
    """Lista processos ativos."""
    try:
        processes = executor.get_active_processes()
        return jsonify({
            'success': True,
            'processes': processes,
            'count': len(processes)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/processos/matar', methods=['POST'])
def matar_processo():
    """Mata um processo específico."""
    try:
        data = request.json
        script_name = data.get('script')
        
        if not script_name:
            return jsonify({
                'success': False,
                'error': 'Nome do script não fornecido'
            }), 400
        
        success = executor.kill_process(script_name)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Processo {script_name} encerrado'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Processo {script_name} não encontrado ou não pôde ser encerrado'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/processos/matar-todos', methods=['POST'])
def matar_todos_processos():
    """Mata todos os processos ativos."""
    try:
        count = executor.kill_all_processes()
        
        return jsonify({
            'success': True,
            'message': f'{count} processo(s) encerrado(s)',
            'count': count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/elenco/jogadores', methods=['GET'])
def listar_jogadores():
    """Lista todos os jogadores organizados por time."""
    return jsonify({
        'success': True,
        'time_azul': TIMES['time_azul'],
        'time_preto': TIMES['time_preto']
    })

@app.route('/api/elenco/jogador', methods=['POST'])
def adicionar_jogador():
    """Adiciona um jogador a um time."""
    try:
        data = request.json
        nome = data.get('nome', '').strip()
        time = data.get('time')  # 'azul' ou 'preto'
        
        if not nome:
            return jsonify({'success': False, 'error': 'Nome do jogador é obrigatório'}), 400
        
        if time not in ['azul', 'preto']:
            return jsonify({'success': False, 'error': 'Time inválido'}), 400
        
        # Verifica se jogador já existe em algum time
        if nome in TIMES['time_azul'] or nome in TIMES['time_preto']:
            return jsonify({'success': False, 'error': 'Jogador já existe'}), 400
        
        # Adiciona ao time
        time_key = f'time_{time}'
        TIMES[time_key].append(nome)
        
        # Salva no arquivo
        with open('times.json', 'w', encoding='utf-8') as f:
            json.dump(TIMES, f, ensure_ascii=False, indent=4)
        
        # Atualiza lista global
        global JOGADORES
        JOGADORES = TIMES['time_azul'] + TIMES['time_preto']
        
        return jsonify({
            'success': True,
            'message': f'Jogador {nome} adicionado ao time {time}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/elenco/jogador', methods=['DELETE'])
def remover_jogador():
    """Remove um jogador de um time."""
    try:
        data = request.json
        nome = data.get('nome')
        time = data.get('time')  # 'azul' ou 'preto'
        
        if not nome or time not in ['azul', 'preto']:
            return jsonify({'success': False, 'error': 'Dados inválidos'}), 400
        
        time_key = f'time_{time}'
        
        if nome not in TIMES[time_key]:
            return jsonify({'success': False, 'error': 'Jogador não encontrado'}), 404
        
        # Remove do time
        TIMES[time_key].remove(nome)
        
        # Salva no arquivo
        with open('times.json', 'w', encoding='utf-8') as f:
            json.dump(TIMES, f, ensure_ascii=False, indent=4)
        
        # Atualiza lista global
        global JOGADORES
        JOGADORES = TIMES['time_azul'] + TIMES['time_preto']
        
        return jsonify({
            'success': True,
            'message': f'Jogador {nome} removido'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/elenco/jogador/mover', methods=['POST'])
def mover_jogador():
    """Move um jogador de um time para outro."""
    try:
        data = request.json
        nome = data.get('nome')
        time_origem = data.get('time_origem')  # 'azul' ou 'preto'
        time_destino = data.get('time_destino')  # 'azul' ou 'preto'
        
        if not nome or time_origem not in ['azul', 'preto'] or time_destino not in ['azul', 'preto']:
            return jsonify({'success': False, 'error': 'Dados inválidos'}), 400
        
        if time_origem == time_destino:
            return jsonify({'success': False, 'error': 'Times origem e destino são iguais'}), 400
        
        time_origem_key = f'time_{time_origem}'
        time_destino_key = f'time_{time_destino}'
        
        if nome not in TIMES[time_origem_key]:
            return jsonify({'success': False, 'error': 'Jogador não encontrado no time de origem'}), 404
        
        # Remove da origem e adiciona ao destino
        TIMES[time_origem_key].remove(nome)
        TIMES[time_destino_key].append(nome)
        
        # Salva no arquivo
        with open('times.json', 'w', encoding='utf-8') as f:
            json.dump(TIMES, f, ensure_ascii=False, indent=4)
        
        # Atualiza lista global
        global JOGADORES
        JOGADORES = TIMES['time_azul'] + TIMES['time_preto']
        
        return jsonify({
            'success': True,
            'message': f'Jogador {nome} movido para time {time_destino}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTAS DE VÍDEOS
# ============================================================

def _ytdlp_cmd(ios=False):
    """Retorna o comando base para yt-dlp usando o Python do ambiente.
    Usa cliente android que não requer PO Token nem cookies."""
    python = executor.get_python_command()[0]
    return [python, '-m', 'yt_dlp',
            '--extractor-args', 'youtube:player_client=android']

# Formato preferido: MP4 até 720p via cliente android
YT_FORMAT = 'best[height<=720][ext=mp4]/best[height<=720]/best'

def _is_youtube_url(url):
    return bool(re.match(r'https?://(www\.)?(youtube\.com|youtu\.be)/', url or ''))

@app.route('/captura')
def captura_page():
    """Página de captura de imagens."""
    return render_template('videos.html')

@app.route('/videos')
def videos_page_redirect():
    """Redireciona /videos para /captura (compat. com links antigos)."""
    from flask import redirect
    return redirect('/captura', code=301)

@app.route('/api/videos/info', methods=['POST'])
def api_videos_info():
    """Busca metadados de um vídeo do YouTube via yt-dlp."""
    try:
        url = request.json.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL não informada'}), 400

        result = subprocess.run(
            _ytdlp_cmd() + ['--dump-json', '--no-download', '--no-playlist',
                             '--quiet', '--no-warnings', url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            return jsonify({'success': False, 'error': result.stderr[:300] or 'Erro ao buscar vídeo'}), 400

        info = json.loads(result.stdout.splitlines()[0])
        return jsonify({
            'success': True,
            'title':     info.get('title', 'Sem título'),
            'duration':  info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'uploader':  info.get('uploader', ''),
            'view_count': info.get('view_count', 0),
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout ao buscar informações (20s)'}), 408
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/baixar', methods=['POST'])
def api_videos_baixar():
    """Baixa um vídeo do YouTube para a pasta videos/."""
    try:
        url   = request.json.get('url', '').strip()
        nome  = request.json.get('nome', '%(title)s').strip() or '%(title)s'
        if not url:
            return jsonify({'success': False, 'error': 'URL não informada'}), 400

        output_tmpl = str(VIDEOS_DIR / f'{nome}.%(ext)s')
        result = subprocess.run(
            _ytdlp_cmd() + [
                '-f', YT_FORMAT,
                '--no-playlist',
                '-o', output_tmpl,
                '--print', 'after_move:filepath',
                '--merge-output-format', 'mp4',
                url
            ],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            return jsonify({'success': False, 'error': result.stderr[:400]}), 400

        filepath = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ''
        return jsonify({'success': True, 'path': filepath, 'message': 'Download concluído'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout no download (10min)'}), 408
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/stream-url', methods=['POST'])
def api_videos_stream_url():
    """Valida que o vídeo é acessível e retorna a URL original do YouTube.
    O script.py usa StreamCapture (yt-dlp+ffmpeg pipe) internamente,
    então a URL passada ao script DEVE ser a URL original do YouTube.
    """
    try:
        url = request.json.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL não informada'}), 400

        # Valida que conseguimos obter metadados (confirma que o vídeo é acessível)
        result = subprocess.run(
            _ytdlp_cmd() + [
                '--dump-json', '--no-download', '--quiet', '--no-warnings', '--no-playlist', url
            ],
            capture_output=True, text=True, timeout=25
        )
        if result.returncode != 0:
            return jsonify({'success': False, 'error': result.stderr[:300] or 'Vídeo inacessível'}), 400

        # Retorna a URL ORIGINAL do YouTube (não a URL raw do googlevideo)
        # O StreamCapture em script.py usará yt-dlp para fazer o download/pipe
        return jsonify({'success': True, 'stream_url': url})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout ao validar vídeo (25s)'}), 408
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/lista', methods=['GET'])
def api_videos_lista():
    """Lista todos os vídeos disponíveis na pasta videos/."""
    try:
        videos = []
        extensions = ['*.mp4', '*.mkv', '*.avi', '*.mov', '*.webm']
        for ext in extensions:
            for f in sorted(VIDEOS_DIR.glob(ext)):
                videos.append({
                    'name': f.name,
                    'path': str(f),
                    'size_mb': round(f.stat().st_size / 1024 / 1024, 1)
                })
        return jsonify({'success': True, 'videos': videos})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/deletar', methods=['DELETE'])
def api_videos_deletar():
    """Remove um vídeo da pasta videos/."""
    try:
        nome = request.json.get('nome', '').strip()
        if not nome:
            return jsonify({'success': False, 'error': 'Nome não informado'}), 400
        filepath = VIDEOS_DIR / nome
        if not filepath.exists() or not str(filepath.resolve()).startswith(str(VIDEOS_DIR.resolve())):
            return jsonify({'success': False, 'error': 'Arquivo não encontrado'}), 404
        filepath.unlink()
        return jsonify({'success': True, 'message': f'{nome} removido'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/videos/parar', methods=['POST'])
def api_videos_parar():
    """Encerra o processo de captura em andamento."""
    if not _captura_state:
        return jsonify({'success': False, 'error': 'Nenhuma captura em andamento'}), 400
    proc = _captura_state.get('process')
    if proc is None or proc.poll() is not None:
        return jsonify({'success': False, 'error': 'Processo já encerrado'}), 400
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return jsonify({'success': True, 'message': 'Captura encerrada'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/videos/browse', methods=['GET'])
def api_videos_browse():
    """Abre diálogo nativo de seleção de arquivo (zenity) e retorna o caminho escolhido."""
    try:
        # Detecta o DISPLAY real (evita o :99 virtual do VS Code)
        env = os.environ.copy()
        for display in [':0', ':1', ':2']:
            test = subprocess.run(['xdpyinfo', '-display', display],
                                  capture_output=True, timeout=2)
            if test.returncode == 0:
                env['DISPLAY'] = display
                break

        result = subprocess.run(
            ['zenity', '--file-selection',
             '--title=Selecionar vídeo',
             '--file-filter=Vídeos | *.mp4 *.mkv *.avi *.mov *.webm',
             '--file-filter=Todos os arquivos | *'],
            capture_output=True, text=True, timeout=120, env=env
        )
        if result.returncode != 0:
            return jsonify({'success': False, 'error': 'Seleção cancelada'})
        path = result.stdout.strip()
        if not path or not os.path.exists(path):
            return jsonify({'success': False, 'error': 'Arquivo não encontrado'})
        return jsonify({'success': True, 'path': path, 'name': os.path.basename(path)})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout (2min)'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/videos/processar', methods=['POST'])
def api_videos_processar():
    """Inicia script.py com os vídeos selecionados, redirecionando saída para log."""
    try:
        data       = request.json
        video_esq  = data.get('video_esq', '').strip()
        video_dir  = data.get('video_dir', '').strip()
        model      = data.get('model', 'yolo11n.pt').strip()
        confidence = str(data.get('confidence', 0.5))
        output_dir = data.get('output_dir', 'jogadores_terca').strip() or 'jogadores_terca'

        if not video_esq and not video_dir:
            return jsonify({'success': False, 'error': 'Nenhum vídeo selecionado'}), 400

        # Limpa log anterior
        CAPTURA_LOG.write_text('')

        script_path = executor.scripts_dir / 'script.py'
        cmd = executor.get_python_command() + [str(script_path), '--headless']
        if video_esq:
            cmd += ['--video-esq', video_esq]
        if video_dir:
            cmd += ['--video-dir', video_dir]
        cmd += ['--model', model, '--confidence', confidence, '--output-dir', output_dir]

        log_file = open(CAPTURA_LOG, 'w', buffering=1)
        process = subprocess.Popen(
            cmd,
            cwd=str(executor.project_root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, 'HEADLESS': '1', 'PYTHONUNBUFFERED': '1'}
        )

        _captura_state.update({
            'pid':        process.pid,
            'process':    process,
            'log_file':   log_file,
            'started_at': datetime.now().isoformat(timespec='seconds'),
            'video_esq':  video_esq or '(padrão)',
            'video_dir':  video_dir or '(padrão)',
            'model':      model,
            'confidence': confidence,
            'output_dir': output_dir,
            'imgs_start': _count_imgs(),
            'historico_saved': False,
        })

        return jsonify({
            'success': True,
            'pid': process.pid,
            'message': 'Captura iniciada em background',
            'video_esq': video_esq or '(padrão)',
            'video_dir': video_dir or '(padrão)',
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _count_imgs():
    img_dir = executor.project_root / 'jogadores_terca'
    try:
        return sum(1 for _ in img_dir.glob('*.jpg'))
    except Exception:
        return 0


def _tail_log(n=40):
    try:
        text = CAPTURA_LOG.read_text(errors='replace')
        lines = [l for l in text.splitlines() if l.strip()]
        return lines[-n:]
    except Exception:
        return []


@app.route('/api/videos/status', methods=['GET'])
def api_videos_status():
    """Retorna status da captura em andamento: PID, imagens capturadas e últimas linhas do log."""
    if not _captura_state:
        return jsonify({'running': False, 'imgs_total': _count_imgs(), 'log': []})

    proc        = _captura_state.get('process')
    running     = proc is not None and proc.poll() is None
    imgs_total  = _count_imgs()
    imgs_new    = imgs_total - _captura_state.get('imgs_start', 0)
    log_lines   = _tail_log(40)

    # Salva histórico na primeira vez em que detecta que o processo terminou
    if not running and not _captura_state.get('historico_saved'):
        _salvar_historico(imgs_new, imgs_total)
        _captura_state['historico_saved'] = True

    return jsonify({
        'running':    running,
        'pid':        _captura_state.get('pid'),
        'started_at': _captura_state.get('started_at'),
        'video_esq':  _captura_state.get('video_esq'),
        'video_dir':  _captura_state.get('video_dir'),
        'imgs_total': imgs_total,
        'imgs_new':   imgs_new,
        'log':        log_lines,
    })


def _salvar_historico(imgs_new, imgs_total):
    """Salva entrada no histórico de capturas (JSON append)."""
    try:
        historico = []
        if HISTORICO_FILE.exists():
            historico = json.loads(HISTORICO_FILE.read_text(encoding='utf-8'))
        entrada = {
            'id':           len(historico) + 1,
            'data_inicio':  _captura_state.get('started_at', ''),
            'data_fim':     datetime.now().isoformat(timespec='seconds'),
            'video_esq':    _captura_state.get('video_esq', ''),
            'video_dir':    _captura_state.get('video_dir', ''),
            'model':        _captura_state.get('model', 'yolo11n.pt'),
            'confidence':   _captura_state.get('confidence', 0.5),
            'output_dir':   _captura_state.get('output_dir', 'jogadores_terca'),
            'imgs_novas':   max(0, imgs_new),
            'imgs_total':   imgs_total,
            'status':       'concluído',
        }
        historico.append(entrada)
        HISTORICO_FILE.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


@app.route('/api/videos/historico', methods=['GET'])
def api_videos_historico():
    """Retorna o histórico de execuções de captura."""
    try:
        if not HISTORICO_FILE.exists():
            return jsonify({'success': True, 'historico': []})
        historico = json.loads(HISTORICO_FILE.read_text(encoding='utf-8'))
        return jsonify({'success': True, 'historico': list(reversed(historico))})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─── ATLETA — reconhecimento individual + heatmap ─────────────────

@app.route('/atleta')
def atleta_page():
    """Página de análise de atleta específico."""
    videos = sorted([f.name for f in VIDEOS_DIR.glob('*.mp4')])
    return render_template('atleta.html', videos=videos)


@app.route('/api/atleta/fotos', methods=['POST'])
def atleta_upload_fotos():
    """Recebe fotos de referência e gera embedding L2-normalizado."""
    from scripts.analisar_atleta import gerar_embedding_referencia

    nome  = request.form.get('nome', '').strip()
    fotos = request.files.getlist('fotos')

    if not nome:
        return jsonify({'success': False, 'error': 'Nome do atleta é obrigatório'}), 400

    atleta_dir = ATLETA_REFS_DIR / nome
    atleta_dir.mkdir(exist_ok=True)

    caminhos = []
    for foto in fotos:
        if foto.filename:
            dest = atleta_dir / Path(foto.filename).name
            foto.save(str(dest))
            caminhos.append(str(dest))

    # Se nenhuma foto enviada, usar imagens já existentes (crops do extrator)
    if not caminhos:
        caminhos = [str(p) for p in sorted(atleta_dir.glob('*.jpg'))
                    if p.name != 'embedding.json']
        caminhos += [str(p) for p in sorted(atleta_dir.glob('*.png'))]

    if not caminhos:
        return jsonify({'success': False, 'error': 'Nenhuma foto disponível. Envie fotos ou use o extrator.'}), 400

    try:
        embedding = gerar_embedding_referencia(caminhos)
        emb_file  = atleta_dir / 'embedding.json'
        emb_file.write_text(
            json.dumps({'nome': nome, 'embedding': embedding}, ensure_ascii=False),
            encoding='utf-8'
        )
        return jsonify({'success': True, 'nome': nome, 'n_fotos': len(caminhos)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/atleta/frame', methods=['POST'])
def atleta_extrair_frame():
    """
    Extrai um frame de vídeo/URL num dado timestamp,
    roda YOLO e retorna o frame anotado (base64) + lista de bounding boxes.
    """
    import base64
    data  = request.get_json() or {}
    src   = data.get('src', '').strip()     # URL ou nome do arquivo em videos/
    ts    = float(data.get('ts', 0))        # timestamp em segundos

    if not src:
        return jsonify({'success': False, 'error': 'Fonte não informada'}), 400

    tmp_file = None
    try:
        if src.startswith('http'):
            # Obter URL direta do stream (sem fazer download)
            result = subprocess.run(
                ['yt-dlp', '--extractor-args', 'youtube:player_client=android',
                 '-f', 'best[height<=720][ext=mp4]/best[height<=720]/best',
                 '--get-url', src],
                capture_output=True, text=True, timeout=30
            )
            stream_url = result.stdout.strip().split('\n')[0]
            if not stream_url:
                return jsonify({'success': False,
                                'error': 'Não foi possível obter URL do vídeo. ' + result.stderr[-200:]}), 400
            video_path = stream_url
        else:
            video_path = str(VIDEOS_DIR / src)

        if not video_path:
            return jsonify({'success': False, 'error': 'Vídeo não encontrado'}), 400

        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ret, frame = cap.read()
        if not ret:
            # Tentar alguns frames à frente
            for extra in [500, 1000, 2000]:
                cap.set(cv2.CAP_PROP_POS_MSEC, (ts + extra/1000) * 1000)
                ret, frame = cap.read()
                if ret:
                    break
        cap.release()

        if not ret:
            return jsonify({'success': False, 'error': f'Frame no timestamp {ts}s não encontrado'}), 400

        from ultralytics import YOLO
        yolo  = YOLO('yolo11n.pt')
        h_fr, w_fr = frame.shape[:2]
        results = yolo(frame, classes=[0], verbose=False)[0]
        boxes   = []

        annotated = frame.copy()
        for i, box in enumerate(results.boxes):
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w_fr, x2), min(h_fr, y2)
            conf = float(box.conf[0])
            # caixa cinza com índice
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (100, 200, 100), 2)
            cv2.putText(annotated, str(i), (x1+4, y1+18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 220, 100), 2)
            boxes.append({'i': i, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'conf': round(conf, 2)})

        # Reduzir para 480px de altura
        scale = 480 / h_fr
        small = cv2.resize(annotated, (int(w_fr * scale), 480))
        _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode()

        # Escalar boxes para a imagem reduzida
        boxes_scaled = [{
            'i': b['i'],
            'x1': int(b['x1']*scale), 'y1': int(b['y1']*scale),
            'x2': int(b['x2']*scale), 'y2': int(b['y2']*scale),
        } for b in boxes]

        return jsonify({
            'success': True,
            'frame_b64': b64,
            'boxes': boxes_scaled,
            'boxes_orig': boxes,
            'w': int(w_fr * scale),
            'h': 480,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/atleta/crop', methods=['POST'])
def atleta_salvar_crop():
    """
    Salva o crop de uma bbox de um frame como foto de referência do atleta.
    Recebe: nome, src, ts, box {x1,y1,x2,y2} (coordenadas originais).
    """
    data  = request.get_json() or {}
    nome  = data.get('nome', '').strip()
    src   = data.get('src', '').strip()
    ts    = float(data.get('ts', 0))
    box   = data.get('box', {})

    if not nome or not src or not box:
        return jsonify({'success': False, 'error': 'Parâmetros incompletos'}), 400

    try:
        if src.startswith('http'):
            result = subprocess.run(
                ['yt-dlp', '--extractor-args', 'youtube:player_client=android',
                 '-f', 'best[height<=720][ext=mp4]/best[height<=720]/best',
                 '--get-url', src],
                capture_output=True, text=True, timeout=30
            )
            stream_url = result.stdout.strip().split('\n')[0]
            if not stream_url:
                return jsonify({'success': False, 'error': 'Não foi possível obter URL do stream'}), 400
            video_path = stream_url
        else:
            video_path = str(VIDEOS_DIR / src)

        if not video_path:
            return jsonify({'success': False, 'error': 'Vídeo não encontrado'}), 400

        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return jsonify({'success': False, 'error': 'Frame não encontrado'}), 400

        x1, y1 = max(0, box['x1']), max(0, box['y1'])
        x2, y2 = box['x2'], box['y2']
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return jsonify({'success': False, 'error': 'Crop vazio'}), 400

        atleta_dir = ATLETA_REFS_DIR / nome
        atleta_dir.mkdir(exist_ok=True)

        existing = list(atleta_dir.glob('crop_*.jpg'))
        idx = len(existing) + 1
        dest = atleta_dir / f'crop_{idx:03d}_ts{int(ts)}.jpg'
        cv2.imwrite(str(dest), crop)

        n_fotos = len(list(atleta_dir.glob('*.jpg'))) + len(list(atleta_dir.glob('*.png')))
        return jsonify({'success': True, 'salvo': dest.name, 'n_fotos': n_fotos})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


_COR_RANGES = {
    'azul':     [(np.array([100, 60, 50]),   np.array([130, 255, 255]))],
    'branco':   [(np.array([0, 0, 160]),     np.array([180, 40, 255]))],
    'vermelho': [(np.array([0, 120, 70]),    np.array([10, 255, 255])),
                 (np.array([170, 120, 70]),  np.array([180, 255, 255]))],
    'amarelo':  [(np.array([20, 100, 100]),  np.array([35, 255, 255]))],
    'verde':    [(np.array([40, 50, 50]),    np.array([80, 255, 255]))],
    'preto':    [(np.array([0, 0, 0]),       np.array([180, 255, 60]))],
    'roxo':     [(np.array([130, 50, 50]),   np.array([160, 255, 255]))],
    'laranja':  [(np.array([10, 100, 100]),  np.array([20, 255, 255]))],
}


def _detectar_cores_crop(crop_bgr, pct_min: float = 0.06):
    """Retorna dict {cor: pct} com todas as cores acima de pct_min."""
    hsv   = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    total = crop_bgr.shape[0] * crop_bgr.shape[1]
    if total == 0:
        return {}
    result = {}
    for cor, rng in _COR_RANGES.items():
        count = sum(int(cv2.countNonZero(cv2.inRange(hsv, lo, hi))) for lo, hi in rng)
        pct = count / total
        if pct >= pct_min:
            result[cor] = round(pct, 3)
    return result


def _tem_cor_uniforme(crop_bgr, cor: str, pct_min: float = 0.08) -> bool:
    """Retorna True se o crop tem >= pct_min de pixels na cor do uniforme."""
    if not cor or cor == 'nenhuma':
        return True
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    ranges = {
        'azul':     [(np.array([100, 60, 50]),   np.array([130, 255, 255]))],
        'branco':   [(np.array([0, 0, 160]),     np.array([180, 40, 255]))],
        'vermelho': [(np.array([0, 120, 70]),    np.array([10, 255, 255])),
                     (np.array([170, 120, 70]),  np.array([180, 255, 255]))],
        'amarelo':  [(np.array([20, 100, 100]),  np.array([35, 255, 255]))],
        'verde':    [(np.array([40, 50, 50]),    np.array([80, 255, 255]))],
        'preto':    [(np.array([0, 0, 0]),       np.array([180, 255, 60]))],
        'roxo':     [(np.array([130, 50, 50]),   np.array([160, 255, 255]))],
        'laranja':  [(np.array([10, 100, 100]),  np.array([20, 255, 255]))],
    }
    rng = ranges.get(cor, [])
    if not rng:
        return True
    total = crop_bgr.shape[0] * crop_bgr.shape[1]
    if total == 0:
        return False
    count = sum(int(cv2.countNonZero(cv2.inRange(hsv, lo, hi))) for lo, hi in rng)
    return (count / total) >= pct_min


@app.route('/api/atleta/capturar_refs', methods=['POST'])
def atleta_capturar_refs():
    """
    Varre o vídeo automaticamente, detecta pessoas via ReID e salva
    candidatos para revisão em .revisao/ . Filtra por cor de uniforme se informado.
    Roda em background thread; use /api/atleta/capturar_refs/status para acompanhar.
    Após varredura muda status para 'aguardando_revisao' com lista de candidatos (base64).
    """
    import threading, json as _json, base64 as _b64
    global _captura_refs_state

    data          = request.get_json() or {}
    nome          = data.get('nome', '').strip()
    src           = data.get('src', '').strip()
    threshold     = float(data.get('threshold', 0.65))
    max_crops     = int(data.get('max_crops', 50))
    step_s        = float(data.get('step_s', 8))
    cor_uniforme  = data.get('cor_uniforme', 'nenhuma').strip().lower()

    if not nome or not src:
        return jsonify({'success': False, 'error': 'Nome e fonte são obrigatórios'}), 400

    emb_file = ATLETA_REFS_DIR / nome / 'embedding.json'
    if not emb_file.exists():
        return jsonify({'success': False,
                        'error': f'Embedding não encontrado para "{nome}". Gere primeiro.'}), 400

    if _captura_refs_state.get('status') in ('rodando', 'iniciando'):
        return jsonify({'success': False, 'error': 'Captura já em andamento'}), 400

    _captura_refs_state = {'status': 'iniciando', 'progresso': 0,
                           'salvos': 0, 'avaliados': 0, 'nome': nome}

    def _run():
        global _captura_refs_state
        try:
            try:
                from scripts.acelerador import get_reid as _get_reid
                _reid = _get_reid()
                _emb_fn = lambda _m, crop: _reid.embedding(crop)
                model_emb = None
                print(f'[CAPTURA] ReID via OpenVINO {_reid.device}', flush=True)
            except Exception as _e:
                print(f'[CAPTURA] Acelerador indisponível ({_e}), usando PyTorch', flush=True)
                from scripts.analisar_atleta import _build_model, _embedding as _emb_fn
                model_emb = _build_model()
            from ultralytics import YOLO

            emb_data = _json.loads(emb_file.read_text())
            ref_emb  = np.array(emb_data['embedding'] if isinstance(emb_data, dict) else emb_data)

            if src.startswith('http'):
                result = subprocess.run(
                    ['yt-dlp', '--extractor-args', 'youtube:player_client=android',
                     '-f', 'best[height<=720][ext=mp4]/best[height<=720]/best',
                     '--get-url', src],
                    capture_output=True, text=True, timeout=40
                )
                video_path = result.stdout.strip().split('\n')[0]
                if not video_path:
                    raise ValueError('Não foi possível obter URL do stream. ' + result.stderr[-200:])
            else:
                video_path = str(VIDEOS_DIR / src)

            cap      = cv2.VideoCapture(video_path)
            fps      = cap.get(cv2.CAP_PROP_FPS) or 25
            total_fr = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            dur_s    = total_fr / fps
            step_fr  = max(1, int(step_s * fps))

            yolo       = YOLO('yolo11n.pt')

            atleta_dir  = ATLETA_REFS_DIR / nome
            atleta_dir.mkdir(exist_ok=True)
            revisao_dir = atleta_dir / '.revisao'
            # Limpar revisão anterior
            if revisao_dir.exists():
                for f in revisao_dir.iterdir():
                    f.unlink()
            revisao_dir.mkdir(exist_ok=True)

            candidatos  = []
            avaliados   = 0
            frame_pos   = 0
            idx         = 0

            _captura_refs_state.update({'status': 'rodando', 'duracao': round(dur_s)})

            while len(candidatos) < max_crops:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                if not ret:
                    break

                ts_atual = frame_pos / fps
                _captura_refs_state.update({
                    'progresso': min(99, int(ts_atual / dur_s * 100)),
                    'ts_atual':  round(ts_atual),
                    'salvos':    len(candidatos),
                    'avaliados': avaliados,
                })

                h_fr, w_fr = frame.shape[:2]
                results = yolo(frame, classes=[0], verbose=False)[0]

                for box in results.boxes:
                    if len(candidatos) >= max_crops:
                        break
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w_fr, x2), min(h_fr, y2)
                    crop = frame[y1:y2, x1:x2]
                    if crop.size == 0:
                        continue

                    # Filtro de cor antes do ReID (mais rápido)
                    if not _tem_cor_uniforme(crop, cor_uniforme):
                        avaliados += 1
                        continue

                    emb = _emb_fn(model_emb, crop)
                    sim = float(np.dot(emb, ref_emb))
                    avaliados += 1

                    if sim >= threshold:
                        idx += 1
                        arquivo = f'cand_{idx:03d}_ts{int(ts_atual)}_sim{sim:.2f}.jpg'
                        cv2.imwrite(str(revisao_dir / arquivo), crop)

                        # Thumbnail 64×96 para preview no browser
                        thumb = cv2.resize(crop, (64, 96))
                        _, buf = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        b64 = _b64.b64encode(buf).decode()

                        cores = _detectar_cores_crop(crop)
                        candidatos.append({
                            'idx':     idx,
                            'ts':      round(ts_atual),
                            'sim':     round(sim, 3),
                            'arquivo': arquivo,
                            'b64':     b64,
                            'cores':   cores,
                        })
                        _captura_refs_state['salvos'] = len(candidatos)

                frame_pos += step_fr

            cap.release()
            _captura_refs_state.update({
                'status':      'aguardando_revisao',
                'progresso':   100,
                'candidatos':  candidatos,
                'avaliados':   avaliados,
                'nome':        nome,
            })
        except Exception as e:
            _captura_refs_state.update({'status': 'erro', 'error': str(e)})

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'success': True})


@app.route('/api/atleta/capturar_refs/status', methods=['GET'])
def atleta_capturar_refs_status():
    return jsonify(_captura_refs_state)


@app.route('/api/atleta/capturar_refs/confirmar', methods=['POST'])
def atleta_capturar_refs_confirmar():
    """
    Recebe lista de arquivos confirmados, move da pasta .revisao/ para atleta_refs/{nome}/,
    descarta os rejeitados.
    """
    global _captura_refs_state
    data        = request.get_json() or {}
    nome        = data.get('nome', '').strip()
    confirmados = data.get('confirmados', [])   # lista de 'arquivo'

    if not nome:
        return jsonify({'success': False, 'error': 'Nome obrigatório'}), 400

    atleta_dir  = ATLETA_REFS_DIR / nome
    revisao_dir = atleta_dir / '.revisao'

    existing = len([f for f in atleta_dir.glob('crop_*.jpg')])
    salvos   = 0

    for arquivo in confirmados:
        src_path = revisao_dir / arquivo
        if src_path.exists():
            idx  = existing + salvos + 1
            dest = atleta_dir / f'crop_{idx:03d}_rev.jpg'
            src_path.rename(dest)
            salvos += 1

    # Limpar pasta de revisão
    if revisao_dir.exists():
        for f in revisao_dir.iterdir():
            try: f.unlink()
            except Exception: pass
        try: revisao_dir.rmdir()
        except Exception: pass

    n_total = len(list(atleta_dir.glob('*.jpg'))) + len(list(atleta_dir.glob('*.png')))
    _captura_refs_state = {}
    return jsonify({'success': True, 'salvos': salvos, 'n_total': n_total})
def atleta_testar_rastreamento():
    """
    Extrai um frame, roda YOLO + ReID e devolve o frame anotado:
    caixa âmbar = match acima do limiar, cinza = descartado.
    """
    import base64, json as _json
    data      = request.get_json() or {}
    nome      = data.get('nome', '').strip()
    src       = data.get('src', '').strip()
    ts        = float(data.get('ts', 0))
    threshold = float(data.get('threshold', 0.65))

    if not nome or not src:
        return jsonify({'success': False, 'error': 'Nome e fonte são obrigatórios'}), 400

    emb_file = ATLETA_REFS_DIR / nome / 'embedding.json'
    if not emb_file.exists():
        return jsonify({'success': False,
                        'error': f'Embedding não encontrado para "{nome}". Gere primeiro.'}), 400

    try:
        emb_data = _json.loads(emb_file.read_text())
        ref_emb = np.array(emb_data['embedding'] if isinstance(emb_data, dict) else emb_data)

        if src.startswith('http'):
            result = subprocess.run(
                ['yt-dlp', '--extractor-args', 'youtube:player_client=android',
                 '-f', 'best[height<=720][ext=mp4]/best[height<=720]/best',
                 '--get-url', src],
                capture_output=True, text=True, timeout=30
            )
            stream_url = result.stdout.strip().split('\n')[0]
            if not stream_url:
                return jsonify({'success': False,
                                'error': 'Não foi possível obter URL do vídeo. ' + result.stderr[-200:]}), 400
            video_path = stream_url
        else:
            video_path = str(VIDEOS_DIR / src)

        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ret, frame = cap.read()
        if not ret:
            for extra in [500, 1000, 2000]:
                cap.set(cv2.CAP_PROP_POS_MSEC, (ts + extra / 1000) * 1000)
                ret, frame = cap.read()
                if ret:
                    break
        cap.release()

        if not ret:
            return jsonify({'success': False,
                            'error': f'Frame no timestamp {ts}s não encontrado'}), 400

        from ultralytics import YOLO
        try:
            from scripts.acelerador import get_reid as _get_reid
            _reid     = _get_reid()
            _emb_fn   = lambda _m, crop: _reid.embedding(crop)
            model_emb = None
            print(f'[TESTAR] ReID via OpenVINO {_reid.device}', flush=True)
        except Exception as _e:
            print(f'[TESTAR] Acelerador indisponível ({_e}), usando PyTorch', flush=True)
            from scripts.analisar_atleta import _build_model, _embedding as _emb_fn
            model_emb = _build_model()

        yolo      = YOLO('yolo11n.pt')
        h_fr, w_fr = frame.shape[:2]
        results   = yolo(frame, classes=[0], verbose=False)[0]

        annotated = frame.copy()
        n_matches = 0

        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w_fr, x2), min(h_fr, y2)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            emb     = _emb_fn(model_emb, crop)
            sim     = float(np.dot(emb, ref_emb))
            matched = sim >= threshold

            if matched:
                color = (0, 165, 255)   # âmbar BGR
                thick = 3
                n_matches += 1
            else:
                color = (100, 100, 100)  # cinza
                thick = 1

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thick)
            cv2.putText(annotated, f'{sim:.2f}', (x1 + 3, y1 + 17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # HUD na parte inferior
        hud = f'Limiar: {threshold}  |  Matches: {n_matches}/{len(results.boxes)}  |  ts: {ts}s'
        cv2.rectangle(annotated, (0, h_fr - 28), (w_fr, h_fr), (0, 0, 0), -1)
        cv2.putText(annotated, hud, (10, h_fr - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 165, 255), 1)

        scale = 480 / h_fr
        small = cv2.resize(annotated, (int(w_fr * scale), 480))
        _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 82])
        b64 = base64.b64encode(buf).decode()

        return jsonify({
            'success': True,
            'frame_b64': b64,
            'w': int(w_fr * scale),
            'h': 480,
            'matches': n_matches,
            'total': len(results.boxes),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/atleta/analisar', methods=['POST'])
def atleta_analisar():
    """Inicia análise de vídeo em background thread."""
    import threading
    global _atleta_state

    data      = request.get_json() or {}
    nome      = data.get('nome', '').strip()
    video     = data.get('video', '').strip()
    threshold = float(data.get('threshold', 0.65))

    if not nome:
        return jsonify({'success': False, 'error': 'Nome do atleta é obrigatório'}), 400
    if not video:
        return jsonify({'success': False, 'error': 'Vídeo é obrigatório'}), 400

    emb_file = ATLETA_REFS_DIR / nome / 'embedding.json'
    if not emb_file.exists():
        return jsonify({
            'success': False,
            'error': f'Embedding de "{nome}" não encontrado. Envie as fotos primeiro.'
        }), 400

    is_url = video.startswith('http://') or video.startswith('https://')
    if is_url:
        video_path = video   # URL — será baixado na thread
    else:
        video_path = str(VIDEOS_DIR / video)
        if not os.path.exists(video_path):
            if os.path.exists(video):
                video_path = video
            else:
                return jsonify({'success': False, 'error': 'Vídeo não encontrado'}), 400

    if _atleta_state.get('status') == 'rodando':
        return jsonify({'success': False, 'error': 'Análise já em andamento'}), 400

    ref_data      = json.loads(emb_file.read_text(encoding='utf-8'))
    ref_embedding = ref_data['embedding']

    preview_path = f'/tmp/atleta_preview_{nome.replace(" ","_")}.jpg'
    _atleta_state = {
        'status': 'iniciando', 'progresso': 0,
        'matches': 0, 'nome': nome,
        'preview_path': preview_path,
    }

    def _run():
        global _atleta_state
        import tempfile, shutil
        from scripts.analisar_atleta import analisar_video, gerar_heatmap, gerar_csv, calcular_zonas
        import scripts.analisar_atleta as _mod
        _mod.SIMILARITY_THRESHOLD = threshold
        tmp_file = None
        try:
            path = video_path
            if is_url:
                _atleta_state.update({'status': 'rodando', 'progresso': 2,
                                      'msg': 'Baixando vídeo do YouTube...'})
                tmp_file = tempfile.mktemp(suffix='.mp4')
                dl = subprocess.run(
                    ['yt-dlp',
                     '--extractor-args', 'youtube:player_client=android',
                     '-f', 'best[height<=720][ext=mp4]/best[height<=720]/best',
                     '-o', tmp_file, video_path],
                    capture_output=True, text=True
                )
                if dl.returncode != 0 or not os.path.exists(tmp_file):
                    raise RuntimeError(f'Falha no download: {dl.stderr[-400:]}')
                path = tmp_file
                _atleta_state.update({'progresso': 5, 'msg': 'Download concluído. Analisando...'})

            resultado = analisar_video(path, ref_embedding, _atleta_state)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            nome_arquivo = f'heatmap_{nome}_{ts}.png'
            csv_arquivo  = f'posicoes_{nome}_{ts}.csv'
            heatmap_path = str(HEATMAPS_DIR / nome_arquivo)
            csv_path     = str(HEATMAPS_DIR / csv_arquivo)
            gerou   = gerar_heatmap(resultado['posicoes'], heatmap_path, nome)
            gerar_csv(resultado['posicoes'], csv_path, nome)
            zonas   = calcular_zonas(resultado['posicoes'])
            _atleta_state.update({
                'status':       'concluido',
                'progresso':    100,
                'heatmap':      nome_arquivo if gerou else None,
                'csv':          csv_arquivo,
                'zonas':        zonas,
                'matches':      resultado['matches'],
                'deteccoes':    resultado['deteccoes'],
                'total_frames': resultado['total_frames'],
            })
            _salvar_estado_atleta()
        except Exception as e:
            _atleta_state['status'] = 'erro'
            _atleta_state['erro']   = str(e)
            _salvar_estado_atleta()
        finally:
            if tmp_file and os.path.exists(tmp_file):
                os.remove(tmp_file)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'success': True, 'nome': nome})


@app.route('/api/atleta/status', methods=['GET'])
def atleta_status():
    """Retorna estado atual da análise em andamento."""
    return jsonify({'success': True, **_atleta_state})


@app.route('/api/atleta/preview', methods=['GET'])
def atleta_preview():
    """Serve o frame anotado mais recente durante a análise."""
    path = _atleta_state.get('preview_path', '/tmp/atleta_preview.jpg')
    if not os.path.exists(path):
        return '', 204
    resp = send_file(path, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/atleta/csv/<path:filename>', methods=['GET'])
def atleta_csv_download(filename):
    """Download do CSV de posições gerado após análise."""
    csv_path = HEATMAPS_DIR / filename
    if not csv_path.exists():
        return jsonify({'error': 'CSV não encontrado'}), 404
    return send_file(str(csv_path.resolve()),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=filename)


@app.route('/api/atleta/atletas', methods=['GET'])
def atleta_listar():
    """Lista atletas com embedding gerado."""
    atletas = []
    if ATLETA_REFS_DIR.exists():
        for d in sorted(ATLETA_REFS_DIR.iterdir()):
            if d.is_dir() and (d / 'embedding.json').exists():
                n_fotos = len(list(d.glob('*.jpg'))) + len(list(d.glob('*.png')))
                atletas.append({'nome': d.name, 'n_fotos': n_fotos})
    return jsonify({'success': True, 'atletas': atletas})


# Recuperar candidatos .revisao/ pendentes de sessões anteriores
_captura_refs_state = _recuperar_revisao_do_disco()

if __name__ == '__main__':
    print("\n" + "="*70)
    print("⚽ SISTEMA TERÇA NOBRE - ANÁLISE DE FUTEBOL")
    print("="*70)
    print(f"\n✓ {len(IDS_SORTED)} IDs capturados")
    print(f"✓ {len(classificacoes)} já classificados")
    print(f"✓ {len(JOGADORES)} jogadores cadastrados")
    print(f"\n🔵 Time Azul: {len(TIMES['time_azul'])} jogadores")
    print(f"⚫ Time Preto: {len(TIMES['time_preto'])} jogadores")
    print(f"\n🌐 Dashboard: http://localhost:5001")
    print(f"🏷️  Classificar: http://localhost:5001/classificar")
    print("\n   Pressione Ctrl+C para sair\n")
    print("="*70 + "\n")
    
    app.run(debug=True, port=5001)
