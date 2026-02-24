# ⚽ Sistema de Análise de Futebol - Terça Nobre

Sistema completo de rastreamento, reconhecimento e análise de performance de jogadores de futebol usando Computer Vision e Deep Learning.

## 📁 Estrutura do Projeto

```
terça-nobre/
├── 📱 app_times.py           # Interface Web Principal (Flask)
│
├── 📂 api/                   # Backend e Executores
│   ├── executor.py          # Gerenciador de processos
│   └── progress.py          # WebSocket para progresso
│
├── 📂 scripts/               # Scripts Funcionais
│   ├── script.py            # 📸 Capturar imagens dos vídeos
│   ├── setup_times.py       # ⚙️ Configurar times
│   ├── exportar_reid.py     # 📦 Exportar dataset ReID
│   ├── treinar_reid_model.py # 🤖 Treinar modelo Deep Learning
│   ├── reconhecer_por_time.py # 🔍 Reconhecer jogadores (método 1)
│   ├── reconhecer_com_reid.py # 🔍 Reconhecer com ReID (método 2)
│   ├── analisar_trajetoria.py # 📊 Calcular distâncias
│   ├── sincronizar_cameras.py # 🔗 Sincronizar câmeras
│   └── analisar_balanceamento.py # 📈 Estatísticas dataset
│
├── 📂 templates/            # Interface Web (HTML)
│   ├── dashboard.html       # 🏠 Página principal
│   ├── classificar_times.html # 🏷️ Classificação de jogadores
│   └── relatorios.html      # 📊 Relatórios e gráficos
│
├── 📂 static/               # Assets estáticos
│   ├── css/                # Estilos
│   ├── js/                 # JavaScript
│   └── uploads/            # Vídeos enviados
│
├── 📂 jogadores_terca/      # 📸 Fotos extraídas
├── 📂 dataset_reid/         # 📦 Dataset organizado por jogador
├── 📂 docs/                 # 📚 Documentação
│
├── 🔧 times.json            # Configuração dos times
├── 🔧 jogadores_com_ids.json # Classificações ID→Nome
├── 🔧 custom_tracker.yaml   # Configuração ByteTrack
└── 🔧 modelo_reid_terca.pth # Modelo treinado (gerado)
```

## 🚀 Como Usar

### Opção 1: Interface Web (Recomendado)
```bash
python app_times.py
# Acesse: http://localhost:5001
```

### Opção 2: Scripts Individuais
```bash
# Configurar times
python scripts/setup_times.py

# Capturar imagens
python scripts/script.py

# Classificar via web
python app_times.py → http://localhost:5001

# Treinar modelo ReID
python scripts/treinar_reid_model.py

# Reconhecer jogadores
python scripts/reconhecer_por_time.py
# ou
python scripts/reconhecer_com_reid.py

# Analisar trajetórias
python scripts/analisar_trajetoria.py
```

## 📊 Fluxo de Trabalho

1. **Configurar Times** → `setup_times.py`
2. **Capturar Imagens** → `script.py`
3. **Classificar Jogadores** → Interface Web (port 5001)
4. **Exportar Dataset** → `exportar_reid.py`
5. **Treinar Modelo** → `treinar_reid_model.py`
6. **Reconhecer em Vídeos** → `reconhecer_com_reid.py`
7. **Analisar Performance** → `analisar_trajetoria.py`

## 🛠️ Tecnologias

- **Computer Vision:** OpenCV, Ultralytics YOLO
- **Tracking:** ByteTrack (Supervision)
- **Deep Learning:** PyTorch, ResNet50
- **Web:** Flask, Flask-SocketIO
- **Frontend:** HTML5, CSS3, JavaScript, Chart.js

## 📚 Documentação Adicional

- [docs/GUIA_REID.md](docs/GUIA_REID.md) - Guia de treinamento ReID
- [docs/FERRAMENTAS_AVANCADAS.md](docs/FERRAMENTAS_AVANCADAS.md) - Ferramentas extras
- [docs/MELHORIAS.md](docs/MELHORIAS.md) - Melhorias futuras

## 🔮 Roadmap

- [ ] Dashboard web completo
- [ ] Upload de vídeo local
- [ ] Download do YouTube
- [ ] Streaming em tempo real
- [ ] Gerador de highlights
- [ ] API REST

## 📝 Licença

Projeto pessoal - Terça Nobre © 2026
