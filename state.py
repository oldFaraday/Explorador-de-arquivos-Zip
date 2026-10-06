"""Gestão de estado em memória e persistência local."""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict

from models import Item, Checklist, SyncState
from crypto import descobrir_itens_zip

logger = logging.getLogger(__name__)

# Constantes de diretórios
APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "ExploradorZip"
CACHE_DIR = APPDATA_DIR / "cache"
CHECKLISTS_DIR = APPDATA_DIR / "checklists"
LOGS_DIR = APPDATA_DIR / "logs"
SYNC_STATE_FILE = APPDATA_DIR / "sync_state.json"
CONFIG_FILE = APPDATA_DIR / "config.json"

VERSAO_APP = "1.1.0"

# Mapa de migração de IDs legados para novos (estrutura hierárquica futura)
# Chave = item_id antigo (estrutura plana), Valor = item_id novo (estrutura hierárquica)
MAPA_MIGRACAO_LEGADO = {
    # Chips Lisa
    'chips_lisa_cebola_salsa_115g': 'bobinas_de_embalagem_chips_lisa_cebola_salsa_115g',
    'chips_lisa_cebola_salsa_70g': 'bobinas_de_embalagem_chips_lisa_cebola_salsa_70g',
    'chips_lisa_classica_115g': 'bobinas_de_embalagem_chips_lisa_classica_115g',
    'chips_lisa_classica_70g': 'bobinas_de_embalagem_chips_lisa_classica_70g',
    'chips_lisa_churrasco_70g': 'bobinas_de_embalagem_chips_lisa_churrasco_70g',
    'chips_lisa_queijo_80g': 'bobinas_de_embalagem_chips_lisa_queijo_80g',
    # Chips Ondulada
    'chips_ondulada_cebola_salsa_115g': 'bobinas_de_embalagem_chips_ondulada_cebola_salsa_115g',
    'chips_ondulada_cebola_salsa_68g': 'bobinas_de_embalagem_chips_ondulada_cebola_salsa_68g',
    'chips_ondulada_cheddar_bacon_115g': 'bobinas_de_embalagem_chips_ondulada_cheddar_bacon_115g',
    'chips_ondulada_classica_115g': 'bobinas_de_embalagem_chips_ondulada_classica_115g',
    'chips_ondulada_classica_68g': 'bobinas_de_embalagem_chips_ondulada_classica_68g',
    'chips_ondulada_picanha_115g': 'bobinas_de_embalagem_chips_ondulada_picanha_115g',
    'chips_ondulada_pimenta_mexicana_115g': 'bobinas_de_embalagem_chips_ondulada_pimenta_mexicana_115g',
    # Palha Extrafina
    'palha_extrafina_100g': 'bobinas_de_embalagem_palha_extrafina_100g',
    'palha_extrafina_400g': 'bobinas_de_embalagem_palha_extrafina_400g',
    'palha_extrafina_sal_marinho_100g': 'bobinas_de_embalagem_palha_extrafina_sal_marinho_100g',
    'palha_extrafina_ervas_finas_100g': 'bobinas_de_embalagem_palha_extrafina_ervas_finas_100g',
    # Palha Tradicional
    'palha_tradicional_100g': 'bobinas_de_embalagem_palha_tradicional_100g',
    'palha_tradicional_200g': 'bobinas_de_embalagem_palha_tradicional_200g',
    'palha_tradicional_400g': 'bobinas_de_embalagem_palha_tradicional_400g',
    'palha_tradicional_800g': 'bobinas_de_embalagem_palha_tradicional_800g',
    'palha_tradicional_cebola_e_alho_200g': 'bobinas_de_embalagem_palha_tradicional_cebola_e_alho_200g',
}


def migrar_checklists_se_necessario() -> int:
    """
    Migra checklists locais órfãos (IDs antigos) para novos IDs, se aplicável.
    Executa uma vez na primeira inicialização após mudança de estrutura do ZIP.
    Retorna número de checklists migrados.
    """
    migrados = 0
    for antigo, novo in MAPA_MIGRACAO_LEGADO.items():
        old_path = CHECKLISTS_DIR / f'{antigo}.json'
        new_path = CHECKLISTS_DIR / f'{novo}.json'
        if old_path.exists() and not new_path.exists():
            try:
                shutil.move(str(old_path), str(new_path))
                logger.info(f'Checklist migrado: {antigo} → {novo}')
                migrados += 1
            except Exception as e:
                logger.error(f'Falha ao migrar checklist {antigo}: {e}')
    return migrados


