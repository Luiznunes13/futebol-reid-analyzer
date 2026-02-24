import json
from pathlib import Path

print("\n" + "="*70)
print("⚽ CONFIGURAÇÃO DE TIMES - TERÇA NOBRE")
print("="*70)

# Carregar lista de jogadores do jogadores.json
jogadores_file = Path('jogadores.json')
if jogadores_file.exists():
    with open(jogadores_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        todos_jogadores = data.get('jogadores', [])
else:
    print("\n⚠️  Arquivo jogadores.json não encontrado!")
    print("   Criando lista padrão...\n")
    todos_jogadores = [
        "Julio", "Juninho", "Caíque", "Wilson", "Vinicius",
        "Alexandrino", "Picoya", "Neto", "André", "Gustavo",
        "Éder", "Rafael", "Édson", "João Pedro", "Thiago", "Ageu", "Sérgio"
    ]

print(f"\n✓ {len(todos_jogadores)} jogadores encontrados")
print("\nJogadores disponíveis:")
for i, nome in enumerate(todos_jogadores, 1):
    print(f"{i:2d}. {nome}")

import sys

print("\n" + "-"*70)

# Dividir em times
time_azul = []
time_preto = []

if sys.stdin.isatty():
    print("INSTRUÇÃO: Digite os números dos jogadores separados por vírgula")
    print("Exemplo: 1,2,3,4,5,6,7,8")
    print("-"*70)

    print("\n🔵 TIME AZUL (Colete Azul)")
    print("Digite os números dos jogadores do time azul:")
    azul_input = input(">> ").strip()

    if azul_input:
        try:
            indices_azul = [int(x.strip()) - 1 for x in azul_input.split(',')]
            time_azul = [todos_jogadores[i] for i in indices_azul if 0 <= i < len(todos_jogadores)]
            print(f"✓ {len(time_azul)} jogadores no time azul: {', '.join(time_azul)}")
        except:
            print("⚠️  Erro ao processar entrada. Tente novamente.")

    print("\n⚫ TIME PRETO (Colete Preto)")
    print("Digite os números dos jogadores do time preto:")
    preto_input = input(">> ").strip()

    if preto_input:
        try:
            indices_preto = [int(x.strip()) - 1 for x in preto_input.split(',')]
            time_preto = [todos_jogadores[i] for i in indices_preto if 0 <= i < len(todos_jogadores)]
            print(f"✓ {len(time_preto)} jogadores no time preto: {', '.join(time_preto)}")
        except:
            print("⚠️  Erro ao processar entrada. Tente novamente.")
else:
    print("Modo não-interativo: lendo configuração atual do times.json...")
    times_file = Path('times.json')
    if times_file.exists():
        with open(times_file, 'r', encoding='utf-8') as f:
            times_atual = json.load(f)
        time_azul = times_atual.get('time_azul', [])
        time_preto = times_atual.get('time_preto', [])
        print(f"✓ Time Azul ({len(time_azul)}): {', '.join(time_azul)}")
        print(f"✓ Time Preto ({len(time_preto)}): {', '.join(time_preto)}")

# Se não preencheu, criar automaticamente
if not time_azul and not time_preto:
    print("\n⚠️  Nenhum time configurado. Criando divisão automática...")
    meio = len(todos_jogadores) // 2
    time_azul = todos_jogadores[:meio]
    time_preto = todos_jogadores[meio:]

# Salvar configuração
times_config = {
    "time_azul": time_azul,
    "time_preto": time_preto,
    "cor_azul": [0, 0, 255],  # BGR
    "cor_preto": [0, 0, 0]    # BGR
}

with open('times.json', 'w', encoding='utf-8') as f:
    json.dump(times_config, f, ensure_ascii=False, indent=4)

print("\n" + "="*70)
print("✅ CONFIGURAÇÃO SALVA EM times.json")
print("="*70)
print(f"\n🔵 TIME AZUL ({len(time_azul)} jogadores):")
for nome in time_azul:
    print(f"   - {nome}")

print(f"\n⚫ TIME PRETO ({len(time_preto)} jogadores):")
for nome in time_preto:
    print(f"   - {nome}")

print("\n" + "="*70)
print("PRÓXIMOS PASSOS:")
print("="*70)
print("1. Classifique jogadores: python app_times.py")
print("2. Reconheça por time: python reconhecer_por_time.py")
print("\nPara editar manualmente, abra: times.json")
print("="*70 + "\n")
