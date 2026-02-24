import json
from collections import Counter

# Carregar classificações
with open('jogadores_com_ids.json', 'r', encoding='utf-8') as f:
    classificacoes = json.load(f)

# Contar classificações por jogador
contagem = Counter(classificacoes.values())

# Estatísticas
total_ids = len(classificacoes)
num_jogadores = len(contagem)
media = total_ids / num_jogadores if num_jogadores > 0 else 0

print("\n" + "="*70)
print("📊 ANÁLISE DE BALANCEAMENTO DAS CLASSIFICAÇÕES")
print("="*70)
print(f"\n✓ Total de IDs classificados: {total_ids}")
print(f"✓ Jogadores únicos: {num_jogadores}")
print(f"✓ Média por jogador: {media:.1f} IDs")

# Ordenar por quantidade (mais classificações primeiro)
jogadores_ordenados = sorted(contagem.items(), key=lambda x: x[1], reverse=True)

print("\n" + "-"*70)
print(" DISTRIBUIÇÃO POR JOGADOR")
print("-"*70)
print(f"{'Jogador':<20} {'IDs':<8} {'Barra':<40}")
print("-"*70)

max_count = jogadores_ordenados[0][1]

for nome, count in jogadores_ordenados:
    # Criar barra visual
    barra_size = int((count / max_count) * 40)
    barra = "█" * barra_size
    
    # Alerta se tem poucos IDs
    alerta = " ⚠️" if count < 3 else ""
    
    print(f"{nome:<20} {count:<8} {barra:<40}{alerta}")

# Identificar problemas
print("\n" + "="*70)
print(" RECOMENDAÇÕES")
print("="*70)

# Jogadores com poucas amostras
poucos = [(nome, count) for nome, count in contagem.items() if count < 3]
if poucos:
    print(f"\n⚠️  Jogadores com POUCAS referências (< 3):")
    for nome, count in sorted(poucos, key=lambda x: x[1]):
        print(f"   - {nome}: {count} ID(s)")
    print(f"\n   Recomendação: Classifique mais IDs destes jogadores")

# Jogadores com muitas amostras
muitos = [(nome, count) for nome, count in contagem.items() if count > media * 2]
if muitos:
    print(f"\n📈 Jogadores com MUITAS referências (> {media*2:.0f}):")
    for nome, count in sorted(muitos, key=lambda x: x[1], reverse=True):
        print(f"   - {nome}: {count} IDs")

# Jogadores com boa quantidade
bons = [(nome, count) for nome, count in contagem.items() if 3 <= count <= media * 2]
if bons:
    print(f"\n✅ Jogadores bem balanceados ({len(bons)} jogadores):")
    for nome, count in sorted(bons, key=lambda x: x[0]):
        print(f"   - {nome}: {count} IDs")

# Resumo
print("\n" + "="*70)
print(" RESUMO")
print("="*70)
print(f"✅ Bem balanceados: {len(bons)} jogadores")
print(f"⚠️  Precisam mais referências: {len(poucos)} jogadores")
print(f"📊 Com excesso de referências: {len(muitos)} jogadores")

# Qualidade geral
if len(poucos) == 0:
    print(f"\n🎉 ÓTIMO! Todos os jogadores têm pelo menos 3 referências")
elif len(poucos) <= 3:
    print(f"\n👍 BOM! Apenas {len(poucos)} jogador(es) precisa(m) mais referências")
else:
    print(f"\n⚠️  ATENÇÃO! {len(poucos)} jogadores precisam de mais referências")

print("\n" + "="*70)
print(" DICAS PARA MELHORAR O BALANCEAMENTO")
print("="*70)
print("""
1. Use o filtro 'Pendentes' no app web para focar em IDs não classificados
2. Tente ter pelo menos 3-5 referências de cada jogador
3. Priorize jogadores com poucas referências
4. Referências variadas (ângulos diferentes) funcionam melhor

Para reabrir o classificador: python app.py
""")
