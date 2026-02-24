"""
Reconhecimento de jogadores usando modelo ReID treinado
Muito mais preciso que histogramas de cor
"""

import cv2
import torch
import torch.nn as nn
import numpy as np
from ultralytics import YOLO
import supervision as sv
from pathlib import Path
import json
import argparse
from collections import Counter
from torchvision import transforms, models
from PIL import Image
from scipy.spatial.distance import cosine

# Configurações
# Caminhos de vídeo passados via CLI (--cam1 / --cam2)
MODEL_YOLO = "yolo11n.pt"
MODEL_REID = "modelo_reid_terca.pth"
EMBEDDINGS_DIR = Path('embeddings_reid')
SIMILARITY_THRESHOLD = 0.70  # Limiar de similaridade (ajuste se necessário)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


class ReIDModel(nn.Module):
    """Mesmo modelo usado no treinamento"""
    
    def __init__(self, num_classes, embedding_size=512):
        super(ReIDModel, self).__init__()
        
        resnet = models.resnet50(weights=None)
        self.backbone = nn.Sequential(*list(resnet.children())[:-1])
        self.global_pool = nn.AdaptiveAvgPool2d((1, 1))
        
        self.embedding = nn.Sequential(
            nn.Linear(2048, embedding_size),
            nn.BatchNorm1d(embedding_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5)
        )
        
        self.classifier = nn.Linear(embedding_size, num_classes)
        
    def forward(self, x):
        x = self.backbone(x)
        x = self.global_pool(x)
        x = torch.flatten(x, 1)
        embedding = self.embedding(x)
        logits = self.classifier(embedding)
        return logits, embedding


