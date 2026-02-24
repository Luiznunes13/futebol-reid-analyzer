import cv2
import numpy as np
from ultralytics import YOLO
import supervision as sv
import os
import json
from pathlib import Path
from collections import defaultdict

# Configurações
VIDEO_ESQ = "/home/nunes/Downloads/Jogo 03-02-2026 - Ataque do 🔵 (🔵 1 x 1 ⚫)2.mp4"
VIDEO_DIR = "/home/nunes/Downloads/Jogo 03-02-2026 - Ataque do ⚫ (⚫ 1 x 1 🔵)2.mp4"
MODEL_PATH = "yolo11n.pt"
OUTPUT_DIR = "jogadores_terca"
REFERENCE_FILE = "jogadores_com_ids.json"
TIMES_FILE = "times.json"
SIMILARITY_THRESHOLD = 0.65  # Reduzido porque agora compara menos jogadores

class JogadorRecognizerPorTime:
    """Sistema de reconhecimento separado por cor de time"""
    
    def __init__(self, reference_file, times_file, images_dir):
        self.reference_file = reference_file
        self.times_file = times_file
        self.images_dir = Path(images_dir)
        
        # Embeddings separados por time
        self.embeddings_azul = {}
        self.embeddings_preto = {}
        
        # Configuração dos times
        with open(times_file, 'r', encoding='utf-8') as f:
            self.times = json.load(f)
    
    def detect_team_color(self, image):
        """Detecta se é time azul ou preto pela cor predominante da parte superior"""
        if image.size == 0:
            return None
        
        h, w = image.shape[:2]
        # Pegar parte superior (tórax = camisa)
        torso = image[int(h*0.2):int(h*0.6), :]
        
        if torso.size == 0:
            return None
        
        # Converter para HSV
        hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
        
        # Definir ranges de cores
        # Azul: H entre 100-130
        lower_blue = np.array([100, 50, 50])
        upper_blue = np.array([130, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
        
        # Preto/Cinza: baixa saturação e baixo valor
        lower_black = np.array([0, 0, 0])
        upper_black = np.array([180, 255, 80])
        mask_black = cv2.inRange(hsv, lower_black, upper_black)
        
        # Contar pixels
        blue_pixels = cv2.countNonZero(mask_blue)
        black_pixels = cv2.countNonZero(mask_black)
        
        # Decidir qual time baseado em maior quantidade
        if blue_pixels > black_pixels * 1.5:  # Bias para azul
            return 'azul'
        elif black_pixels > blue_pixels:
            return 'preto'
        else:
            return None  # Incerto
    
    def extract_features(self, image):
        """Extrai features da imagem"""
        if image.size == 0:
            return None
        
        img_resized = cv2.resize(image, (128, 256))
        features = []
        
        # Histograma de cor (parte superior = camisa)
        top_half = img_resized[:128, :]
        for channel in range(3):
            hist = cv2.calcHist([top_half], [channel], None, [32], [0, 256])
            features.extend(hist.flatten())
        
        # HSV
        hsv = cv2.cvtColor(top_half, cv2.COLOR_BGR2HSV)
        hist_h = cv2.calcHist([hsv], [0], None, [32], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256])
        features.extend(hist_h.flatten())
        features.extend(hist_s.flatten())
        
        # Normalizar
        features = np.array(features)
        features = features / (np.linalg.norm(features) + 1e-6)
        
        return features
    
    def load_references(self):
        """Carrega referências separadas por time"""
        print("\n🔍 Carregando referências por time...")
        
        if not os.path.exists(self.reference_file):
            print(f"⚠️  {self.reference_file} não encontrado!")
            return False
        
        with open(self.reference_file, 'r', encoding='utf-8') as f:
            classificacoes = json.load(f)
        
        if len(classificacoes) == 0:
            print("⚠️  Nenhum jogador classificado!")
            return False
        
        # Agrupar por nome e time
        jogadores_azul = defaultdict(list)
        jogadores_preto = defaultdict(list)
        
        for id_num, nome in classificacoes.items():
            if nome in self.times['time_azul']:
                jogadores_azul[nome].append(id_num)
            elif nome in self.times['time_preto']:
                jogadores_preto[nome].append(id_num)
        
        # Processar time azul
        print(f"\n🔵 TIME AZUL:")
        for nome, ids in jogadores_azul.items():
            embeddings = []
            for id_num in ids:
                for img_path in self.images_dir.glob(f"*_id_{id_num}.jpg"):
                    img = cv2.imread(str(img_path))
                    if img is not None:
                        features = self.extract_features(img)
                        if features is not None:
                            embeddings.append(features)
            
            if embeddings:
                self.embeddings_azul[nome] = np.mean(embeddings, axis=0)
                print(f"  ✓ {nome}: {len(embeddings)} refs")
        
        # Processar time preto
        print(f"\n⚫ TIME PRETO:")
        for nome, ids in jogadores_preto.items():
            embeddings = []
            for id_num in ids:
                for img_path in self.images_dir.glob(f"*_id_{id_num}.jpg"):
                    img = cv2.imread(str(img_path))
                    if img is not None:
                        features = self.extract_features(img)
                        if features is not None:
                            embeddings.append(features)
            
            if embeddings:
                self.embeddings_preto[nome] = np.mean(embeddings, axis=0)
                print(f"  ✓ {nome}: {len(embeddings)} refs")
        
        total = len(self.embeddings_azul) + len(self.embeddings_preto)
        print(f"\n✓ Total: {total} jogadores ({len(self.embeddings_azul)} azul + {len(self.embeddings_preto)} preto)\n")
        
        return total > 0
    
    def recognize(self, image):
        """Reconhece jogador considerando o time"""
        # Detectar time pela cor
        team = self.detect_team_color(image)
        
        if team is None:
            return None, 0.0, None
        
        # Escolher pool de jogadores do time correto
        if team == 'azul':
            embeddings = self.embeddings_azul
        else:
            embeddings = self.embeddings_preto
        
        if not embeddings:
            return None, 0.0, team
        
        # Extrair features
        features = self.extract_features(image)
        if features is None:
            return None, 0.0, team
        
        # Comparar apenas com jogadores do mesmo time
        best_match = None
        best_similarity = 0.0
        
        for nome, ref_embedding in embeddings.items():
            similarity = np.dot(features, ref_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = nome
        
        if best_similarity >= SIMILARITY_THRESHOLD:
            return best_match, best_similarity, team
        
        return None, best_similarity, team


def process_videos():
    """Processa vídeos com reconhecimento por time"""
    
    # Verificar arquivos
    if not os.path.exists(TIMES_FILE):
        print("\n❌ Arquivo times.json não encontrado!")
        print("\n📝 Execute primeiro: python setup_times.py\n")
        return
    
    recognizer = JogadorRecognizerPorTime(REFERENCE_FILE, TIMES_FILE, OUTPUT_DIR)
    
    if not recognizer.load_references():
        print("\n❌ Não foi possível carregar referências!")
        print("\n📝 PASSOS:")
        print("   1. python setup_times.py")
        print("   2. python app_times.py")
        print("   3. python reconhecer_por_time.py\n")
        return
    
    print(f"Carregando modelo {MODEL_PATH}...")
    model = YOLO(MODEL_PATH)
    
    label_annotator = sv.LabelAnnotator(
        text_position=sv.Position.TOP_CENTER,
        text_scale=0.6,
        text_thickness=2
    )
    box_annotator = sv.BoxAnnotator(thickness=2)
    
    videos = [
        ("ESQ", VIDEO_ESQ),
        ("DIR", VIDEO_DIR)
    ]
    
    for camera_name, video_path in videos:
        print(f"\n{'='*70}")
        print(f"⚽ Processando: {camera_name}")
        print(f"{'='*70}\n")
        
        tracker = sv.ByteTrack()
        cap = cv2.VideoCapture(video_path)
        frame_count = 0
        
        recognized_players = {}  # track_id -> (nome, time, conf)
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            results = model.track(
                frame,
                persist=True,
                classes=[0],
                verbose=False
            )[0]
            
            detections = sv.Detections.from_ultralytics(results)
            detections = tracker.update_with_detections(detections)
            
            labels = []
            colors = []
            
            for i in range(len(detections)):
                track_id = detections.tracker_id[i]
                
                if track_id in recognized_players:
                    nome, team, conf = recognized_players[track_id]
                    emoji = "🔵" if team == 'azul' else "⚫"
                    labels.append(f"{emoji} {nome} ({conf:.0%})")
                else:
                    x1, y1, x2, y2 = detections.xyxy[i].astype(int)
                    crop = frame[max(0, y1):y2, max(0, x1):x2]
                    
                    nome, similarity, team = recognizer.recognize(crop)
                    
                    if nome:
                        recognized_players[track_id] = (nome, team, similarity)
                        emoji = "🔵" if team == 'azul' else "⚫"
                        labels.append(f"{emoji} {nome} ({similarity:.0%})")
                        print(f"✓ ID {track_id} = {emoji} {nome} ({similarity:.0%})")
                    else:
                        emoji = "🔵" if team == 'azul' else "⚫" if team else "❓"
                        labels.append(f"{emoji} ID {track_id}")
            
            annotated_frame = box_annotator.annotate(scene=frame.copy(), detections=detections)
            annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections, labels=labels)
            
            cv2.putText(annotated_frame, f"Frame: {frame_count} | Reconhecidos: {len(recognized_players)}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            h, w = annotated_frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                annotated_frame = cv2.resize(annotated_frame, (1280, int(h * scale)))
            
            cv2.imshow(f"Reconhecimento por Time: {camera_name}", annotated_frame)
            
            if frame_count % 50 == 0:
                print(f"Frame {frame_count}...")
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        
        # Resumo
        print(f"\n{'='*70}")
        print(f"✓ {camera_name} concluído: {frame_count} frames")
        print(f"✓ Jogadores reconhecidos: {len(recognized_players)}")
        
        azul = [(tid, nome, conf) for tid, (nome, team, conf) in recognized_players.items() if team == 'azul']
        preto = [(tid, nome, conf) for tid, (nome, team, conf) in recognized_players.items() if team == 'preto']
        
        print(f"\n🔵 Time Azul ({len(azul)}):")
        for tid, nome, conf in azul:
            print(f"  - ID {tid}: {nome} ({conf:.0%})")
        
        print(f"\n⚫ Time Preto ({len(preto)}):")
        for tid, nome, conf in preto:
            print(f"  - ID {tid}: {nome} ({conf:.0%})")
        
        print(f"{'='*70}\n")
    
    print("\n🎉 PROCESSAMENTO CONCLUÍDO!\n")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🔵⚫ RECONHECIMENTO AUTOMÁTICO POR TIMES")
    print("="*70)
    print(f"✓ Modelo: {MODEL_PATH}")
    print(f"✓ Limiar: {SIMILARITY_THRESHOLD*100:.0f}%")
    print(f"✓ Separação por cor de colete")
    print("="*70)
    
    process_videos()
