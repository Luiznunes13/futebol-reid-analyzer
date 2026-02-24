"""
Script para exportar dataset no formato ReID
Organiza as imagens classificadas em pastas por jogador
Formato: dataset_reid/jogador_nome/img_001.jpg
"""

import json
import os
import shutil
from pathlib import Path
from collections import defaultdict

# Configurações
IMGS_DIR = Path('jogadores_terca')
OUTPUT_DIR = Path('dataset_reid')
CLASSIFICACOES_FILE = 'jogadores_com_ids.json'

def exportar_dataset_reid():
    """Exporta imagens classificadas no formato ReID"""
    
    # Carregar classificações
    if not os.path.exists(CLASSIFICACOES_FILE):
        print(f"❌ Arquivo {CLASSIFICACOES_FILE} não encontrado!")
        print("   Execute a classificação primeiro.")
        return
    
    with open(CLASSIFICACOES_FILE, 'r', encoding='utf-8') as f:
        classificacoes = json.load(f)
    
    # Criar diretório de saída
    if OUTPUT_DIR.exists():
        import sys
        if sys.stdin.isatty():
            resposta = input(f"\n⚠️  Pasta {OUTPUT_DIR} já existe. Deseja sobrescrever? (s/n): ")
            if resposta.lower() != 's':
                print("❌ Operação cancelada.")
                return
        else:
            print(f"\n⚠️  Pasta {OUTPUT_DIR} já existe. Sobrescrevendo automaticamente...")
        shutil.rmtree(OUTPUT_DIR)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Agrupar por jogador
    jogadores_imgs = defaultdict(list)
    descartados = 0
    
    for id_num, nome in classificacoes.items():
        if nome == 'DESCARTADO':
            descartados += 1
            continue
        
        # Buscar imagens desse ID
        imgs = list(IMGS_DIR.glob(f'*_id_{id_num}.jpg'))
        if imgs:
            jogadores_imgs[nome].extend(imgs)
    
    if not jogadores_imgs:
        print("❌ Nenhuma imagem classificada encontrada!")
        return
    
    # Copiar e organizar imagens por jogador
    print("\n" + "="*70)
    print("📁 EXPORTANDO DATASET REID")
    print("="*70 + "\n")
    
    estatisticas = {}
    total_imagens = 0
    
    for jogador, imgs in sorted(jogadores_imgs.items()):
        # Criar pasta do jogador
        jogador_dir = OUTPUT_DIR / jogador
        jogador_dir.mkdir(parents=True, exist_ok=True)
        
        # Copiar imagens
        for idx, img_path in enumerate(imgs, 1):
            # Novo nome: formato sequencial
            nova_img = jogador_dir / f"{jogador.lower().replace(' ', '_')}_{idx:03d}.jpg"
            shutil.copy2(img_path, nova_img)
        
        estatisticas[jogador] = len(imgs)
        total_imagens += len(imgs)
        print(f"✓ {jogador:20s} → {len(imgs):3d} imagens")
    
    # Criar arquivo de metadados
    metadata = {
        'total_jogadores': len(jogadores_imgs),
        'total_imagens': total_imagens,
        'descartados': descartados,
        'jogadores': estatisticas
    }
    
    with open(OUTPUT_DIR / 'metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)
    
    # Criar arquivo README
    readme_content = f"""# Dataset ReID - Terça Nobre

## Estrutura
```
dataset_reid/
├── metadata.json
├── README.md
└── jogador_nome/
    ├── jogador_nome_001.jpg
    ├── jogador_nome_002.jpg
    └── ...
```

## Estatísticas
- **Total de jogadores**: {len(jogadores_imgs)}
- **Total de imagens**: {total_imagens}
- **Imagens descartadas**: {descartados}

## Jogadores
"""
    
    for jogador, count in sorted(estatisticas.items(), key=lambda x: x[1], reverse=True):
        readme_content += f"- **{jogador}**: {count} imagens\n"
    
    readme_content += """
## Uso

Este dataset está pronto para uso em sistemas de Re-Identification (ReID).

### Exemplo com PyTorch:
```python
from torchvision import datasets, transforms

transform = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

dataset = datasets.ImageFolder('dataset_reid/', transform=transform)
```

### Estrutura esperada por frameworks de ReID:
- Cada pasta = 1 identidade (jogador)
- Múltiplas imagens por identidade para aprendizado robusto
"""
    
    with open(OUTPUT_DIR / 'README.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print("\n" + "="*70)
    print(f"✓ Dataset exportado com sucesso para: {OUTPUT_DIR}/")
    print(f"✓ {len(jogadores_imgs)} jogadores")
    print(f"✓ {total_imagens} imagens totais")
    print(f"✓ {descartados} imagens descartadas")
    print("="*70 + "\n")
    
    # Análise de balanceamento
    print("📊 ANÁLISE DE BALANCEAMENTO:\n")
    media = total_imagens / len(jogadores_imgs)
    print(f"Média de imagens por jogador: {media:.1f}\n")
    
    poucos = [j for j, c in estatisticas.items() if c < media * 0.5]
    muitos = [j for j, c in estatisticas.items() if c > media * 1.5]
    
    if poucos:
        print(f"⚠️  Jogadores com POUCAS imagens (< {media*0.5:.0f}):")
        for j in poucos:
            print(f"   - {j}: {estatisticas[j]} imagens")
        print()
    
    if muitos:
        print(f"✓ Jogadores com MUITAS imagens (> {media*1.5:.0f}):")
        for j in muitos:
            print(f"   - {j}: {estatisticas[j]} imagens")
        print()
    
    print("💡 Dica: Para melhor precisão no ReID, tente manter 8-15 imagens por jogador.\n")

if __name__ == '__main__':
    exportar_dataset_reid()
