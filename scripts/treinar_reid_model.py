"""
Script para treinar modelo ReID personalizado usando Torchreid
Treina com suas fotos classificadas para reconhecimento preciso dos jogadores
"""

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, Sampler
from torchvision import transforms, models
from pathlib import Path
import json
import os
import random
from PIL import Image
import numpy as np
from collections import defaultdict, Counter
import shutil

# Configurações
DATASET_DIR = Path('dataset_reid')
EMBEDDINGS_DIR = Path('embeddings_reid')
MODEL_PATH = 'modelo_reid_terca.pth'
BATCH_SIZE = 32
EPOCHS = 50
LEARNING_RATE = 0.001
IMG_SIZE = (256, 128)  # Altura x Largura padrão ReID

# Verificar GPU
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"\n🖥️  Usando dispositivo: {device}")
if device.type == 'cuda':
    print(f"   GPU: {torch.cuda.get_device_name(0)}")
else:
    print("   ⚠️  CPU detectada - treinamento será mais lento")


class JogadoresDataset(Dataset):
    """Dataset customizado para jogadores"""
    
    def __init__(self, root_dir, transform=None):
        self.root_dir = Path(root_dir)
        self.transform = transform
        self.samples = []
        self.classes = []
        self.class_to_idx = {}
        
        # Escanear pastas
        jogador_dirs = sorted([d for d in self.root_dir.iterdir() if d.is_dir()])
        
        for idx, jogador_dir in enumerate(jogador_dirs):
            jogador_nome = jogador_dir.name
            self.classes.append(jogador_nome)
            self.class_to_idx[jogador_nome] = idx
            
            # Adicionar todas as imagens desse jogador
            for img_path in jogador_dir.glob('*.jpg'):
                self.samples.append((str(img_path), idx))
        
        print(f"✓ Dataset carregado:")
        print(f"  - {len(self.classes)} jogadores")
        print(f"  - {len(self.samples)} imagens totais")

    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        
        # Carregar imagem
        image = Image.open(img_path).convert('RGB')
        
        if self.transform:
            image = self.transform(image)
        
        return image, label


class ReIDModel(nn.Module):
    """Modelo ReID baseado em ResNet50"""
    
    def __init__(self, num_classes, embedding_size=512):
        super(ReIDModel, self).__init__()
        
        # Backbone: ResNet50 pré-treinado
        resnet = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
        
        # Remover camada FC original
        self.backbone = nn.Sequential(*list(resnet.children())[:-1])
        
        # Pooling global
        self.global_pool = nn.AdaptiveAvgPool2d((1, 1))
        
        # Camadas de embedding
        self.embedding = nn.Sequential(
            nn.Linear(2048, embedding_size),
            nn.BatchNorm1d(embedding_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5)
        )
        
        # Classificador
        self.classifier = nn.Linear(embedding_size, num_classes)
        
    def forward(self, x):
        # Extração de features
        x = self.backbone(x)
        x = self.global_pool(x)
        x = torch.flatten(x, 1)
        
        # Embedding
        embedding = self.embedding(x)
        
        # Classificação
        logits = self.classifier(embedding)
        
        return logits, embedding


def stratified_split(dataset, val_ratio=0.2):
    """Split estratificado: garante representação de cada classe na validação."""
    class_indices = defaultdict(list)
    for idx, (_, label) in enumerate(dataset.samples):
        class_indices[label].append(idx)

    train_indices, val_indices = [], []
    for label, indices in class_indices.items():
        random.shuffle(indices)
        n_val = max(1, int(len(indices) * val_ratio))
        val_indices.extend(indices[:n_val])
        train_indices.extend(indices[n_val:])

    return train_indices, val_indices