class AppState:
    """Gerenciador central de estado da aplicação."""
    
    def __init__(self):
        self._itens: Dict[str, Item] = {}  # id -> Item
        self._categorias: Dict[str, List[str]] = {}  # categoria -> [ids]
        self._item_atual_id: Optional[str] = None
        self._sync_state: Optional[SyncState] = None
        self._config: dict = {}
        self._zip_path: Optional[Path] = None
        self._zip_senha: str = ""
        self._inicializado = False
    
    def inicializar_diretorios(self) -> None:
        """Cria a estrutura de diretórios local."""
        for dir_path in [CACHE_DIR, CHECKLISTS_DIR, LOGS_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Diretórios inicializados em {APPDATA_DIR}")
    
    def carregar_config(self) -> dict:
        """Carrega configurações do arquivo local."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                self._zip_path = Path(self._config.get("zip_path", "")) if self._config.get("zip_path") else None
                self._zip_senha = self._config.get("zip_senha", "")
                self._config.setdefault("auto_recarregar", False)
            except Exception as e:
                logger.warning(f"Erro ao carregar config: {e}")
                self._config = {}
        return self._config
    
    def salvar_config(self) -> None:
        """Salva configurações no arquivo local."""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar config: {e}")
    
    @property
    def zip_path(self) -> Optional[Path]:
        return self._zip_path
    
    @zip_path.setter
    def zip_path(self, value: Optional[Path]) -> None:
        self._zip_path = value
        self._config["zip_path"] = str(value) if value else ""
        self.salvar_config()
    
    @property
    def zip_senha(self) -> str:
        return self._zip_senha
    
    @zip_senha.setter
    def zip_senha(self, value: str) -> None:
        self._zip_senha = value
        self._config["zip_senha"] = value
        self.salvar_config()
    
    @property
    def auto_recarregar(self) -> bool:
        return self._config.get("auto_recarregar", False)
    
    @auto_recarregar.setter
    def auto_recarregar(self, value: bool) -> None:
        self._config["auto_recarregar"] = value
        self.salvar_config()
    
    def carregar_sync_state(self) -> Optional[SyncState]:
        """Carrega estado de sincronização."""
        if SYNC_STATE_FILE.exists():
            try:
                with open(SYNC_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._sync_state = SyncState.from_dict(data)
            except Exception as e:
                logger.warning(f"Erro ao carregar sync_state: {e}")
        return self._sync_state
    
    def salvar_sync_state(self, sync_state: SyncState) -> None:
        """Salva estado de sincronização."""
        self._sync_state = sync_state
        try:
            with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(sync_state.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar sync_state: {e}")
    
    @property
    def sync_state(self) -> Optional[SyncState]:
        return self._sync_state
    
    def carregar_checklists_locais(self) -> Dict[str, Checklist]:
        """Carrega todos os checklists locais do disco."""
        checklists = {}
        if CHECKLISTS_DIR.exists():
            for arquivo in CHECKLISTS_DIR.glob("*.json"):
                try:
                    with open(arquivo, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    checklist = Checklist.from_dict(data)
                    checklists[checklist.item_id] = checklist
                except Exception as e:
                    logger.warning(f"Erro ao carregar checklist {arquivo}: {e}")
        return checklists
    
    def salvar_checklist_local(self, checklist: Checklist) -> None:
        """Salva checklist local no disco."""
        CHECKLISTS_DIR.mkdir(parents=True, exist_ok=True)
        arquivo = CHECKLISTS_DIR / f"{checklist.item_id}.json"
        try:
            with open(arquivo, "w", encoding="utf-8") as f:
                json.dump(checklist.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar checklist {checklist.item_id}: {e}")
    
    def carregar_itens_do_zip(self) -> List[Item]:
        """Descobre itens no ZIP e carrega checklists locais associados."""
        if not self._zip_path or not self._zip_path.exists():
            logger.warning("ZIP não configurado ou não existe")
            return []
        
        checklists_locais = self.carregar_checklists_locais()
        itens = descobrir_itens_zip(self._zip_path, self._zip_senha, CACHE_DIR)
        
        # Associar checklists locais aos itens descobertos
        for item in itens:
            if item.id in checklists_locais:
                item.checklist = checklists_locais[item.id]
        
        return itens
    
    def definir_itens(self, itens: List[Item]) -> None:
        """Define a lista de itens e reconstrói índices."""
        self._itens = {item.id: item for item in itens}
        self._categorias = {}
        for item in itens:
            # Usar categoria como chave principal (compatibilidade com código existente)
            # Se tiver marca/linha, criar chaves compostas também
            key = item.categoria if item.categoria else (item.marca if item.marca else 'Geral')
            self._categorias.setdefault(key, []).append(item.id)
        self._inicializado = True
        logger.info(f"Estado carregado: {len(itens)} itens em {len(self._categorias)} grupos")
    
    @property
    def itens(self) -> Dict[str, Item]:
        return self._itens
    
    @property
    def categorias(self) -> Dict[str, List[str]]:
        return self._categorias
    
    def get_item(self, item_id: str) -> Optional[Item]:
        return self._itens.get(item_id)
    
    def get_itens_categoria(self, categoria: str) -> List[Item]:
        ids = self._categorias.get(categoria, [])
        return [self._itens[id_] for id_ in ids if id_ in self._itens]
    
    def get_itens_marca(self, marca: str) -> List[Item]:
        """Retorna itens de uma marca específica."""
        return [item for item in self._itens.values() if item.marca.lower() == marca.lower()]
    
    def get_itens_linha(self, linha: str) -> List[Item]:
        """Retorna itens de uma linha específica."""
        return [item for item in self._itens.values() if item.linha.lower() == linha.lower()]
    
    @property
    def item_atual_id(self) -> Optional[str]:
        return self._item_atual_id
    
    @item_atual_id.setter
    def item_atual_id(self, value: Optional[str]) -> None:
        self._item_atual_id = value
    
    @property
    def item_atual(self) -> Optional[Item]:
        if self._item_atual_id:
            return self._itens.get(self._item_atual_id)
        return None
    
    @property
    def inicializado(self) -> bool:
        return self._inicializado


# Instância global (singleton)
app_state = AppState()