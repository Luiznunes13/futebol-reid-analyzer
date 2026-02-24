"""
Acelerador de inferência via OpenVINO (Intel UHD GPU + CPU otimizado).

Exports (feitos uma vez na primeira execução):
  - scripts/reid_backbone.onnx  → ResNet50 backbone para ReID

Hierarquia de dispositivos:
  ReID  → GPU > CPU  (OpenVINO)
  YOLO  → PyTorch CPU (mais rápido que OV para este modelo)
"""

from __future__ import annotations
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms

SCRIPTS_DIR = Path(__file__).parent
ONNX_REID   = SCRIPTS_DIR / 'reid_backbone.onnx'
IMG_SIZE    = (256, 128)

_transform = transforms.Compose([
    transforms.Resize(IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


# ─── Export helper ────────────────────────────────────────────────
def _exportar_reid_onnx() -> None:
    """Exporta ResNet50 backbone para ONNX (executado só uma vez)."""
    from torchvision import models
    print('[ACELERADOR] Exportando ResNet50 → ONNX ...', flush=True)
    resnet   = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    backbone = nn.Sequential(*list(resnet.children())[:-1]).eval()
    dummy    = torch.zeros(1, 3, IMG_SIZE[0], IMG_SIZE[1])
    torch.onnx.export(
        backbone, dummy, str(ONNX_REID),
        opset_version=11,
        input_names=['input'], output_names=['output'],
    )
    print(f'[ACELERADOR] ONNX salvo → {ONNX_REID}', flush=True)


# ─── OpenVINO ReID ────────────────────────────────────────────────
class ReIDAccelerado:
    """
    Extrator de embeddings ReID com OpenVINO.
    Usa GPU Intel se disponível, cai para CPU OpenVINO otimizado.
    """

    def __init__(self):
        import openvino as ov

        if not ONNX_REID.exists():
            _exportar_reid_onnx()

        core    = ov.Core()
        devices = core.available_devices
        device  = 'GPU' if 'GPU' in devices else 'CPU'
        print(f'[ACELERADOR] ReID compilando para {device} '
              f'(disponíveis: {devices}) ...', flush=True)

        t0    = time.perf_counter()
        model = core.read_model(str(ONNX_REID))
        self._infer = core.compile_model(model, device).create_infer_request()
        self._device = device
        print(f'[ACELERADOR] ReID pronto em {device} '
              f'({(time.perf_counter()-t0)*1000:.0f} ms de compilação)', flush=True)

    def embedding(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Retorna embedding L2-normalizado dado um crop em BGR."""
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        t   = _transform(img).unsqueeze(0).numpy()          # (1,3,H,W) float32
        self._infer.infer({'input': t})
        out  = self._infer.get_output_tensor(0).data.copy()
        emb  = out.squeeze()
        norm = np.linalg.norm(emb)
        return emb / (norm + 1e-8)

    @property
    def device(self) -> str:
        return self._device


# ─── Singleton por processo ────────────────────────────────────────
_reid_instance: ReIDAccelerado | None = None

def get_reid() -> ReIDAccelerado:
    """Retorna instância singleton do extrator ReID acelerado."""
    global _reid_instance
    if _reid_instance is None:
        _reid_instance = ReIDAccelerado()
    return _reid_instance


def reset_reid() -> None:
    """Força recriação do modelo (útil após nova exportação)."""
    global _reid_instance
    _reid_instance = None
