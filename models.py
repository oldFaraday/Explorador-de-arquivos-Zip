"""Modelos de dados do sistema Explorador de Arquivos Zip."""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import json


@dataclass
class ChecklistEntry:
    """Entrada individual de uma conferência."""
    data: str              # ISO 8601: "2026-10-02T14:30:00"
    conferente: str        # Nome do usuário / auditor
    status: str            # "OK" | "NOK" | "PENDENTE"
    observacao: str        # Texto livre informativo

    def __post_init__(self):
        # Validar status
        if self.status not in ("OK", "NOK", "PENDENTE"):
            raise ValueError(f"Status inválido: {self.status}. Use OK, NOK ou PENDENTE")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChecklistEntry":
        return cls(**data)

    @classmethod
    def create(cls, conferente: str, status: str, observacao: str = "") -> "ChecklistEntry":
        """Cria uma nova entrada com timestamp atual."""
        return cls(
            data=datetime.now().isoformat(timespec="seconds"),
            conferente=conferente.strip(),
            status=status.strip().upper(),
            observacao=observacao.strip()
        )


@dataclass
class Checklist:
    """Histórico de conferências de um item."""
    item_id: str                   # Slug único: ex: "chips_lisa_cebola_salsa_115g"
    historico: List[ChecklistEntry] = field(default_factory=list)

    def adicionar_entrada(self, entry: ChecklistEntry) -> None:
        """Adiciona entrada mantendo ordem cronológica e evitando duplicatas."""
        # Chave composta para deduplicação: (data, conferente)
        chave_nova = (entry.data, entry.conferente)
        
        # Remover duplicata se existir
        self.historico = [
            e for e in self.historico 
            if (e.data, e.conferente) != chave_nova
        ]
        
        # Adicionar nova entrada
        self.historico.append(entry)
        
        # Ordenar por data ascendente
        self.historico.sort(key=lambda e: e.data)

    def ultima_entrada(self) -> Optional[ChecklistEntry]:
        """Retorna a entrada mais recente."""
        return self.historico[-1] if self.historico else None

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "historico": [e.to_dict() for e in self.historico]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checklist":
        return cls(
            item_id=data["item_id"],
            historico=[ChecklistEntry.from_dict(e) for e in data.get("historico", [])]
        )

    def merge(self, outro: "Checklist") -> "Checklist":
        """Faz merge com outro checklist (usado na sincronização)."""
        resultado = Checklist(item_id=self.item_id)
        # Adicionar todas as entradas de ambos
        for entry in self.historico + outro.historico:
            resultado.adicionar_entrada(entry)
        return resultado


@dataclass
class Item:
    """Representa um SKU de embalagem."""
    id: str                      # Slug único (gerado do caminho)
    nome: str                    # Nome amigável para UI (derivado do nome da pasta)
    pasta_zip: str               # Caminho relativo completo no ZIP
    pdf_nome: str                # Nome real do arquivo PDF detectado
    pdf_path: Path               # Caminho no cache local
    docx_path: Path              # Caminho no cache local (sempre 'Descricao Tecnica.docx')
    checklist: Checklist
    
    # Campos opcionais para UI (extraídos do caminho se houver profundidade >= 3)
    marca: str = ''              # Ex: 'ASSAÍ' (nível 1 do caminho)
    linha: str = ''              # Ex: 'CHIPS' (nível 2)
    categoria: str = ''          # Ex: 'Lisa' (nível 3)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "marca": self.marca,
            "linha": self.linha,
            "categoria": self.categoria,
            "pasta_zip": self.pasta_zip,
            "pdf_nome": self.pdf_nome,
            "pdf_path": str(self.pdf_path),
            "docx_path": str(self.docx_path),
            "checklist": self.checklist.to_dict()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        return cls(
            id=data["id"],
            nome=data["nome"],
            marca=data.get("marca", ""),
            linha=data.get("linha", ""),
            categoria=data.get("categoria", ""),
            pasta_zip=data["pasta_zip"],
            pdf_nome=data.get("pdf_nome", "Conferencia Visual.pdf"),
            pdf_path=Path(data["pdf_path"]),
            docx_path=Path(data["docx_path"]),
            checklist=Checklist.from_dict(data["checklist"])
        )


@dataclass
class SyncState:
    """Estado da sincronização para controle de versão."""
    zip_hash: str          # Hash SHA-256 do arquivo ZIP sincronizado
    ultimo_sync: str       # Timestamp ISO 8601 do último sync
    versao_app: str        # Versão do software (ex: "1.0.0")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SyncState":
        return cls(**data)

    @classmethod
    def create(cls, zip_hash: str, versao_app: str) -> "SyncState":
        return cls(
            zip_hash=zip_hash,
            ultimo_sync=datetime.now().isoformat(timespec="seconds"),
            versao_app=versao_app
        )