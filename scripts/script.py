import cv2
import numpy as np
from ultralytics import YOLO
import supervision as sv
import os
import signal
import sys
import subprocess
import json
from pathlib import Path

# Flag global para controlar interrupção
STOP_FLAG = False
STOP_FLAG_FILE = Path(".stop_script")

def signal_handler(sig, frame):
    """Handler para Ctrl+C e outros sinais de interrupção"""
    global STOP_FLAG
    print('\n\n⚠️  Interrupção detectada! Finalizando...')
    STOP_FLAG = True

def check_stop_flag():
    """Verifica se há um arquivo de flag pedindo para parar"""
    global STOP_FLAG
    if STOP_FLAG_FILE.exists():
        print('\n\n⚠️  Flag de parada detectada! Finalizando...')
        STOP_FLAG = True
        STOP_FLAG_FILE.unlink()  # Remove o arquivo
        return True
    return False

# Registrar handlers de sinais
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Configurações Iniciais
VIDEO_ESQ = None  # definido via --video-esq
VIDEO_DIR = None  # definido via --video-dir
MODEL_PATH = "yolo11n.pt"  # Volta para Nano - mais rápido e leve
OUTPUT_DIR = "jogadores_terca"
CONFIDENCE_THRESHOLD = 0.5  # Mínimo de confiança para salvar foto
USE_FACE_DETECTION = False  # Salvar apenas se detectar rosto

# Modo headless: sem janela CV2
# Ativa se: --headless nos args OU variável HEADLESS=1 OU não tem DISPLAY (servidor)
HEADLESS_MODE = (
    '--headless' in sys.argv or 
    os.environ.get('HEADLESS', '0') == '1' or
    os.environ.get('DISPLAY', '') == ''
)

# Suporte a vídeos customizados via argumentos de linha de comando
import argparse as _argparse
_parser = _argparse.ArgumentParser(add_help=False)
_parser.add_argument('--video-esq',   default=None, help='Caminho ou URL do vídeo câmera ESQ')
_parser.add_argument('--video-dir',   default=None, help='Caminho ou URL do vídeo câmera DIR')
_parser.add_argument('--model',       default=None, help='Modelo YOLO (ex: yolo11n.pt)')
_parser.add_argument('--confidence',  type=float, default=None, help='Confiança mínima 0-1')
_parser.add_argument('--output-dir',  default=None, help='Pasta de saída das imagens')
_parser.add_argument('--headless', action='store_true')
_args, _ = _parser.parse_known_args()

if _args.video_esq:
    VIDEO_ESQ = _args.video_esq
if _args.video_dir:
    VIDEO_DIR = _args.video_dir
if _args.model:
    MODEL_PATH = _args.model
if _args.confidence is not None:
    CONFIDENCE_THRESHOLD = _args.confidence
if _args.output_dir:
    OUTPUT_DIR = _args.output_dir

# Se apenas um vídeo foi informado, usa o mesmo para os dois lados
if VIDEO_ESQ and not VIDEO_DIR:
    VIDEO_DIR = VIDEO_ESQ
    print("⚠ Câmera DIR não definida — usando o mesmo vídeo da ESQ")
elif VIDEO_DIR and not VIDEO_ESQ:
    VIDEO_ESQ = VIDEO_DIR
    print("⚠ Câmera ESQ não definida — usando o mesmo vídeo da DIR")
elif not VIDEO_ESQ and not VIDEO_DIR:
    print("❌ Erro: nenhum vídeo fornecido. Use --video-esq e/ou --video-dir")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"🎬 Iniciando captura de imagens")
print(f"{'='*60}")
print(f"Modo: {'🖥️  Headless (sem janela)' if HEADLESS_MODE else '🪟 Com janela'}")
print(f"Vídeo ESQ: {VIDEO_ESQ}")
print(f"Vídeo DIR: {VIDEO_DIR}")
print(f"{'='*60}\n")

# ROI (Região de Interesse) - Descomente e ajuste os pontos para limitar ao campo
# Formato: lista de pontos [x, y] formando um polígono
# USE_ROI = True
# ROI_POINTS = np.array([[100, 100], [1800, 100], [1800, 900], [100, 900]], np.int32)
USE_ROI = False
ROI_POINTS = None

# Criar pasta para os cards dos jogadores
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Inicializar Modelo e Rastreadores
print(f"Carregando modelo {MODEL_PATH}...")
model = YOLO(MODEL_PATH)
tracker_esq = sv.ByteTrack()
tracker_dir = sv.ByteTrack()

# Carregar detector de rostos (Haar Cascade)
if USE_FACE_DETECTION:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    print("✓ Detector de rostos carregado")