class PKSampler(Sampler):
    """Amostra P classes × K imagens por batch — necessário para Triplet Loss."""

    def __init__(self, dataset, indices, P=8, K=4):
        self.P = P
        self.K = K
        class_to_indices = defaultdict(list)
        for i in indices:
            _, label = dataset.samples[i]
            class_to_indices[label].append(i)
        # Manter apenas classes com pelo menos 2 imagens
        self.class_to_indices = {c: v for c, v in class_to_indices.items() if len(v) >= 2}
        self.classes = list(self.class_to_indices.keys())

    def __iter__(self):
        batches = []
        n_batches = max(1, len(self.classes) // self.P)
        for _ in range(n_batches):
            selected = random.sample(self.classes, min(self.P, len(self.classes)))
            batch = []
            for cls in selected:
                imgs = self.class_to_indices[cls]
                batch.extend(random.choices(imgs, k=self.K))
            batches.append(batch)
        return iter(batches)

    def __len__(self):
        return max(1, len(self.classes) // self.P)


def batch_hard_triplet_loss(embeddings, labels, margin=0.3):
    """Triplet Loss com hard mining dentro do batch."""
    dist = torch.cdist(embeddings, embeddings, p=2)   # [N, N]
    N = embeddings.size(0)
    dev = embeddings.device
    loss = torch.tensor(0.0, device=dev)
    count = 0
    for i in range(N):
        pos_mask = (labels == labels[i])
        neg_mask = (labels != labels[i])
        pos_mask[i] = False
        if pos_mask.sum() == 0 or neg_mask.sum() == 0:
            continue
        hardest_pos = dist[i][pos_mask].max()
        hardest_neg = dist[i][neg_mask].min()
        loss += torch.clamp(hardest_pos - hardest_neg + margin, min=0.0)
        count += 1
    return loss / max(count, 1)


def preparar_dataset():
    """Prepara o dataset dividindo em treino/validação"""
    
    if not DATASET_DIR.exists():
        print(f"\n❌ Dataset não encontrado em {DATASET_DIR}/")
        print("   Execute: python exportar_reid.py")
        return False
    
    # Verificar quantidade mínima de imagens
    metadata_file = DATASET_DIR / 'metadata.json'
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)
        
        jogadores_poucos = [j for j, c in metadata['jogadores'].items() if c < 5]
        
        if jogadores_poucos:
            print(f"\n⚠️  ATENÇÃO: Jogadores com poucas imagens (< 5):")
            for j in jogadores_poucos:
                print(f"   - {j}: {metadata['jogadores'][j]} imagens")
            print("\n💡 Recomendação: Capture mais imagens rodando: python script.py")
            
            resposta = input("\nContinuar mesmo assim? (s/n): ")
            if resposta.lower() != 's':
                return False
    
    return True


def treinar_modelo():
    """Treina o modelo ReID"""
    
    print("\n" + "="*70)
    print("🚀 TREINAMENTO DE MODELO REID - TERÇA NOBRE")
    print("="*70 + "\n")
    
    # Verificar dataset
    if not preparar_dataset():
        return
    
    # Transformações SEM flip horizontal (inversão troca lado do corpo, prejudica ReID)
    transform_train = transforms.Compose([
        transforms.Resize(IMG_SIZE),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                           std=[0.229, 0.224, 0.225])
    ])

    transform_val = transforms.Compose([
        transforms.Resize(IMG_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                           std=[0.229, 0.224, 0.225])
    ])

    # Carregar dataset
    dataset = JogadoresDataset(DATASET_DIR, transform=transform_train)
    val_dataset_raw = JogadoresDataset(DATASET_DIR, transform=transform_val)

    # Split estratificado (garante representação de cada classe na validação)
    train_indices, val_indices = stratified_split(dataset, val_ratio=0.2)
    train_dataset = torch.utils.data.Subset(dataset, train_indices)
    val_dataset = torch.utils.data.Subset(val_dataset_raw, val_indices)

    print(f"\n📊 Divisão estratificada:")
    print(f"   Treino:    {len(train_indices)} imagens")
    print(f"   Validação: {len(val_indices)} imagens")

    # PKSampler: P classes × K imagens por batch (requerido para Triplet Loss)
    P = min(len(dataset.classes), 8)
    K = 4
    pk_sampler = PKSampler(dataset, train_indices, P=P, K=K)

    train_loader = DataLoader(
        train_dataset,
        batch_sampler=pk_sampler,
        num_workers=4 if device.type == 'cuda' else 0
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=4 if device.type == 'cuda' else 0
    )

    # Criar modelo
    num_classes = len(dataset.classes)
    model = ReIDModel(num_classes).to(device)

    print(f"\n🧠 Modelo criado:")
    print(f"   Classes: {num_classes} jogadores")
    print(f"   Parâmetros: {sum(p.numel() for p in model.parameters()):,}")
    print(f"   Batch: P={P} classes × K={K} imagens = {P*K}")

    # Triplet Loss (batch hard mining) + Cross-Entropy auxiliar
    ce_loss_fn = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=20, gamma=0.1)

    # Treinamento
    print(f"\n🏋️  Iniciando treinamento ({EPOCHS} épocas)...\n")

    best_acc = 0.0
    history = {'train_loss': [], 'train_acc': [], 'val_loss': [], 'val_acc': []}

    for epoch in range(EPOCHS):
        # ===== TREINO =====
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)

            optimizer.zero_grad()

            logits, embeddings = model(images)

            # Triplet Loss com batch hard mining
            t_loss = batch_hard_triplet_loss(embeddings, labels, margin=0.3)
            # Cross-Entropy auxiliar (estabiliza início do treino)
            ce_loss = ce_loss_fn(logits, labels)
            loss = t_loss + 0.5 * ce_loss

            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            _, predicted = logits.max(1)
            train_total += labels.size(0)
            train_correct += predicted.eq(labels).sum().item()

        train_loss /= max(len(train_loader), 1)
        train_acc = 100. * train_correct / max(train_total, 1)

        # ===== VALIDAÇÃO =====
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)

                logits, _ = model(images)
                loss = ce_loss_fn(logits, labels)

                val_loss += loss.item()
                _, predicted = logits.max(1)
                val_total += labels.size(0)
                val_correct += predicted.eq(labels).sum().item()

        val_loss /= max(len(val_loader), 1)
        val_acc = 100. * val_correct / max(val_total, 1)

        scheduler.step()

        history['train_loss'].append(train_loss)
        history['train_acc'].append(train_acc)
        history['val_loss'].append(val_loss)
        history['val_acc'].append(val_acc)

        print(f"Época [{epoch+1:2d}/{EPOCHS}] | "
              f"Loss: {train_loss:.4f} | Acc Treino: {train_acc:.2f}% | "
              f"Acc Val: {val_acc:.2f}%")

        # Salvar melhor modelo
        if val_acc > best_acc:
            best_acc = val_acc
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_acc': val_acc,
                'classes': dataset.classes,
                'class_to_idx': dataset.class_to_idx
            }, MODEL_PATH)
            print(f"   ✓ Melhor modelo salvo! (Acc: {val_acc:.2f}%)")
    
    # Resultados finais
    print("\n" + "="*70)
    print("✓ TREINAMENTO CONCLUÍDO!")
    print("="*70)
    print(f"\n📊 Resultados:")
    print(f"   Melhor acurácia validação: {best_acc:.2f}%")
    print(f"   Modelo salvo em: {MODEL_PATH}")
    print(f"\n💡 Próximo passo: python gerar_embeddings.py")
    
    # Salvar histórico
    with open('historico_treino.json', 'w') as f:
        json.dump(history, f, indent=4)
    
    print(f"   Histórico salvo em: historico_treino.json")


