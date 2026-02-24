"""
Gerenciador de execução de scripts do sistema Terça Nobre.
Executa scripts Python como subprocessos e captura output em tempo real.
"""

import subprocess
import os
import sys
import signal
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class ScriptExecutor:
    """Executa scripts Python do sistema de forma segura com controle de processos."""
    
    def __init__(self, project_root: str = None):
        """
        Inicializa o executor.
        
        Args:
            project_root: Caminho raiz do projeto. Se None, usa o diretório pai.
        """
        if project_root is None:
            # Pega o diretório raiz do projeto (pai de 'api/')
            self.project_root = Path(__file__).parent.parent.resolve()
        else:
            self.project_root = Path(project_root).resolve()
        
        self.scripts_dir = self.project_root / "scripts"
        
        # Dicionário para rastrear processos ativos
        self.active_processes: Dict[str, subprocess.Popen] = {}
        
    def get_python_command(self) -> List[str]:
        """
        Retorna o comando Python correto (pyenv ou system).
        
        Returns:
            Lista com o comando Python a ser usado
        """
        # Usa o mesmo interpretador Python que está executando este código
        return [sys.executable]
    
    def list_available_scripts(self) -> List[Dict[str, str]]:
        """
        Lista todos os scripts disponíveis na pasta scripts/.
        
        Returns:
            Lista de dicionários com informações dos scripts
        """
        scripts = []
        
        if not self.scripts_dir.exists():
            return scripts
        
        # Mapeamento de scripts para descrições amigáveis
        descriptions = {
            "script.py": "📸 Capturar imagens dos vídeos com detecção facial",
            "setup_times.py": "⚙️ Configurar times e jogadores",
            "exportar_reid.py": "📦 Exportar dataset organizado para ReID",
            "treinar_reid_model.py": "🤖 Treinar modelo Deep Learning (ReID)",
            "reconhecer_por_time.py": "🔍 Reconhecer jogadores (método histograma)",
            "reconhecer_com_reid.py": "🔍 Reconhecer jogadores (método ReID)",
            "analisar_trajetoria.py": "📊 Calcular distâncias percorridas",
            "sincronizar_cameras.py": "🔗 Sincronizar IDs entre câmeras",
            "analisar_balanceamento.py": "📈 Estatísticas do dataset"
        }
        
        for script_file in sorted(self.scripts_dir.glob("*.py")):
            script_name = script_file.name
            scripts.append({
                "name": script_name,
                "path": str(script_file),
                "description": descriptions.get(script_name, script_name)
            })
        
        return scripts
    
    def execute_script(
        self, 
        script_name: str, 
        args: List[str] = None,
        capture_output: bool = True,
        timeout: int = 600
    ) -> Tuple[int, str, str]:
        """
        Executa um script Python e retorna o resultado.
        
        Args:
            script_name: Nome do script (ex: 'script.py')
            args: Argumentos adicionais para o script
            capture_output: Se True, captura stdout/stderr. Se False, mostra no terminal.
            timeout: Timeout em segundos (padrão 10 minutos)
        
        Returns:
            Tupla (exit_code, stdout, stderr)
        """
        script_path = self.scripts_dir / script_name
        
        if not script_path.exists():
            return (1, "", f"Erro: Script '{script_name}' não encontrado em {self.scripts_dir}")
        
        # Verifica se já existe um processo rodando para este script
        if script_name in self.active_processes:
            proc = self.active_processes[script_name]
            if proc.poll() is None:  # Processo ainda rodando
                return (1, "", f"Erro: Script '{script_name}' já está em execução (PID: {proc.pid})")
        
        # Monta o comando
        cmd = self.get_python_command() + [str(script_path)]
        
        # Adiciona flag --headless para scripts que processam vídeo
        if script_name in ['script.py', 'reconhecer_por_time.py', 'reconhecer_com_reid.py']:
            cmd.append('--headless')
        
        if args:
            cmd.extend(args)
        
        # Log detalhado para debug
        print("\n" + "="*70)
        print(f"🚀 EXECUTANDO SCRIPT: {script_name}")
        print(f"📍 Comando: {' '.join(cmd)}")
        print(f"📁 CWD: {self.project_root}")
        print(f"⚙️  Env HEADLESS: 1")
        print("="*70 + "\n")
        
        # Ajusta timeout para scripts longos de processamento de vídeo
        if script_name in ['script.py', 'reconhecer_por_time.py', 'reconhecer_com_reid.py']:
            timeout = 3600  # 1 hora para processamento de vídeo
        elif script_name == 'treinar_reid_model.py':
            timeout = 7200  # 2 horas para treinamento
        
        try:
            if capture_output:
                # Executa e captura output
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.project_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env={**os.environ, 'HEADLESS': '1'}  # Define variável de ambiente
                )
                
                # Registra o processo
                self.active_processes[script_name] = process
                
                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                    exit_code = process.returncode
                except subprocess.TimeoutExpired:
                    # Mata o processo se exceder timeout
                    self.kill_process(script_name)
                    return (1, "", f"Erro: Script excedeu tempo limite de {timeout} segundos ({timeout//60} minutos)")
                finally:
                    # Remove do registro
                    if script_name in self.active_processes:
                        del self.active_processes[script_name]
                
                return (exit_code, stdout, stderr)
            else:
                # Executa sem capturar (mostra no terminal)
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.project_root),
                    env={**os.environ, 'HEADLESS': '1'}
                )
                
                self.active_processes[script_name] = process
                
                try:
                    exit_code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self.kill_process(script_name)
                    return (1, "", f"Erro: Script excedeu tempo limite de {timeout} segundos")
                finally:
                    if script_name in self.active_processes:
                        del self.active_processes[script_name]
                
                return (exit_code, "", "")
                
        except Exception as e:
            # Remove do registro em caso de erro
            if script_name in self.active_processes:
                del self.active_processes[script_name]
            return (1, "", f"Erro ao executar script: {str(e)}")
    
    def execute_script_async(
        self, 
        script_name: str, 
        args: List[str] = None
    ) -> subprocess.Popen:
        """
        Executa um script de forma assíncrona (não-bloqueante).
        Útil para scripts longos como treinamento de modelo ou processamento de vídeo.
        
        Args:
            script_name: Nome do script
            args: Argumentos adicionais
            
        Returns:
            Processo em execução (Popen object)
        """
        script_path = self.scripts_dir / script_name
        
        if not script_path.exists():
            raise FileNotFoundError(f"Script '{script_name}' não encontrado")
        
        # Verifica se já existe um processo rodando
        if script_name in self.active_processes:
            proc = self.active_processes[script_name]
            if proc.poll() is None:  # Ainda rodando
                raise RuntimeError(f"Script '{script_name}' já está em execução (PID: {proc.pid})")
        
        cmd = self.get_python_command() + [str(script_path)]
        
        # Adiciona flag --headless para scripts que processam vídeo
        if script_name in ['script.py', 'reconhecer_por_time.py', 'reconhecer_com_reid.py']:
            cmd.append('--headless')
        
        if args:
            cmd.extend(args)
        
        process = subprocess.Popen(
            cmd,
            cwd=str(self.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, 'HEADLESS': '1'}
        )
        
        # Registra o processo
        self.active_processes[script_name] = process
        
        return process
    
    def get_active_processes(self) -> List[Dict[str, any]]:
        """
        Retorna lista de processos ativos.
        
        Returns:
            Lista de dicionários com informações dos processos
        """
        self.cleanup_finished_processes()
        
        processes = []
        for script_name, process in self.active_processes.items():
            processes.append({
                'script': script_name,
                'pid': process.pid,
                'running': process.poll() is None,
                'returncode': process.returncode
            })
        
        return processes
    
    def kill_process(self, script_name: str) -> bool:
        """
        Mata um processo específico.
        
        Args:
            script_name: Nome do script
            
        Returns:
            True se matou com sucesso, False caso contrário
        """
        if script_name not in self.active_processes:
            return False
        
        process = self.active_processes[script_name]
        
        try:
            # Tenta terminar graciosamente primeiro
            process.terminate()
            
            # Aguarda 2 segundos
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Se não terminou, mata forçadamente
                process.kill()
                process.wait()
            
            # Remove do registro
            del self.active_processes[script_name]
            return True
            
        except Exception as e:
            print(f"Erro ao matar processo {script_name}: {e}")
            return False
    
    def kill_all_processes(self) -> int:
        """
        Mata todos os processos ativos.
        
        Returns:
            Número de processos mortos
        """
        count = 0
        script_names = list(self.active_processes.keys())
        
        for script_name in script_names:
            if self.kill_process(script_name):
                count += 1
        
        return count
    
    def cleanup_finished_processes(self):
        """Remove processos finalizados do registro."""
        finished = []
        
        for script_name, process in self.active_processes.items():
            if process.poll() is not None:  # Processo finalizado
                finished.append(script_name)
        
        for script_name in finished:
            del self.active_processes[script_name]
    
    def is_script_running(self, script_name: str) -> bool:
        """
        Verifica se um script está rodando.
        
        Args:
            script_name: Nome do script
            
        Returns:
            True se está rodando, False caso contrário
        """
        if script_name not in self.active_processes:
            return False
        
        process = self.active_processes[script_name]
        return process.poll() is None


def test_executor():
    """Testa o executor com scripts disponíveis."""
    executor = ScriptExecutor()
    
    print("🧪 Testando ScriptExecutor\n")
    print(f"📁 Diretório do projeto: {executor.project_root}")
    print(f"📂 Diretório de scripts: {executor.scripts_dir}")
    print(f"🐍 Comando Python: {' '.join(executor.get_python_command())}\n")
    
    print("📜 Scripts disponíveis:")
    scripts = executor.list_available_scripts()
    for script in scripts:
        print(f"  • {script['description']}")
        print(f"    Arquivo: {script['name']}")
    
    print(f"\n✅ Total: {len(scripts)} scripts encontrados")


if __name__ == "__main__":
    test_executor()
