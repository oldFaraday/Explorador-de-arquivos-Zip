"""Motor de sincronização de checklists (merge bidirecional)."""

import logging
import hashlib
from pathlib import Path
from typing import Dict, Tuple, List
from dataclasses import dataclass

from state import app_state, APPDATA_DIR, CHECKLISTS_DIR
from crypto import extrair_checklists_zip, criar_zip_com_checklists, hash_arquivo
from models import Checklist

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Resultado da operação de sincronização."""
    enviados: int = 0          # Novos registros locais enviados para o ZIP
    recebidos: int = 0         # Novos registros do ZIP recebidos localmente
    conflitos: int = 0         # Registros com mesmo (data, conferente) - deduplicados
    itens_atualizados: int = 0 # Itens que tiveram merge
    erros: List[str] = None
    
    def __post_init__(self):
        if self.erros is None:
            self.erros = []
    
    @property
    def sucesso(self) -> bool:
        return len(self.erros) == 0
    
    def resumo(self) -> str:
        linhas = [
            f"Enviados: {self.enviados}",
            f"Recebidos: {self.recebidos}",
            f"Conflitos resolvidos: {self.conflitos}",
            f"Itens atualizados: {self.itens_atualizados}",
        ]
        if self.erros:
            linhas.append(f"Erros: {len(self.erros)}")
            for e in self.erros[:5]:
                linhas.append(f"  - {e}")
        return "\n".join(linhas)


def sincronizar_checklists(progress_callback=None) -> SyncResult:
    """
    Executa sincronização bidirecional dos checklists.
    
    Fluxo:
    1. Obtém hash do ZIP no servidor
    2. Extrai checklists.json do ZIP remoto
    3. Carrega checklists locais
    4. Merge por item_id com deduplicação (data, conferente)
    5. Reescreve ZIP com checklists consolidados
    6. Atualiza checklists locais com versão consolidada
    7. Atualiza sync_state.json
    """
    result = SyncResult()
    
    try:
        zip_path = app_state.zip_path
        senha = app_state.zip_senha
        
        if not zip_path or not zip_path.exists():
            result.erros.append("Arquivo ZIP não encontrado")
            return result
        
        # 1. Hash do ZIP atual
        zip_hash_atual = hash_arquivo(zip_path)
        logger.info(f"Hash do ZIP remoto: {zip_hash_atual[:16]}...")
        
        if progress_callback:
            progress_callback(10, "Lendo ZIP remoto...")
        
        # 2. Extrair checklists do ZIP
        checklists_zip = extrair_checklists_zip(zip_path, senha)
        logger.info(f"Checklists no ZIP: {len(checklists_zip)}")
        
        if progress_callback:
            progress_callback(30, "Carregando checklists locais...")
        
        # 3. Carregar checklists locais
        checklists_locais = app_state.carregar_checklists_locais()
        logger.info(f"Checklists locais: {len(checklists_locais)}")
        
        if progress_callback:
            progress_callback(50, "Realizando merge...")
        
        # 4. Merge por item_id
        checklists_consolidados = {}
        todos_ids = set(checklists_zip.keys()) | set(checklists_locais.keys())
        
        for item_id in todos_ids:
            zip_cl = checklists_zip.get(item_id)
            local_cl = checklists_locais.get(item_id)
            
            if zip_cl and local_cl:
                # Ambos existem - fazer merge
                checklist_zip = Checklist.from_dict(zip_cl)
                checklist_local = Checklist.from_dict(local_cl)
                consolidado = checklist_local.merge(checklist_zip)
                
                # Contar estatísticas
                antes_local = len(checklist_local.historico)
                antes_zip = len(checklist_zip.historico)
                depois = len(consolidado.historico)
                
                result.conflitos += (antes_local + antes_zip - depois)
                result.enviados += max(0, depois - antes_zip)
                result.recebidos += max(0, depois - antes_local)
                
                if depois > max(antes_local, antes_zip):
                    result.itens_atualizados += 1
                    
            elif local_cl and not zip_cl:
                # Só existe local - novo item ou ZIP não tem
                consolidado = Checklist.from_dict(local_cl)
                result.enviados += len(consolidado.historico)
                result.itens_atualizados += 1
                
            elif zip_cl and not local_cl:
                # Só existe no ZIP - receber
                consolidado = Checklist.from_dict(zip_cl)
                result.recebidos += len(consolidado.historico)
                result.itens_atualizados += 1
            
            else:
                continue
            
            checklists_consolidados[item_id] = consolidado.to_dict()
        
        if progress_callback:
            progress_callback(70, "Atualizando ZIP remoto...")
        
        # 5. Reescrever ZIP com checklists consolidados
        if checklists_consolidados:
            sucesso = criar_zip_com_checklists(zip_path, senha, APPDATA_DIR / "cache", checklists_consolidados)
            if not sucesso:
                result.erros.append("Falha ao atualizar ZIP remoto")
                return result
        
        if progress_callback:
            progress_callback(90, "Atualizando checklists locais...")
        
        # 6. Atualizar checklists locais com versão consolidada
        for item_id, data in checklists_consolidados.items():
            checklist = Checklist.from_dict(data)
            app_state.salvar_checklist_local(checklist)
            # Atualizar também no estado em memória
            item = app_state.get_item(item_id)
            if item:
                item.checklist = checklist
        
        # 7. Atualizar estado de sync
        novo_hash = hash_arquivo(zip_path)
        from models import SyncState
        sync_state = SyncState.create(novo_hash, app_state._config.get("versao_app", "1.0.0"))
        app_state.salvar_sync_state(sync_state)
        
        if progress_callback:
            progress_callback(100, "Sincronização concluída!")
        
        logger.info(f"Sincronização concluída: {result.resumo()}")
        return result
        
    except Exception as e:
        logger.error(f"Erro durante sincronização: {e}")
        result.erros.append(f"Erro inesperado: {e}")
        return result


def verificar_fora_de_sync() -> bool:
    """Verifica se o estado local está fora de sync com o ZIP remoto."""
    try:
        zip_path = app_state.zip_path
        if not zip_path or not zip_path.exists():
            return True
        
        sync_state = app_state.sync_state
        if not sync_state:
            return True
        
        hash_atual = hash_arquivo(zip_path)
        return hash_atual != sync_state.zip_hash
    except Exception:
        return True


def get_status_sync() -> dict:
    """Retorna status detalhado da sincronização para a UI."""
    zip_path = app_state.zip_path
    sync_state = app_state.sync_state
    
    status = {
        "sincronizado": False,
        "hash_local": "",
        "hash_remoto": "",
        "ultimo_sync": "",
        "fora_de_sync": True,
        "checklists_locais": 0,
        "checklists_remotos": 0,
    }
    
    if not zip_path or not zip_path.exists():
        status["erro"] = "ZIP não acessível"
        return status
    
    try:
        hash_remoto = hash_arquivo(zip_path)
        status["hash_remoto"] = hash_remoto[:16] + "..."
        
        if sync_state:
            status["hash_local"] = sync_state.zip_hash[:16] + "..."
            status["ultimo_sync"] = sync_state.ultimo_sync
            status["sincronizado"] = (hash_remoto == sync_state.zip_hash)
            status["fora_de_sync"] = (hash_remoto != sync_state.zip_hash)
        
        # Contar checklists
        checklists_locais = app_state.carregar_checklists_locais()
        status["checklists_locais"] = sum(len(c.historico) for c in checklists_locais.values())
        
        checklists_zip = extrair_checklists_zip(zip_path, app_state.zip_senha)
        status["checklists_remotos"] = sum(len(c.get("historico", [])) for c in checklists_zip.values())
        
    except Exception as e:
        status["erro"] = str(e)
    
    return status