def gerar_embeddings():
    """Gera embeddings de todos os jogadores para reconhecimento rápido"""
    
    print("\n" + "="*70)
    print("🔍 GERANDO EMBEDDINGS DOS JOGADORES")
    print("="*70 + "\n")
    
    # Carregar modelo treinado
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Modelo não encontrado: {MODEL_PATH}")
        print("   Execute: python treinar_reid_model.py")
        return
    
    checkpoint = torch.load(MODEL_PATH, map_location=device)
    classes = checkpoint['classes']
    class_to_idx = checkpoint['class_to_idx']
    
    # Criar modelo
    model = ReIDModel(len(classes)).to(device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    print(f"✓ Modelo carregado (Acc: {checkpoint['val_acc']:.2f}%)")
    print(f"✓ Jogadores: {len(classes)}\n")
    
    # Transformação
    transform = transforms.Compose([
        transforms.Resize(IMG_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                           std=[0.229, 0.224, 0.225])
    ])
    
    # Gerar embeddings para cada jogador
    EMBEDDINGS_DIR.mkdir(exist_ok=True)
    embeddings_database = {}
    
    for jogador in classes:
        jogador_dir = DATASET_DIR / jogador
        embeddings_jogador = []
        
        print(f"Processando: {jogador}...")
        
        for img_path in jogador_dir.glob('*.jpg'):
            img = Image.open(img_path).convert('RGB')
            img_tensor = transform(img).unsqueeze(0).to(device)
            
            with torch.no_grad():
                _, embedding = model(img_tensor)
                embeddings_jogador.append(embedding.cpu().numpy())
        
        # Média dos embeddings
        avg_embedding = np.mean(embeddings_jogador, axis=0)
        embeddings_database[jogador] = avg_embedding.tolist()
        
        print(f"   ✓ {len(embeddings_jogador)} imagens processadas")
    
    # Salvar database
    database_file = EMBEDDINGS_DIR / 'embeddings_database.json'
    with open(database_file, 'w') as f:
        json.dump(embeddings_database, f, indent=4)
    
    # Salvar metadados
    metadata = {
        'model_path': MODEL_PATH,
        'num_jogadores': len(classes),
        'jogadores': classes,
        'embedding_size': 512,
        'accuracy': checkpoint['val_acc']
    }
    
    metadata_file = EMBEDDINGS_DIR / 'metadata.json'
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=4)
    
    print("\n" + "="*70)
    print("✓ EMBEDDINGS GERADOS COM SUCESSO!")
    print("="*70)
    print(f"\n📁 Arquivos salvos em: {EMBEDDINGS_DIR}/")
    print(f"   - embeddings_database.json ({len(classes)} jogadores)")
    print(f"   - metadata.json")
    print(f"\n💡 Próximo passo: python reconhecer_com_reid.py")


if __name__ == '__main__':
    import sys
    
    print("\n🤖 SISTEMA REID - TERÇA NOBRE\n")
    print("Escolha uma opção:")
    print("1. Treinar modelo ReID")
    print("2. Gerar embeddings dos jogadores")
    print("3. Fazer ambos (treinar + gerar)")
    
    opcao = input("\nOpção (1/2/3): ").strip()
    
    if opcao == '1':
        treinar_modelo()
    elif opcao == '2':
        gerar_embeddings()
    elif opcao == '3':
        treinar_modelo()
        print("\n" + "⏳"*35 + "\n")
        gerar_embeddings()
    else:
        print("❌ Opção inválida!")
