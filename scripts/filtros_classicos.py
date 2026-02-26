"""
Filtros Clássicos de Visão Computacional
------------------------------------------
Aplica técnicas do curso (Canny, Laplacian, Histograma) para:
  1. Avaliar qualidade de fotos de referência (blur, sem corpo visível)
  2. Classificar time por cor (Random Forest sobre histograma de cor)

Sem GPU — tudo em NumPy/OpenCV/scikit-learn.
"""

import cv2
import numpy as np
from pathlib import Path

# ── Thresholds padrão (ajustáveis) ─────────────────────────────────
BLUR_THRESHOLD        = 80.0   # Laplacian variance < este valor → borrada
EDGE_DENSITY_MIN      = 0.01   # Edge density < este valor → imagem vazia / sem corpo
SKIN_OR_BODY_MIN      = 0.03   # Fração de pixels com saturação alta < este → fundo/puro

# ── Utilitários de leitura ──────────────────────────────────────────

def read_image(path: Path):
    """Lê imagem suportando caminhos com caracteres Unicode."""
    img = cv2.imread(str(path))
    if img is None:
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return img


# ══════════════════════════════════════════════════════════════════
# 1. QUALIDADE DE FOTO (blur + conteúdo)
# ══════════════════════════════════════════════════════════════════

def blur_score(img: np.ndarray) -> float:
    """
    Variância do Laplacian (quanto mais alta, mais nítida).
    Fotos borradas têm variância baixa porque não têm bordas definidas.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def edge_density(img: np.ndarray,
                 t1: int = 50, t2: int = 150) -> float:
    """
    Proporção de pixels de borda detectados pelo Canny.
    Fotos sem corpo/conteúdo têm pouquíssimas bordas.
    """
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, t1, t2)
    return float(np.sum(edges > 0)) / edges.size


def corpo_visivel(img: np.ndarray) -> float:
    """
    Estima fração de pixels com saturação alta (uniforme, pele, etc.).
    Imagens quase totalmente escuras/brancas têm valor muito baixo.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    return float(np.mean(sat > 30) )   # pixels com S > 30/255


def avaliar_qualidade(img_path: Path) -> dict:
    """
    Retorna um dicionário com scores e veredito de qualidade.

    Retorno:
        {
          'blur':       float,   # variância Laplacian (>80 = nítida)
          'edges':      float,   # densidade de bordas Canny
          'corpo':      float,   # fração de pixels coloridos
          'score':      float,   # score composto 0-100
          'ok':         bool,    # True = foto de boa qualidade
          'motivo':     str      # se não ok, explica por quê
        }
    """
    img = read_image(img_path)
    if img is None:
        return {'ok': False, 'motivo': 'erro_leitura', 'score': 0,
                'blur': 0, 'edges': 0, 'corpo': 0}

    # Redimensiona para 128×128 para consistência / velocidade
    img_s = cv2.resize(img, (128, 128))

    b  = blur_score(img_s)
    e  = edge_density(img_s)
    c  = corpo_visivel(img_s)

    # Score composto ponderado (0–100)
    score = (
        min(b / 300.0, 1.0) * 50 +   # blur (peso 50)
        min(e / 0.05,  1.0) * 30 +   # bordas (peso 30)
        min(c / 0.30,  1.0) * 20     # corpo (peso 20)
    ) * 100 / 100

    # Veredito
    ok = True
    motivo = ''
    if b < BLUR_THRESHOLD:
        ok = False
        motivo = f'borrada (laplacian={b:.0f}<{BLUR_THRESHOLD})'
    elif e < EDGE_DENSITY_MIN:
        ok = False
        motivo = f'sem_corpo (edges={e:.4f}<{EDGE_DENSITY_MIN})'
    elif c < SKIN_OR_BODY_MIN:
        ok = False
        motivo = f'fundo_limpo (corpo={c:.4f}<{SKIN_OR_BODY_MIN})'

    return {
        'blur': round(b, 2),
        'edges': round(e, 5),
        'corpo': round(c, 4),
        'score': round(score, 1),
        'ok': ok,
        'motivo': motivo
    }


def filtrar_pasta(pasta: Path,
                  apenas_ruins: bool = True) -> list[dict]:
    """
    Varre todas as imagens de uma pasta e retorna resultados de qualidade.

    Args:
        pasta:        Caminho da pasta (ex: atleta_refs/Vini Nunes)
        apenas_ruins: Se True, retorna só as fotos com ok=False

    Retorno:
        Lista de { 'arquivo', 'blur', 'edges', 'corpo', 'score', 'ok', 'motivo' }
    """
    exts = {'.jpg', '.jpeg', '.png', '.bmp'}
    resultados = []
    for p in sorted(pasta.iterdir()):
        if p.suffix.lower() not in exts:
            continue
        r = avaliar_qualidade(p)
        r['arquivo'] = p.name
        if apenas_ruins and r['ok']:
            continue
        resultados.append(r)
    # Ordena do pior ao melhor
    resultados.sort(key=lambda x: x['score'])
    return resultados


# ══════════════════════════════════════════════════════════════════
# 2. CLASSIFICAÇÃO DE TIME POR COR (Random Forest / histograma)
# ══════════════════════════════════════════════════════════════════

