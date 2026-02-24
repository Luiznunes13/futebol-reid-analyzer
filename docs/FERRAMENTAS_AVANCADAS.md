# 🚀 Ferramentas Avançadas - Terça Nobre

Sistema completo para análise de jogos de futebol com rastreamento, reconhecimento e análise de performance.

## 📦 Ferramentas Disponíveis

### 1️⃣ Exportação para ReID (Re-Identification)
**Arquivo:** `exportar_reid.py`

Organiza as imagens classificadas no formato ideal para sistemas de Re-Identification.

**Como usar:**
```bash
python exportar_reid.py
```

**O que faz:**
- ✅ Cria pasta `dataset_reid/` com estrutura organizada
- ✅ Cada jogador tem sua própria pasta
- ✅ Gera arquivo `metadata.json` com estatísticas
- ✅ Cria `README.md` com documentação
- ✅ Análise de balanceamento do dataset

**Estrutura gerada:**
```
dataset_reid/
├── metadata.json
├── README.md
├── André/
│   ├── andre_001.jpg
│   ├── andre_002.jpg
│   └── ...
├── João Pedro/
│   ├── joao_pedro_001.jpg
│   └── ...
└── ...
```

**Uso com PyTorch:**
```python
from torchvision import datasets, transforms

transform = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
])

dataset = datasets.ImageFolder('dataset_reid/', transform=transform)
```

---

### 2️⃣ Análise de Trajetória e Distância
**Arquivo:** `analisar_trajetoria.py`

Calcula a distância percorrida por cada jogador durante o jogo.

**Como usar:**
```bash
python analisar_trajetoria.py
```

**O que faz:**
- ✅ Rastreia os jogadores frame a frame
- ✅ Calcula distância percorrida em metros
- ✅ Desenha trajetórias em tempo real
- ✅ Gera relatório por time
- ✅ Ranking de distância percorrida

**Exemplo de saída:**
```
🔵 TIME AZUL:
   1. João Pedro         → 3250.45m (3.25km)
   2. André              → 2890.12m (2.89km)
   3. Gustavo            → 2456.78m (2.46km)

⚫ TIME PRETO:
   1. Juninho            → 3100.00m (3.10km)
   2. Wilson             → 2780.50m (2.78km)
```

**Configurações importantes:**
- `LARGURA_CAMPO_METROS = 68` - Ajuste para seu campo
- `COMPRIMENTO_CAMPO_METROS = 40` - Ajuste para seu campo

---

### 3️⃣ Sincronização de Câmeras
**Arquivo:** `sincronizar_cameras.py`

Gerencia o mapeamento de IDs entre as duas câmeras.

**Como usar:**
```bash
python sincronizar_cameras.py
```

**Menu interativo:**
```
1. Listar sincronias existentes
2. Adicionar sincronia manual
3. Remover sincronia
4. Buscar por jogador
5. Sugerir sincronias automáticas  ← RECOMENDADO!
6. Exportar relatório
0. Sair
```

**O que resolve:**
- ❓ ID 42 da câmera ESQ = ID 10 da câmera DIR?
- ✅ Sistema mapeia automaticamente baseado nas classificações
- ✅ Permite unificar métricas das duas câmeras
- ✅ Evita contar o mesmo jogador duas vezes

**Arquivo gerado:** `sincronia_cameras.json`

**Exemplo:**
```json
{
    "ESQ_42_DIR_10": {
        "id_esq": "42",
        "id_dir": "10",
        "jogador": "João Pedro"
    }
}
```

---

## 🎯 Fluxo de Trabalho Recomendado

### Passo 1: Capturar Imagens
```bash
python script.py
```
- Processa vídeos e extrai fotos dos jogadores
- Com detecção de rosto ativada (melhor qualidade)

### Passo 2: Classificar Jogadores
```bash
python app_times.py
```
- Abra http://localhost:5001
- Use "🚀 Classificação Rápida"
- Classifique todos os IDs

### Passo 3: Exportar Dataset ReID
```bash
python exportar_reid.py
```
- Organiza imagens por jogador
- Pronto para treinar modelos de ReID

### Passo 4: Sincronizar Câmeras
```bash
python sincronizar_cameras.py
```
- Escolha opção 5 (Sugestões automáticas)
- Sistema mapeia IDs entre câmeras

### Passo 5: Analisar Trajetórias
```bash
python analisar_trajetoria.py
```
- Calcula distâncias percorridas
- Gera relatório de performance

### Passo 6: Reconhecimento Automático
```bash
python reconhecer_por_time.py
```
- Identifica jogadores em novos vídeos
- Mostra nomes em tempo real

---

## 🔧 Configurações Importantes

### Detecção de Rosto (script.py)
```python
USE_FACE_DETECTION = True  # Salvar apenas com rosto visível
CONFIDENCE_THRESHOLD = 0.5  # Confiança mínima YOLO
```

### Campo de Futebol (analisar_trajetoria.py)
```python
LARGURA_CAMPO_METROS = 68   # Largura real do campo
COMPRIMENTO_CAMPO_METROS = 40  # Comprimento real
```

### Reconhecimento (reconhecer_por_time.py)
```python
SIMILARITY_THRESHOLD = 0.65  # Limiar de similaridade
IMG_SIZE = (128, 256)  # Tamanho das features
```

---

## 📊 Arquivos Gerados

| Arquivo | Descrição |
|---------|-----------|
| `jogadores_com_ids.json` | Classificações ID → Nome |
| `times.json` | Configuração dos times |
| `sincronia_cameras.json` | Mapeamento entre câmeras |
| `dataset_reid/` | Dataset organizado para ReID |
| `relatorio_sincronias.md` | Relatório de sincronias |

---

## 💡 Próximos Passos

### Dashboard Web Completo
Criar dashboard Flask/FastAPI que mostra em tempo real:
- 📊 Estatísticas de distância
- 🎯 Mapa de calor de posições
- ⚡ Velocidade média e máxima
- 📈 Gráficos de evolução

### Machine Learning Avançado
- Treinar modelo DeepSORT com seu dataset
- Usar Pose Estimation (MediaPipe) para análise de movimentos
- Detecção de eventos (chute, passe, falta)

### Análise Tática
- Formação do time (4-4-2, 3-5-2, etc)
- Análise de passes
- Zonas de influência de cada jogador

---

## 🐛 Troubleshooting

### "Não encontrou rostos"
- Ajuste `minNeighbors` no Haar Cascade
- Use `USE_FACE_DETECTION = False` para desativar

### "Distâncias irrealistas"
- Calibre `ESCALA_X` e `ESCALA_Y` 
- Aumente filtro de teleporte (linha `if distancia < 5`)

### "Sincronias não sugeridas"
- Certifique-se que o mesmo jogador foi classificado em ambas câmeras
- Verifique nomenclatura (nomes devem ser idênticos)

---

## 🤝 Contribuindo

Melhorias bem-vindas:
- Interface web para sincronização
- Exportação para formatos de análise tática
- Integração com GPS/IMU para validação
- Suporte para mais de 2 câmeras

---

## 📝 Licença

Projeto pessoal - Terça Nobre
