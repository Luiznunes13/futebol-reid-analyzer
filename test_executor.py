#!/usr/bin/env python3
"""
Script de teste para validar o executor.
Executa script.py em modo headless por 10 segundos.
"""

import sys
import time
from api.executor import ScriptExecutor

print("="*70)
print("🧪 TESTE DO EXECUTOR")
print("="*70)

executor = ScriptExecutor()

print("\n1️⃣ Verificando processos ativos...")
processos = executor.get_active_processes()
print(f"   Processos rodando: {len(processos)}")

print("\n2️⃣ Executando script.py em modo headless...")
print("   Timeout: 10 segundos para teste")
print("   Pressione Ctrl+C para cancelar\n")

# Executa com timeout de 10 segundos
exit_code, stdout, stderr = executor.execute_script(
    'script.py',
    timeout=10
)

print("\n" + "="*70)
print("📊 RESULTADO DO TESTE")
print("="*70)
print(f"Exit code: {exit_code}")
print(f"\n--- STDOUT ---")
print(stdout[:500] if stdout else "(vazio)")
print(f"\n--- STDERR ---")
print(stderr[:500] if stderr else "(vazio)")
print("="*70)
