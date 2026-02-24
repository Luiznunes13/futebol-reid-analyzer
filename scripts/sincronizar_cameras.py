"""
Sistema de sincronização de IDs entre câmeras
Permite mapear que ID_X da câmera ESQ = ID_Y da câmera DIR
"""

import json
import os
from pathlib import Path

SINCRONIA_FILE = 'sincronia_cameras.json'
CLASSIFICACOES_FILE = 'jogadores_com_ids.json'

class GerenciadorSincronia:
    def __init__(self):
        self.sincronias = self.carregar_sincronias()
        self.classificacoes = self.carregar_classificacoes()
    
    def carregar_sincronias(self):
        """Carrega mapeamento de sincronias entre câmeras"""
        if os.path.exists(SINCRONIA_FILE):
            with open(SINCRONIA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def carregar_classificacoes(self):
        """Carrega classificações de IDs"""
        if os.path.exists(CLASSIFICACOES_FILE):
            with open(CLASSIFICACOES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def salvar_sincronias(self):
        """Salva sincronias no arquivo JSON"""
        with open(SINCRONIA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.sincronias, f, ensure_ascii=False, indent=4)
    
    def adicionar_sincronia(self, id_esq, id_dir, nome_jogador):
        """Adiciona uma sincronia entre IDs de diferentes câmeras"""
        chave = f"ESQ_{id_esq}_DIR_{id_dir}"
        
        self.sincronias[chave] = {
            'id_esq': str(id_esq),
            'id_dir': str(id_dir),
            'jogador': nome_jogador
        }
        
        self.salvar_sincronias()
        print(f"✓ Sincronia adicionada: ESQ ID {id_esq} ↔ DIR ID {id_dir} → {nome_jogador}")
    
    def remover_sincronia(self, id_esq, id_dir):
        """Remove uma sincronia"""
        chave = f"ESQ_{id_esq}_DIR_{id_dir}"
        
        if chave in self.sincronias:
            del self.sincronias[chave]
            self.salvar_sincronias()
            print(f"✓ Sincronia removida: ESQ ID {id_esq} ↔ DIR ID {id_dir}")
        else:
            print(f"❌ Sincronia não encontrada!")
    
    def listar_sincronias(self):
        """Lista todas as sincronias configuradas"""
        if not self.sincronias:
            print("\n❌ Nenhuma sincronia configurada ainda.")
            return
        
        print("\n" + "="*70)
        print("🔗 SINCRONIAS ENTRE CÂMERAS")
        print("="*70 + "\n")
        
        for chave, dados in sorted(self.sincronias.items()):
            id_esq = dados['id_esq']
            id_dir = dados['id_dir']
            jogador = dados['jogador']
            
            # Buscar imagens
            imgs_esq = list(Path('jogadores_terca').glob(f'ESQ_id_{id_esq}.jpg'))
            imgs_dir = list(Path('jogadores_terca').glob(f'DIR_id_{id_dir}.jpg'))
            
            status_esq = "✓" if imgs_esq else "✗"
            status_dir = "✓" if imgs_dir else "✗"
            
            print(f"📷 ESQ ID {id_esq:3s} {status_esq} ↔ 📷 DIR ID {id_dir:3s} {status_dir} → {jogador}")
        
        print("\n" + "="*70 + "\n")
    
    def buscar_por_jogador(self, nome_jogador):
        """Busca todas as sincronias de um jogador específico"""
        resultados = []
        
        for chave, dados in self.sincronias.items():
            if dados['jogador'] == nome_jogador:
                resultados.append(dados)
        
        return resultados
    
    def sugerir_sincronias_automaticas(self):
        """Sugere sincronias baseado nas classificações existentes"""
        print("\n" + "="*70)
        print("🤖 SUGESTÕES AUTOMÁTICAS DE SINCRONIA")
        print("="*70 + "\n")
        
        # Agrupar IDs por jogador
        jogadores_ids = {}
        
        for id_num, nome in self.classificacoes.items():
            if nome == 'DESCARTADO':
                continue
            
            if nome not in jogadores_ids:
                jogadores_ids[nome] = {'esq': [], 'dir': []}
            
            # Verificar se é ESQ ou DIR
            imgs = list(Path('jogadores_terca').glob(f'*_id_{id_num}.jpg'))
            for img in imgs:
                if 'ESQ' in img.name:
                    jogadores_ids[nome]['esq'].append(id_num)
                elif 'DIR' in img.name:
                    jogadores_ids[nome]['dir'].append(id_num)
        
        # Sugerir sincronias para jogadores com IDs em ambas câmeras
        sugestoes = []
        
        for jogador, ids in sorted(jogadores_ids.items()):
            if ids['esq'] and ids['dir']:
                # Tem IDs em ambas câmeras
                for id_esq in ids['esq']:
                    for id_dir in ids['dir']:
                        # Verificar se já existe
                        chave = f"ESQ_{id_esq}_DIR_{id_dir}"
                        if chave not in self.sincronias:
                            sugestoes.append((id_esq, id_dir, jogador))
        
        if not sugestoes:
            print("✓ Todas as sincronias possíveis já estão configuradas!")
            return
        
        print(f"Encontradas {len(sugestoes)} sugestões:\n")
        
        for i, (id_esq, id_dir, jogador) in enumerate(sugestoes, 1):
            print(f"{i:2d}. ESQ ID {id_esq:3s} ↔ DIR ID {id_dir:3s} → {jogador}")
        
        print("\n" + "="*70)
        
        import sys
        if sys.stdin.isatty():
            resposta = input("\nAdicionar todas as sugestões automaticamente? (s/n): ")
            adicionar = resposta.lower() == 's'
        else:
            print("\nModo não-interativo: adicionando sugestões automaticamente.")
            adicionar = True

        if adicionar:
            for id_esq, id_dir, jogador in sugestoes:
                self.adicionar_sincronia(id_esq, id_dir, jogador)
            print(f"\n✓ {len(sugestoes)} sincronias adicionadas!")
        else:
            print("\nCancelado. Use o menu para adicionar manualmente.")

def menu_interativo():
    """Menu interativo para gerenciar sincronias"""
    gerenciador = GerenciadorSincronia()
    
    while True:
        print("\n" + "="*70)
        print("🔗 GERENCIADOR DE SINCRONIA DE CÂMERAS")
        print("="*70)
        print("\n1. Listar sincronias existentes")
        print("2. Adicionar sincronia manual")
        print("3. Remover sincronia")
        print("4. Buscar por jogador")
        print("5. Sugerir sincronias automáticas")
        print("6. Exportar relatório")
        print("0. Sair")
        
        opcao = input("\nEscolha uma opção: ").strip()
        
        if opcao == '0':
            print("\n👋 Até logo!")
            break
        
        elif opcao == '1':
            gerenciador.listar_sincronias()
        
        elif opcao == '2':
            print("\n📝 ADICIONAR SINCRONIA MANUAL")
            print("-" * 40)
            
            id_esq = input("ID da câmera ESQ: ").strip()
            id_dir = input("ID da câmera DIR: ").strip()
            nome = input("Nome do jogador: ").strip()
            
            if id_esq and id_dir and nome:
                gerenciador.adicionar_sincronia(id_esq, id_dir, nome)
            else:
                print("❌ Dados inválidos!")
        
        elif opcao == '3':
            print("\n🗑️  REMOVER SINCRONIA")
            print("-" * 40)
            
            id_esq = input("ID da câmera ESQ: ").strip()
            id_dir = input("ID da câmera DIR: ").strip()
            
            if id_esq and id_dir:
                gerenciador.remover_sincronia(id_esq, id_dir)
            else:
                print("❌ Dados inválidos!")
        
        elif opcao == '4':
            print("\n🔍 BUSCAR POR JOGADOR")
            print("-" * 40)
            
            nome = input("Nome do jogador: ").strip()
            resultados = gerenciador.buscar_por_jogador(nome)
            
            if resultados:
                print(f"\n✓ Encontradas {len(resultados)} sincronias para '{nome}':\n")
                for r in resultados:
                    print(f"   ESQ ID {r['id_esq']} ↔ DIR ID {r['id_dir']}")
            else:
                print(f"\n❌ Nenhuma sincronia encontrada para '{nome}'")
        
        elif opcao == '5':
            gerenciador.sugerir_sincronias_automaticas()
        
        elif opcao == '6':
            print("\n📄 EXPORTAR RELATÓRIO")
            print("-" * 40)
            
            relatorio = []
            relatorio.append("# Relatório de Sincronias entre Câmeras\n")
            relatorio.append("| Câmera ESQ | Câmera DIR | Jogador |\n")
            relatorio.append("|------------|------------|----------|\n")
            
            for chave, dados in sorted(gerenciador.sincronias.items()):
                relatorio.append(f"| ID {dados['id_esq']} | ID {dados['id_dir']} | {dados['jogador']} |\n")
            
            arquivo = 'relatorio_sincronias.md'
            with open(arquivo, 'w', encoding='utf-8') as f:
                f.writelines(relatorio)
            
            print(f"✓ Relatório exportado para: {arquivo}")
        
        else:
            print("\n❌ Opção inválida!")

def modo_relatorio():
    """Modo não-interativo: mostra sincronias existentes e sugere novas automaticamente"""
    gerenciador = GerenciadorSincronia()
    gerenciador.listar_sincronias()
    gerenciador.sugerir_sincronias_automaticas()

if __name__ == '__main__':
    import sys
    if sys.stdin.isatty():
        menu_interativo()
    else:
        modo_relatorio()