# Inicializar Anotadores com posição otimizada
label_annotator = sv.LabelAnnotator(
    text_position=sv.Position.TOP_CENTER,  # ID acima da caixa
    text_scale=0.5,
    text_thickness=1
)
box_annotator = sv.BoxAnnotator(thickness=2)

def has_face(image):
    """Verifica se há pelo menos um rosto na imagem"""
    if not USE_FACE_DETECTION:
        return True  # Se não estiver usando detecção, sempre retorna True
    
    if image is None or image.size == 0:
        return False
    
    # Converte para escala de cinza
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Detecta rostos
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=3,
        minSize=(20, 20)
    )
    
    return len(faces) > 0

def apply_roi_mask(detections, roi_points):
    """Filtra detecções que estão fora da região de interesse"""
    if roi_points is None:
        return detections
    
    valid_indices = []
    for i in range(len(detections)):
        x1, y1, x2, y2 = detections.xyxy[i]
        # Centro da caixa delimitadora
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        
        # Verifica se o centro está dentro do polígono
        if cv2.pointPolygonTest(roi_points, (center_x, center_y), False) >= 0:
            valid_indices.append(i)
    
    # Filtra as detecções
    if len(valid_indices) > 0:
        detections = detections[valid_indices]
    else:
        # Retorna detecções vazias se nada estiver no ROI
        detections = sv.Detections.empty()
    
    return detections

def process_frame(frame, tracker, camera_name):
    # Detecção simples e rápida
    results = model.track(
        frame, 
        persist=True, 
        classes=[0, 32],  # Pessoas e bola
        verbose=False
    )[0]
    
    detections = sv.Detections.from_ultralytics(results)
    
    # Aplicar ROI se configurado
    if USE_ROI and ROI_POINTS is not None:
        detections = apply_roi_mask(detections, ROI_POINTS)
    
    detections = tracker.update_with_detections(detections)

    # Lógica para salvar fotos dos jogadores (Cards) com filtro de confiança e rosto
    for i in range(len(detections)):
        if detections.class_id[i] == 0:  # Se for pessoa
            confidence = detections.confidence[i]
            
            # FILTRO DE CONFIANÇA: Só salva se tiver certeza >= threshold
            if confidence > CONFIDENCE_THRESHOLD:
                track_id = detections.tracker_id[i]
                save_path = f"{OUTPUT_DIR}/{camera_name}_id_{track_id}.jpg"
                
                # Se a foto ainda não existe, tenta salvar o crop
                if not os.path.exists(save_path):
                    x1, y1, x2, y2 = detections.xyxy[i].astype(int)
                    crop = frame[max(0, y1):y2, max(0, x1):x2]
                    
                    # Verifica se o crop tem conteúdo E se há rosto
                    if crop.size > 0 and has_face(crop):
                        cv2.imwrite(save_path, crop)
                        print(f"✓ Rosto detectado - Salvando: {save_path}")

    # Desenha na tela com confiança
    labels = [
        f"ID: {track_id} ({conf:.0%})" 
        for track_id, conf in zip(detections.tracker_id, detections.confidence)
    ]
    
    annotated_frame = box_annotator.annotate(scene=frame.copy(), detections=detections)
    annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections, labels=labels)
    
    # Desenhar ROI se ativo
    if USE_ROI and ROI_POINTS is not None:
        cv2.polylines(annotated_frame, [ROI_POINTS], True, (0, 255, 0), 3)
    
    return annotated_frame

