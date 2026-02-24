"""
Script para análise de trajetória e cálculo de distância percorrida
Integra os IDs rastreados com os nomes dos jogadores
"""

import cv2
import numpy as np
from ultralytics import YOLO
import supervision as sv
import json
import os
from collections import defaultdict
from pathlib import Path

# Configurações
VIDEO_ESQ = "/home/nunes/Downloads/Jogo 03-02-2026 - Ataque do 🔵 (🔵 1 x 1 ⚫)2.mp4"
VIDEO_DIR = "/home/nunes/Downloads/Jogo 03-02-2026 - Ataque do ⚫ (⚫ 1 x 1 🔵)2.mp4"
MODEL_PATH = "yolo11n.pt"
CLASSIFICACOES_FILE = 'jogadores_com_ids.json'
TIMES_FILE = 'times.json'

# Configurações de campo (em metros)
LARGURA_CAMPO_METROS = 68  # Campo oficial futsal
COMPRIMENTO_CAMPO_METROS = 40
LARGURA_VIDEO_PIXELS = 1920
ALTURA_VIDEO_PIXELS = 1080

# Calcular escala pixels -> metros (aproximado)
ESCALA_X = LARGURA_CAMPO_METROS / LARGURA_VIDEO_PIXELS
ESCALA_Y = COMPRIMENTO_CAMPO_METROS / ALTURA_VIDEO_PIXELS

class AnalisadorTrajetoria:
    def __init__(self):
        # Carregar classificações
        self.classificacoes = {}
        if os.path.exists(CLASSIFICACOES_FILE):
            with open(CLASSIFICACOES_FILE, 'r', encoding='utf-8') as f:
                self.classificacoes = json.load(f)
        
        # Carregar times
        self.times = {}
        if os.path.exists(TIMES_FILE):
            with open(TIMES_FILE, 'r', encoding='utf-8') as f:
                self.times = json.load(f)
        
        # Histórico de posições: {track_id: [(x, y), ...]}
        self.trajetorias = defaultdict(list)
        
        # Distâncias percorridas: {track_id: distancia_metros}
        self.distancias = defaultdict(float)
        
        # Frame count para cálculo de velocidade
        self.frame_count = 0
        self.fps = 30  # Será atualizado do vídeo
    
    def get_nome_jogador(self, track_id, camera):
        """Retorna o nome do jogador baseado no ID e câmera"""
        id_key = str(track_id)
        
        # Verifica se o ID foi classificado
        if id_key in self.classificacoes:
            nome = self.classificacoes[id_key]
            if nome != 'DESCARTADO':
                return nome
        
        return f"ID {track_id}"
    
    def get_cor_time(self, nome):
        """Retorna a cor do time do jogador"""
        if nome in self.times.get('time_azul', []):
            return (255, 100, 0)  # Azul (BGR)
        elif nome in self.times.get('time_preto', []):
            return (100, 100, 100)  # Cinza
        else:
            return (0, 255, 255)  # Amarelo (não classificado)
    
    def calcular_distancia(self, p1, p2):
        """Calcula distância entre dois pontos em metros"""
        dx = (p2[0] - p1[0]) * ESCALA_X
        dy = (p2[1] - p1[1]) * ESCALA_Y
        return np.sqrt(dx**2 + dy**2)
    
    def atualizar_trajetoria(self, track_id, x, y):
        """Atualiza trajetória e calcula distância incremental"""
        ponto_atual = (x, y)
        
        if track_id in self.trajetorias and len(self.trajetorias[track_id]) > 0:
            ponto_anterior = self.trajetorias[track_id][-1]
            distancia = self.calcular_distancia(ponto_anterior, ponto_atual)
            
            # Filtrar movimentos irrealistas (teleporte/erro de tracking)
            if distancia < 5:  # Máximo 5 metros por frame (~150km/h)
                self.distancias[track_id] += distancia
        
        self.trajetorias[track_id].append(ponto_atual)
    
    def desenhar_trajetoria(self, frame, track_id, cor):
        """Desenha a trajetória de um jogador no frame"""
        if track_id not in self.trajetorias or len(self.trajetorias[track_id]) < 2:
            return
        
        pontos = self.trajetorias[track_id]
        
        # Desenhar apenas últimos 50 pontos para não poluir
        pontos_recentes = pontos[-50:]
        
        for i in range(1, len(pontos_recentes)):
            pt1 = tuple(map(int, pontos_recentes[i-1]))
            pt2 = tuple(map(int, pontos_recentes[i]))
            cv2.line(frame, pt1, pt2, cor, 2)
    
    def gerar_relatorio(self, camera_name):
        """Gera relatório de distâncias percorridas"""
        print(f"\n{'='*70}")
        print(f"📊 RELATÓRIO DE DISTÂNCIAS - {camera_name}")
        print(f"{'='*70}\n")
        
        # Organizar por nome
        jogadores_distancias = {}
        
        for track_id, distancia in self.distancias.items():
            if distancia < 10:  # Ignorar IDs com movimento insignificante
                continue
            
            nome = self.get_nome_jogador(track_id, camera_name)
            
            # Agrupar distâncias de IDs do mesmo jogador
            if nome.startswith("ID "):
                # Não classificado
                jogadores_distancias[nome] = jogadores_distancias.get(nome, 0) + distancia
            else:
                jogadores_distancias[nome] = jogadores_distancias.get(nome, 0) + distancia
        
        # Ordenar por distância (decrescente)
        ranking = sorted(jogadores_distancias.items(), key=lambda x: x[1], reverse=True)
        
        # Separar por time
        time_azul_dist = []
        time_preto_dist = []
        nao_classificados = []
        
        for nome, dist in ranking:
            if nome in self.times.get('time_azul', []):
                time_azul_dist.append((nome, dist))
            elif nome in self.times.get('time_preto', []):
                time_preto_dist.append((nome, dist))
            else:
                nao_classificados.append((nome, dist))
        
        # Exibir Time Azul
        if time_azul_dist:
            print("🔵 TIME AZUL:")
            for i, (nome, dist) in enumerate(time_azul_dist, 1):
                print(f"   {i}. {nome:20s} → {dist:6.2f}m ({dist/1000:.2f}km)")
            print()
        
        # Exibir Time Preto
        if time_preto_dist:
            print("⚫ TIME PRETO:")
            for i, (nome, dist) in enumerate(time_preto_dist, 1):
                print(f"   {i}. {nome:20s} → {dist:6.2f}m ({dist/1000:.2f}km)")
            print()
        
        # Exibir não classificados
        if nao_classificados:
            print("❓ NÃO CLASSIFICADOS:")
            for nome, dist in nao_classificados:
                print(f"   - {nome:20s} → {dist:6.2f}m ({dist/1000:.2f}km)")
            print()
        
        # Estatísticas gerais
        total_dist = sum(d for _, d in ranking)
        media_dist = total_dist / len(ranking) if ranking else 0
        
        print(f"{'='*70}")
        print(f"RESUMO:")
        print(f"  Total de jogadores rastreados: {len(ranking)}")
        print(f"  Distância total percorrida: {total_dist:.2f}m ({total_dist/1000:.2f}km)")
        print(f"  Média por jogador: {media_dist:.2f}m ({media_dist/1000:.2f}km)")
        print(f"{'='*70}\n")
        
        return ranking

