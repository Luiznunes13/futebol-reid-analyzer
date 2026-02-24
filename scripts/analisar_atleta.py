"""
Análise de atleta específico por similaridade de embedding.

Pipeline:
  1. Fotos de referência → embedding médio L2-normalizado
  2. Vídeo → YOLO detecta pessoas → crop → embedding → cosine similarity
  3. Posições do atleta acumuladas → mapa de calor em campo de futebol
"""

import csv
import cv2
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from torchvision import transforms, models
from PIL import Image

# ─── Configurações ────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.65   # Limiar padrão — abaixar para mais detecções
SKIP_FRAMES = 3               # Analisa 1 a cada N frames (velocidade vs precisão)
IMG_SIZE = (256, 128)         # Altura × Largura padrão ReID
MODEL_NAME = 'osnet_x1_0'    # Modelo padrão (tenta OSNet, fallback ResNet50)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# ─── Modelo ───────────────────────────────────────────────────────
def _build_model(model_name: str = MODEL_NAME):
    """Constrói backbone de ReID. Tenta OSNet via timm, fallback ResNet50."""
    if model_name.startswith('osnet'):
        try:
            import timm
            model = timm.create_model(model_name, pretrained=True, num_classes=0)
            model.eval()
            print(f'[MODELO] {model_name} carregado via timm', flush=True)
            return model.to(device)
        except Exception as e:
            print(f'[AVISO] OSNet falhou ({e}), usando ResNet50', flush=True)
    # Fallback: ResNet50
    resnet = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    backbone = nn.Sequential(*list(resnet.children())[:-1])
    backbone.eval()
    print('[MODELO] ResNet50 carregado', flush=True)
    return backbone.to(device)