def extrair_histograma_cor(img: np.ndarray, bins: int = 16) -> np.ndarray:
    """
    Extrai histograma de cor HSV normalizado como vetor de features.
    16 bins × 3 canais = 48 features.
    """
    img_s = cv2.resize(img, (64, 64))
    hsv   = cv2.cvtColor(img_s, cv2.COLOR_BGR2HSV)
    feats = []
    for ch in range(3):
        hist = cv2.calcHist([hsv], [ch], None, [bins], [0, 256]).flatten()
        hist = hist / (hist.sum() + 1e-7)
        feats.append(hist)
    return np.concatenate(feats)


def treinar_classificador_time(crops_por_time: dict[str, list[Path]]):
    """
    Treina Random Forest para classificar time por cor uniforme.

    Args:
        crops_por_time: { 'time_azul': [Path, ...], 'time_preto': [Path, ...] }

    Retorno:
        (clf, scaler, classes) ou (None, None, None) se dados insuficientes
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler

    X, y = [], []
    for time_nome, caminhos in crops_por_time.items():
        for p in caminhos:
            img = read_image(p)
            if img is None:
                continue
            X.append(extrair_histograma_cor(img))
            y.append(time_nome)

    if len(set(y)) < 2 or len(X) < 10:
        return None, None, None

    X = np.array(X)
    y = np.array(y)

    scaler = StandardScaler()
    X_sc   = scaler.fit_transform(X)

    clf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    clf.fit(X_sc, y)

    acc = clf.score(X_sc, y) * 100
    print(f"[classificador_time] Treino: {len(X)} crops, {len(set(y))} classes, acc={acc:.1f}%")
    return clf, scaler, list(clf.classes_)


def classificar_crop_time(img: np.ndarray, clf, scaler) -> tuple[str, float]:
    """
    Classifica um crop BGR e retorna (time, confiança).
    """
    feats  = extrair_histograma_cor(img).reshape(1, -1)
    feats_sc = scaler.transform(feats)
    pred   = clf.predict(feats_sc)[0]
    proba  = clf.predict_proba(feats_sc)[0].max()
    return pred, float(proba)


# ══════════════════════════════════════════════════════════════════
# 3. DESCRITORES DE AÇÃO (para acoes.py)
# ══════════════════════════════════════════════════════════════════

def extrair_features_acao(img: np.ndarray) -> np.ndarray:
    """
    Extrai 10 features rápidas de um crop para classificação de ação:
      0-2  : Cor média (B, G, R)
      3-5  : Desvio de cor (B, G, R)
      6    : Edge density (Canny)
      7    : Aspect ratio do bounding box real (detecção de contorno)
      8    : Posição vertical do centróide normalizada (0=topo, 1=base)
      9    : Fração de pixels em movimento (estimativa por saturação)
    """
    img_s = cv2.resize(img, (64, 96))

    # Cor
    mean_color = img_s.mean(axis=(0, 1))
    std_color  = img_s.std(axis=(0, 1))

    # Bordas
    gray  = cv2.cvtColor(img_s, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    e_density = float(np.sum(edges > 0)) / edges.size

    # Aspect ratio do contorno principal
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        c    = max(contours, key=cv2.contourArea)
        x, y_c, w, h = cv2.boundingRect(c)
        aspect = w / (h + 1e-7)
        centroid_y = (y_c + h / 2) / img_s.shape[0]
    else:
        aspect    = 0.5
        centroid_y = 0.5

    # Saturação (movimento / uniformes coloridos)
    hsv = cv2.cvtColor(img_s, cv2.COLOR_BGR2HSV)
    sat_frac = float(np.mean(hsv[:, :, 1] > 40))

    return np.concatenate([
        mean_color, std_color,
        [e_density, aspect, centroid_y, sat_frac]
    ])


# ─── Persistência do classificador RF com joblib ─────────────────────────────
def salvar_classificador(clf, scaler, path) -> None:
    """
    Salva o modelo Random Forest + scaler em disco.
    `path` deve ser um str ou Path (e.g. 'models/rf_time.joblib').
    """
    import joblib
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'clf': clf, 'scaler': scaler, 'classes': list(clf.classes_)}, path)
    print(f'[RF] Classificador salvo → {path}')


def carregar_classificador(path):
    """
    Carrega clf e scaler salvos com `salvar_classificador`.
    Retorna (None, None) se o arquivo não existir.
    """
    import joblib
    from pathlib import Path
    path = Path(path)
    if not path.exists():
        print(f'[RF] Arquivo não encontrado: {path}')
        return None, None
    d = joblib.load(path)
    print(f'[RF] Classificador carregado ← {path}  (classes: {d["classes"]})')
    return d['clf'], d['scaler']


# ── Teste rápido ────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        pasta = Path(sys.argv[1])
        print(f"\nFiltrando: {pasta}")
        ruins = filtrar_pasta(pasta)
        print(f"{len(ruins)} fotos com baixa qualidade:\n")
        for r in ruins[:10]:
            print(f"  {r['arquivo']:40s}  score={r['score']:5.1f}  {r['motivo']}")
    else:
        print("Uso: python filtros_classicos.py <pasta_atleta>")