def analisar_video(video_path, camera_name):
    """Analisa um vídeo e calcula trajetórias"""
    print(f"\n🎥 Processando: {camera_name}")
    print(f"   Vídeo: {Path(video_path).name}\n")
    
    # Inicializar
    model = YOLO(MODEL_PATH)
    tracker = sv.ByteTrack()
    analisador = AnalisadorTrajetoria()
    
    cap = cv2.VideoCapture(video_path)
    analisador.fps = cap.get(cv2.CAP_PROP_FPS)
    
    # Anotadores
    box_annotator = sv.BoxAnnotator(thickness=2)
    label_annotator = sv.LabelAnnotator()
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        analisador.frame_count += 1
        
        # Detecção e rastreamento
        results = model.track(
            frame,
            persist=True,
            classes=[0],  # Apenas pessoas
            verbose=False
        )[0]
        
        detections = sv.Detections.from_ultralytics(results)
        detections = tracker.update_with_detections(detections)
        
        # Atualizar trajetórias
        for i in range(len(detections)):
            track_id = detections.tracker_id[i]
            x1, y1, x2, y2 = detections.xyxy[i]
            
            # Centro da bounding box
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            
            analisador.atualizar_trajetoria(track_id, cx, cy)
        
        # Desenhar trajetórias e anotações
        frame_anotado = frame.copy()
        
        for i in range(len(detections)):
            track_id = detections.tracker_id[i]
            nome = analisador.get_nome_jogador(track_id, camera_name)
            cor = analisador.get_cor_time(nome)
            
            # Desenhar trajetória
            analisador.desenhar_trajetoria(frame_anotado, track_id, cor)
        
        # Desenhar boxes e labels
        labels = []
        for i in range(len(detections)):
            track_id = detections.tracker_id[i]
            nome = analisador.get_nome_jogador(track_id, camera_name)
            dist = analisador.distancias[track_id]
            labels.append(f"{nome} | {dist:.0f}m")
        
        frame_anotado = box_annotator.annotate(frame_anotado, detections)
        frame_anotado = label_annotator.annotate(frame_anotado, detections, labels)
        
        # Mostrar
        cv2.imshow(f"Trajetória - {camera_name}", cv2.resize(frame_anotado, (960, 540)))
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Gerar relatório
    analisador.gerar_relatorio(camera_name)
    
    return analisador

if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', choices=['1', '2', '3'], default='3',
                        help='1=ESQ, 2=DIR, 3=Ambas (padrão: 3)')
    args = parser.parse_args()

    # Modo interativo: se stdin é um terminal real, pede input
    if sys.stdin.isatty() and args.camera == '3':
        print("\n" + "="*70)
        print("🏃 ANÁLISE DE TRAJETÓRIA E DISTÂNCIA PERCORRIDA")
        print("="*70)
        print("\nEscolha o vídeo para analisar:")
        print("1. Câmera Esquerda (ESQ)")
        print("2. Câmera Direita (DIR)")
        print("3. Ambas")
        escolha = input("\nOpção (1/2/3): ").strip() or '3'
    else:
        escolha = args.camera

    print("\n" + "="*70)
    print("🏃 ANÁLISE DE TRAJETÓRIA E DISTÂNCIA PERCORRIDA")
    print("="*70)

    if escolha == '1':
        analisar_video(VIDEO_ESQ, "ESQ")
    elif escolha == '2':
        analisar_video(VIDEO_DIR, "DIR")
    elif escolha == '3':
        print("\n📹 Processando câmera ESQ...")
        analisar_video(VIDEO_ESQ, "ESQ")
        print("\n📹 Processando câmera DIR...")
        analisar_video(VIDEO_DIR, "DIR")
    else:
        print("❌ Opção inválida!")