_transform = transforms.Compose([
    transforms.Resize(IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def _embedding(model, crop_bgr: np.ndarray) -> np.ndarray:
    """Extrai embedding L2-normalizado de um crop em BGR."""
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    t = _transform(img).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(t)
        emb = out.squeeze().cpu().numpy()
    norm = np.linalg.norm(emb)
    return emb / (norm + 1e-8)


# ─── Referência ───────────────────────────────────────────────────
def gerar_embedding_referencia(fotos_paths: list) -> list:
    """
    Recebe lista de caminhos de fotos do atleta.
    Retorna embedding médio como lista Python (serializável em JSON).
    """
    try:
        from scripts.acelerador import get_reid
        reid = get_reid()
        embeddings = []
        for p in fotos_paths:
            img = cv2.imread(str(p))
            if img is None:
                continue
            embeddings.append(reid.embedding(img))
    except Exception as e:
        print(f'[AVISO] Acelerador falhou ({e}), usando PyTorch', flush=True)
        model = _build_model()
        embeddings = []
        for p in fotos_paths:
            img = cv2.imread(str(p))
            if img is None:
                continue
            embeddings.append(_embedding(model, img))

    if not embeddings:
        raise ValueError("Nenhuma foto de referência válida.")

    ref = np.mean(embeddings, axis=0)
    ref = ref / (np.linalg.norm(ref) + 1e-8)
    return ref.tolist()


# ─── Análise do vídeo ─────────────────────────────────────────────
def analisar_video(video_path: str, ref_embedding: list, state: dict) -> dict:
    """
    Percorre o vídeo, detecta pessoas com YOLO e compara com embedding de referência.
    Atualiza `state` em tempo real com progresso.
    Retorna dicionário com posições normalizadas (0..1) e estatísticas.
    """
    from ultralytics import YOLO

    # ReID: preferir OpenVINO GPU, fallback PyTorch
    try:
        from scripts.acelerador import get_reid
        reid     = get_reid()
        _emb_fn  = lambda _model, crop: reid.embedding(crop)
        model_emb = None
        print(f'[ANÁLISE] ReID via OpenVINO {reid.device}', flush=True)
    except Exception as e:
        print(f'[AVISO] Acelerador indisponível ({e}), usando PyTorch', flush=True)
        model_emb = _build_model()
        _emb_fn   = _embedding

    yolo = YOLO('yolo11n.pt')
    ref_emb = np.array(ref_embedding)

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    posicoes = []       # (x_rel, y_rel) em [0, 1]
    frame_idx = 0
    deteccoes_total = 0
    matches_total = 0

    state.update({
        'status': 'rodando', 'progresso': 0,
        'frame': 0, 'total_frames': total_frames, 'matches': 0,
    })

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1

        # Atualizar progresso a cada 30 frames
        if frame_idx % 30 == 0:
            state['progresso'] = int(frame_idx / total_frames * 100)
            state['frame'] = frame_idx

        # Pular frames para desempenho
        if frame_idx % SKIP_FRAMES != 0:
            continue

        results = yolo(frame, classes=[0], verbose=False)[0]

        # Preview: cópia anotada do frame atual
        preview = frame.copy()
        preview_path = state.get('preview_path', '/tmp/atleta_preview.jpg')

        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            deteccoes_total += 1
            emb = _emb_fn(model_emb, crop)
            sim = float(np.dot(emb, ref_emb))   # cosine (vetores já L2-norm)

            matched = sim >= SIMILARITY_THRESHOLD

            # ── Desenhar caixa no preview ──
            if matched:
                # Âmbar sólido + label em destaque
                cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 180, 255), 3)
                label = f'MATCH  {sim:.2f}'
                lw, lh = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                cv2.rectangle(preview, (x1, y1 - lh - 10), (x1 + lw + 8, y1), (0, 140, 220), -1)
                cv2.putText(preview, label, (x1 + 4, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            else:
                # Cinza fino + score pequeno
                cv2.rectangle(preview, (x1, y1), (x2, y2), (160, 160, 160), 1)
                cv2.putText(preview, f'{sim:.2f}', (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

            if matched:
                cx = ((x1 + x2) / 2) / w
                cy = ((y1 + y2) / 2) / h
                posicoes.append({
                    'x': round(cx, 4),
                    'y': round(cy, 4),
                    'frame': frame_idx,
                    'ts': round(frame_idx / fps, 2),
                })
                matches_total += 1
                state['matches'] = matches_total

        # HUD no canto superior
        hud = f'Frame {frame_idx}/{total_frames}  |  Matches: {matches_total}  |  Limiar: {SIMILARITY_THRESHOLD}'
        cv2.rectangle(preview, (0, 0), (len(hud) * 10 + 16, 30), (0, 0, 0), -1)
        cv2.putText(preview, hud, (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 220, 60), 1)

        # Salvar preview (reduzir resolucao para agilizar transferência)
        ph = 360
        pw = int(w * ph / h)
        small = cv2.resize(preview, (pw, ph))
        cv2.imwrite(preview_path, small, [cv2.IMWRITE_JPEG_QUALITY, 70])

    cap.release()

    # Não setar 'concluido' aqui — app_times.py faz isso após gerar o heatmap
    state.update({'progresso': 99, 'frame': frame_idx})

    return {
        'posicoes': posicoes,
        'total_frames': total_frames,
        'fps': fps,
        'video_w': w,
        'video_h': h,
        'matches': matches_total,
        'deteccoes': deteccoes_total,
    }


# ─── Zonas do campo ──────────────────────────────────────────────
def calcular_zonas(posicoes: list) -> dict:
    """
    Divide o campo em 9 zonas (3 colunas × 3 linhas):
      Colunas (x): defesa (<0.33) | meio (0.33-0.66) | ataque (>0.66)
      Linhas  (y): esquerda (<0.33) | centro (0.33-0.66) | direita (>0.66)
    Retorna {zona: {count, pct}}.
    """
    zona_keys = [
        'def_esq', 'def_cen', 'def_dir',
        'mei_esq', 'mei_cen', 'mei_dir',
        'ata_esq', 'ata_cen', 'ata_dir',
    ]
    contagem = {k: 0 for k in zona_keys}
    total = len(posicoes)
    if total == 0:
        return {k: {'count': 0, 'pct': 0.0} for k in zona_keys}

    for p in posicoes:
        x, y = p['x'], p['y']
        col = 'def' if x < 0.33 else ('mei' if x < 0.66 else 'ata')
        row = 'esq' if y < 0.33 else ('cen' if y < 0.66 else 'dir')
        contagem[f'{col}_{row}'] += 1

    return {k: {'count': v, 'pct': round(v / total * 100, 1)}
            for k, v in contagem.items()}


# ─── CSV ──────────────────────────────────────────────────────────
def gerar_csv(posicoes: list, output_path: str, nome_atleta: str = '') -> bool:
    """
    Exporta posições para CSV com colunas:
    frame, timestamp_s, x_rel, y_rel, x_metros, y_metros, zona
    Retorna True se gerou.
    """
    if not posicoes:
        return False

    FIELD_W, FIELD_H = 105, 68

    def _zona(x, y):
        col = 'Defesa' if x < 0.33 else ('Meio' if x < 0.66 else 'Ataque')
        row = 'Esq'    if y < 0.33 else ('Cen'  if y < 0.66 else 'Dir')
        return f'{col}-{row}'

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['atleta', 'frame', 'timestamp_s',
                         'x_rel', 'y_rel', 'x_metros', 'y_metros', 'zona'])
        for p in posicoes:
            writer.writerow([
                nome_atleta,
                p['frame'],
                p['ts'],
                p['x'],
                p['y'],
                round(p['x'] * FIELD_W, 2),
                round(p['y'] * FIELD_H, 2),
                _zona(p['x'], p['y']),
            ])
    return True


# ─── Heatmap ──────────────────────────────────────────────────────
def gerar_heatmap(posicoes: list, output_path: str, nome_atleta: str = '') -> bool:
    """
    Gera PNG com campo de futebol, mapa de calor e grades de zonas.
    Retorna True se gerou, False se não havia dados.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from scipy.ndimage import gaussian_filter

    if not posicoes:
        return False

    FIELD_W, FIELD_H = 105, 68
    RES = 10
    W, H = FIELD_W * RES, FIELD_H * RES

    # Acumular densidade
    grid = np.zeros((H, W), dtype=float)
    for p in posicoes:
        px = int(np.clip(p['x'] * W, 0, W - 1))
        py = int(np.clip(p['y'] * H, 0, H - 1))
        grid[py, px] += 1

    grid = gaussian_filter(grid, sigma=15)

    fig, ax = plt.subplots(figsize=(13, 8.5))
    fig.patch.set_facecolor('#111111')
    ax.set_facecolor('#1e4620')

    ax.add_patch(patches.Rectangle(
        (0, 0), W, H, linewidth=2, edgecolor='white', facecolor='#1e4620'
    ))

    def ln(x1, y1, x2, y2, **kw):
        ax.plot([x1 * RES, x2 * RES], [y1 * RES, y2 * RES],
                color='white', linewidth=1.5, alpha=0.8, **kw)

    # Linhas do campo
    ln(0, 0, FIELD_W, 0); ln(0, FIELD_H, FIELD_W, FIELD_H)
    ln(0, 0, 0, FIELD_H); ln(FIELD_W, 0, FIELD_W, FIELD_H)
    ln(FIELD_W/2, 0, FIELD_W/2, FIELD_H)
    ax.add_patch(plt.Circle(
        (FIELD_W/2*RES, FIELD_H/2*RES), 9.15*RES,
        color='white', fill=False, linewidth=1.5, alpha=0.8))
    AREA_Y1 = (FIELD_H - 40.32) / 2
    AREA_Y2 = (FIELD_H + 40.32) / 2
    ln(0, AREA_Y1, 16.5, AREA_Y1); ln(0, AREA_Y2, 16.5, AREA_Y2)
    ln(16.5, AREA_Y1, 16.5, AREA_Y2)
    ln(FIELD_W, AREA_Y1, FIELD_W-16.5, AREA_Y1)
    ln(FIELD_W, AREA_Y2, FIELD_W-16.5, AREA_Y2)
    ln(FIELD_W-16.5, AREA_Y1, FIELD_W-16.5, AREA_Y2)

    # Heatmap
    if grid.max() > 0:
        ax.imshow(grid, extent=[0, W, H, 0], cmap='hot', alpha=0.70,
                  vmin=0, vmax=grid.max(), aspect='auto', interpolation='bilinear')

    # ── Divisores de zona (3×3) ──
    zonas_info = calcular_zonas(posicoes)
    for xf in [0.33, 0.66]:
        ax.plot([xf*W, xf*W], [0, H], color='#facc15', linewidth=1,
                alpha=0.5, linestyle='--')
    for yf in [0.33, 0.66]:
        ax.plot([0, W], [yf*H, yf*H], color='#facc15', linewidth=1,
                alpha=0.5, linestyle='--')

    # Labels de % por zona
    col_centers = [0.165, 0.495, 0.825]
    row_centers = [0.165, 0.495, 0.825]
    col_labels  = ['def', 'mei', 'ata']
    row_labels  = ['esq', 'cen', 'dir']
    for ci, col in enumerate(col_labels):
        for ri, row in enumerate(row_labels):
            pct = zonas_info.get(f'{col}_{row}', {}).get('pct', 0)
            if pct > 0:
                ax.text(col_centers[ci]*W, row_centers[ri]*H,
                        f'{pct:.0f}%',
                        ha='center', va='center',
                        color='white', fontsize=9, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.2',
                                  facecolor='black', alpha=0.45, edgecolor='none'))

    ax.set_xlim(0, W); ax.set_ylim(H, 0)
    ax.set_aspect('equal'); ax.axis('off')

    titulo = f'Mapa de Calor — {nome_atleta}' if nome_atleta else 'Mapa de Calor'
    ax.set_title(titulo, color='white', fontsize=16, fontweight='bold', pad=14)
    ax.text(W/2, H+6, f'{len(posicoes)} detecções  |  limiar {SIMILARITY_THRESHOLD}',
            ha='center', va='top', color='#9ca3af', fontsize=10)

    plt.tight_layout(pad=0.5)
    plt.savefig(output_path, dpi=120, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f'[OK] Heatmap salvo: {output_path}', flush=True)
    return True