class ReconhecedorReID:
    """Reconhecedor usando embeddings ReID"""
    
    def __init__(self):
        # Verificar arquivos necessários
        if not Path(MODEL_REID).exists():
            raise FileNotFoundError(
                f"Modelo {MODEL_REID} não encontrado!\n"
                "Execute: python treinar_reid_model.py"
            )
        
        embeddings_file = EMBEDDINGS_DIR / 'embeddings_database.json'
        if not embeddings_file.exists():
            raise FileNotFoundError(
                f"Embeddings não encontrados!\n"
                "Execute: python treinar_reid_model.py (opção 2 ou 3)"
            )
        
        # Carregar modelo
        print("📥 Carregando modelo ReID...")
        checkpoint = torch.load(MODEL_REID, map_location=device)
        
        self.classes = checkpoint['classes']
        self.model = ReIDModel(len(self.classes)).to(device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.eval()
        
        print(f"✓ Modelo carregado (Acc: {checkpoint['val_acc']:.2f}%)")
        
        # Carregar embeddings database
        print("📥 Carregando embeddings dos jogadores...")
        with open(embeddings_file) as f:
            embeddings_data = json.load(f)
        
        self.embeddings_db = {
            nome: np.array(emb) 
            for nome, emb in embeddings_data.items()
        }
        
        print(f"✓ {len(self.embeddings_db)} jogadores na database\n")
        
        # Transformação para inferência
        self.transform = transforms.Compose([
            transforms.Resize((256, 128)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
        
        # Janela de votação por track_id (evita erro de classificação no 1º frame)
        self.WINDOW_SIZE = 10
        self.cache = {}  # track_id → list de (nome, confianca) dos últimos WINDOW_SIZE frames
    
    def extrair_embedding(self, crop_bgr):
        """Extrai embedding de uma detecção"""
        # Converter BGR -> RGB
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(crop_rgb)
        
        # Transformar e processar
        img_tensor = self.transform(img_pil).unsqueeze(0).to(device)
        
        with torch.no_grad():
            _, embedding = self.model(img_tensor)
        
        return embedding.cpu().numpy().flatten()
    
    def reconhecer(self, crop_bgr, track_id):
        """Reconhece jogador usando janela de votação (evita erro no 1º frame)"""
        # Extrair embedding e comparar com database
        embedding_query = self.extrair_embedding(crop_bgr)
        melhor_match = None
        melhor_similaridade = 0

        for nome, embedding_db in self.embeddings_db.items():
            similaridade = 1 - cosine(embedding_query, embedding_db)
            if similaridade > melhor_similaridade:
                melhor_similaridade = similaridade
                melhor_match = nome

        # Registrar resultado do frame atual na janela do track
        nome_frame = melhor_match if melhor_similaridade >= SIMILARITY_THRESHOLD else None
        conf_frame = melhor_similaridade if nome_frame else 0.0

        if track_id not in self.cache:
            self.cache[track_id] = []
        self.cache[track_id].append((nome_frame, conf_frame))
        if len(self.cache[track_id]) > self.WINDOW_SIZE:
            self.cache[track_id].pop(0)

        # Votação por maioria dentro da janela
        votos = [nome for nome, _ in self.cache[track_id] if nome is not None]
        if not votos:
            return {'nome': f'Desconhecido (ID {track_id})', 'confianca': 0}

        nome_vencedor = Counter(votos).most_common(1)[0][0]
        confianca_media = float(np.mean(
            [conf for nome, conf in self.cache[track_id] if nome == nome_vencedor]
        ))
        return {'nome': nome_vencedor, 'confianca': confianca_media}


def processar_video(video_path, camera_name):
    """Processa vídeo com reconhecimento ReID"""
    
    print(f"\n🎥 Processando: {camera_name}")
    print(f"   Vídeo: {Path(video_path).name}\n")
    
    # Inicializar
    yolo_model = YOLO(MODEL_YOLO)
    tracker = sv.ByteTrack()
    reconhecedor = ReconhecedorReID()
    
    # Anotadores
    box_annotator = sv.BoxAnnotator(thickness=2)
    label_annotator = sv.LabelAnnotator(
        text_position=sv.Position.TOP_CENTER,
        text_scale=0.6,
        text_thickness=2
    )
    
    # Estatísticas
    stats = {
        'reconhecidos': 0,
        'desconhecidos': 0,
        'jogadores': {}
    }
    
    cap = cv2.VideoCapture(video_path)
    frame_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        # Detecção e rastreamento
        results = yolo_model.track(
            frame,
            persist=True,
            classes=[0],  # Apenas pessoas
            verbose=False
        )[0]
        
        detections = sv.Detections.from_ultralytics(results)
        detections = tracker.update_with_detections(detections)
        
        # Reconhecimento
        labels = []
        for i in range(len(detections)):
            track_id = detections.tracker_id[i]
            x1, y1, x2, y2 = detections.xyxy[i].astype(int)
            
            # Crop
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            
            if crop.size > 0:
                # Reconhecer
                resultado = reconhecedor.reconhecer(crop, track_id)
                nome = resultado['nome']
                confianca = resultado['confianca']
                
                # Estatísticas
                if confianca > 0:
                    stats['reconhecidos'] += 1
                    if nome not in stats['jogadores']:
                        stats['jogadores'][nome] = 0
                    stats['jogadores'][nome] += 1
                else:
                    stats['desconhecidos'] += 1
                
                # Label
                if confianca > 0:
                    label = f"{nome} ({confianca:.0%})"
                else:
                    label = nome
                
                labels.append(label)
            else:
                labels.append(f"ID {track_id}")
        
        # Desenhar
        frame_anotado = box_annotator.annotate(frame.copy(), detections)
        frame_anotado = label_annotator.annotate(frame_anotado, detections, labels)
        
        # Info no frame
        info_text = f"Frame: {frame_count} | Reconhecidos: {stats['reconhecidos']} | Desconhecidos: {stats['desconhecidos']}"
        cv2.putText(frame_anotado, info_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Mostrar
        cv2.imshow(f"ReID - {camera_name}", cv2.resize(frame_anotado, (960, 540)))
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Relatório
    print("\n" + "="*70)
    print(f"📊 RELATÓRIO - {camera_name}")
    print("="*70)
    print(f"\nFrames processados: {frame_count}")
    print(f"Detecções reconhecidas: {stats['reconhecidos']}")
    print(f"Detecções desconhecidas: {stats['desconhecidos']}")
    
    if stats['jogadores']:
        print(f"\n👥 Jogadores reconhecidos:")
        for jogador, count in sorted(stats['jogadores'].items(), key=lambda x: x[1], reverse=True):
            print(f"   - {jogador}: {count} detecções")
    
    print("\n" + "="*70 + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Reconhecimento de jogadores com ReID')
    parser.add_argument('--cam1', metavar='VIDEO', help='Vídeo da Câmera 1')
    parser.add_argument('--cam2', metavar='VIDEO', help='Vídeo da Câmera 2')
    args = parser.parse_args()

    if not args.cam1 and not args.cam2:
        parser.error('Informe ao menos um vídeo: --cam1 /path/video.mp4  ou  --cam2 /path/video.mp4')

    print("\n" + "="*70)
    print("🔍 RECONHECIMENTO COM REID - TERÇA NOBRE")
    print("="*70)

    try:
        if args.cam1:
            processar_video(args.cam1, "Câmera 1")
        if args.cam2:
            processar_video(args.cam2, "Câmera 2")
    except FileNotFoundError as e:
        print(f"\n❌ Erro: {e}")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