# Loop Principal
class StreamCapture:
    """
    Imita cv2.VideoCapture mas obtém frames via pipe:
      yt-dlp (download) | ffmpeg (decode) -> frames bgr24
    Usado quando a fonte é uma URL de stream (YouTube, etc.)
    """
    def __init__(self, url):
        self._url    = url
        self._opened = False
        self._procs  = []
        self._w = self._h = 0

        # Obtém dimensões via yt-dlp --dump-json
        try:
            info_r = subprocess.run(
                [sys.executable, '-m', 'yt_dlp',
                 '--extractor-args', 'youtube:player_client=android',
                 '--dump-json', '--no-download', '--quiet', '--no-warnings',
                 '--no-playlist', url],
                capture_output=True, text=True, timeout=25
            )
            if info_r.returncode == 0 and info_r.stdout.strip():
                info = json.loads(info_r.stdout.splitlines()[0])
                self._w = info.get('width',  640) or 640
                self._h = info.get('height', 360) or 360
        except Exception:
            pass

        if not self._w:
            self._w, self._h = 640, 360  # fallback 360p

        # yt-dlp: baixa stream direto para stdout via cliente android (sem SABR)
        yt_proc = subprocess.Popen(
            [sys.executable, '-m', 'yt_dlp',
             '--extractor-args', 'youtube:player_client=android',
             '-f', '18/best[height<=480]/best',
             '--no-playlist', '--quiet', '--no-warnings',
             '-o', '-', url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        # ffmpeg: decodifica e emite frames BGR24 brutos para stdout
        ff_proc = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0',
             '-f', 'rawvideo', '-pix_fmt', 'bgr24',
             '-vf', f'scale={self._w}:{self._h}',
             'pipe:1', '-loglevel', 'quiet'],
            stdin=yt_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        yt_proc.stdout.close()  # permite SIGPIPE se ffmpeg morrer
        self._procs  = [yt_proc, ff_proc]
        self._ff     = ff_proc
        self._bytes_per_frame = self._w * self._h * 3
        self._opened = True
        print(f"\n📺 Stream pipe iniciado ({self._w}x{self._h}) — yt-dlp → ffmpeg → OpenCV")

    def isOpened(self):
        return self._opened and self._ff.poll() is None

    def read(self):
        if not self.isOpened():
            return False, None
        raw = self._ff.stdout.read(self._bytes_per_frame)
        if len(raw) < self._bytes_per_frame:
            self._opened = False
            return False, None
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((self._h, self._w, 3))
        return True, frame.copy()

    def get(self, prop_id):
        """Streams não têm frame count."""
        return 0

    def release(self):
        self._opened = False
        for p in self._procs:
            try:
                p.terminate()
            except Exception:
                pass


def _open_video(path_or_url):
    """Abre arquivo local ou stream YouTube via pipe."""
    if path_or_url.startswith('http://') or path_or_url.startswith('https://'):
        return StreamCapture(path_or_url)
    return cv2.VideoCapture(path_or_url)

cap_e = _open_video(VIDEO_ESQ)
cap_d = _open_video(VIDEO_DIR)

# Contadores
total_detections = 0
saved_with_face = 0
frame_count = 0
total_frames = max(
    int(cap_e.get(cv2.CAP_PROP_FRAME_COUNT)),
    int(cap_d.get(cv2.CAP_PROP_FRAME_COUNT))
)
# Streams de rede retornam 0 — usa modo sem total definido
IS_STREAM = (total_frames == 0)

print("\nIniciando processamento...")
if HEADLESS_MODE:
    print("✓ Modo sem janela (headless) - execute 'touch .stop_script' para parar")
else:
    print("✓ Pressione 'q' na janela do vídeo para sair")

if USE_FACE_DETECTION:
    print("✓ Salvando apenas imagens com rostos detectados")
else:
    print("✓ Salvando todas as imagens")

print(f"\u2713 Total de frames: {total_frames if not IS_STREAM else '(stream — sem total definido)'}\n")

while cap_e.isOpened() and cap_d.isOpened() and not STOP_FLAG:
    ret_e, frame_e = cap_e.read()
    ret_d, frame_d = cap_d.read()
    
    if not ret_e or not ret_d:
        print("\n✓ Fim do vídeo alcançado")
        break
    
    frame_count += 1
    
    # Verifica flag de parada a cada 30 frames (~1 segundo)
    if frame_count % 30 == 0:
        check_stop_flag()
        if STOP_FLAG:
            print(f"\n\u26a0\ufe0f  Processamento interrompido no frame {frame_count}" +
                  (f"/{total_frames}" if not IS_STREAM else ""))
            break
        # Mostra progresso
        if IS_STREAM:
            print(f"\rFrames: {frame_count}", end='', flush=True)
        else:
            progress = (frame_count / total_frames) * 100
            print(f"\rProgresso: {frame_count}/{total_frames} frames ({progress:.1f}%)", end='', flush=True)

    # Processar cada lado
    out_e = process_frame(frame_e, tracker_esq, "ESQ")
    out_d = process_frame(frame_d, tracker_dir, "DIR")

    # Apenas mostra janela se não estiver em modo headless
    if not HEADLESS_MODE:
        # Unificar os dois vídeos lado a lado
        combined = np.hstack((
            cv2.resize(out_e, (640, 360)), 
            cv2.resize(out_d, (640, 360))
        ))

        cv2.imshow("Futebol de Terca - Analise Multi-Camera", combined)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n✓ Usuário solicitou parada")
            break

print(f"\n\n{'='*60}")
print(f"✅ Processamento finalizado!")
print(f"{'='*60}")
print(f"Frames processados: {frame_count}" + (f"/{total_frames}" if not IS_STREAM else " (stream)"))
print(f"Imagens salvas em: {OUTPUT_DIR}/")
print(f"{'='*60}\n")

cap_e.release()
cap_d.release()

if not HEADLESS_MODE:
    cv2.destroyAllWindows()