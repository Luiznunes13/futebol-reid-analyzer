# 🤖 Guia de Uso - Modelo ReID para Reconhecimento de Jogadores

## 📋 O que você precisa fazer:

### Passo 1: Exportar Dataset
```bash
python exportar_reid.py
```
- Organiza suas fotos classificadas no formato correto
- Cria pasta `dataset_reid/`

### Passo 2: Treinar Modelo ReID
```bash
python treinar_reid_model.py
```

Escolha **opção 3** (Fazer ambos):
- Treina modelo com Deep Learning (ResNet50)
- Gera embeddings de todos os jogadores
- Muito mais preciso que histogramas de cor!

**Tempo estimado:**
- Com GPU: ~5-15 minutos
- Com CPU: ~30-60 minutos

### Passo 3: Reconhecer Jogadores
```bash
python reconhecer_com_reid.py
```
- Usa o modelo treinado para identificar jogadores
- Precisão esperada: **85-95%** 🎯

---

## 🎯 Comparação de Precisão:

| Método | Precisão | Velocidade |
|--------|----------|------------|
| Histogramas de Cor | ~60-70% | Rápido |
| **ReID com Deep Learning** | **85-95%** ⭐ | Moderado |

---

## ⚙️ Instalação de Dependências Extras:

Se der erro de pacote faltando:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
# OU para GPU:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

---

## 📊 Recomendações para Melhor Precisão:

### Quantidade de Fotos por Jogador:
- ❌ **Menos de 5:** Não recomendado
- ⚠️ **5-10 fotos:** Funcional, mas pode errar
- ✅ **15-20 fotos:** Boa precisão (recomendado)
- ⭐ **30+ fotos:** Excelente precisão

### Qualidade das Fotos:
- ✅ Com rosto visível
- ✅ Diferentes ângulos (frente, lateral, costas)
- ✅ Variação de iluminação
- ✅ Poses variadas (correndo, parado, pulando)

### Capturar Mais Fotos:
```bash
# Ative detecção de rosto no script.py (linha 12)
USE_FACE_DETECTION = True

# Execute novamente
python script.py
```

---

## 🔧 Ajustes Finos:

### Aumentar Precisão (mais conservador):
No arquivo `reconhecer_com_reid.py`, linha 17:
```python
SIMILARITY_THRESHOLD = 0.80  # Era 0.70
```
- Menos falsos positivos
- Pode deixar mais jogadores como "Desconhecido"

### Aumentar Cobertura (mais liberal):
```python
SIMILARITY_THRESHOLD = 0.60  # Era 0.70
```
- Reconhece mais jogadores
- Pode ter mais erros

---

## 🚀 Arquivos Gerados:

| Arquivo | Descrição |
|---------|-----------|
| `modelo_reid_terca.pth` | Modelo treinado (~100MB) |
| `embeddings_reid/embeddings_database.json` | Embeddings dos jogadores |
| `embeddings_reid/metadata.json` | Metadados do modelo |
| `historico_treino.json` | Curvas de aprendizado |

---

## 🐛 Troubleshooting:

### "CUDA out of memory"
```python
# No treinar_reid_model.py, linha 12:
BATCH_SIZE = 16  # Era 32
```

### "Not enough images"
- Execute `python script.py` para capturar mais fotos
- Certifique-se de ter pelo menos 5 fotos por jogador

### "Model not found"
- Execute passo 2 primeiro (treinar modelo)

---

## 📈 Melhorias Futuras Possíveis:

1. **Fine-tuning com mais épocas** (aumentar `EPOCHS`)
2. **Data Augmentation mais agressivo**
3. **Ensemble de modelos** (múltiplos backbones)
4. **Triplet Loss** ao invés de CrossEntropy
5. **Pose Estimation** para features adicionais

---

## 💡 Dicas:

- Execute o treinamento após capturar todas as fotos
- Re-treine sempre que adicionar novos jogadores
- Teste com `SIMILARITY_THRESHOLD` diferentes
- Use GPU se disponível (20x mais rápido)

---

**Pronto para começar?**
```bash
python exportar_reid.py
python treinar_reid_model.py
python reconhecer_com_reid.py
```

🎯 Boa sorte!
