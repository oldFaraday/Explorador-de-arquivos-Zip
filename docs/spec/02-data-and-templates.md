# Spec 02: Modelos de Dados, Schemas e Templates

## 1. Dataclasses do Sistema (`models.py`)

A aplicação utiliza as seguintes representações de dados padronizadas:

```python
from dataclasses import dataclass
from typing import List
from pathlib import Path

@dataclass
class ChecklistEntry:
    data: str              # ISO 8601: "2026-10-02T14:30:00"
    conferente: str        # Nome do usuário / auditor
    status: str            # "OK" | "NOK" | "PENDENTE"
    observacao: str        # Texto livre informativo

@dataclass
class Checklist:
    item_id: str           # Slug único: ex: "chips_lisa_cebola_salsa_115g"
    historico: List[ChecklistEntry]

@dataclass
class Item:
    id: str                # Slug único
    nome: str              # Nome legível: "Chips Lisa Cebola Salsa 115g"
    categoria: str         # "Chips Lisa"
    pasta_zip: str         # Caminho relativo dentro do arquivo ZIP
    pdf_path: Path         # Caminho em cache para "Conferencia Visual.pdf"
    docx_path: Path        # Caminho em cache para "Descricao Tecnica.docx"
    checklist: Checklist   # Histórico associado ao item

@dataclass
class SyncState:
    zip_hash: str          # Hash SHA-256 do arquivo ZIP sincronizado
    ultimo_sync: str       # Timestamp ISO 8601 do último sync
    versao_app: str        # Versão do software (ex: "1.0.0")
```

---

## 2. Formato do Arquivo `checklist.json`

Cada SKU mantém um histórico individual estruturado no seguinte padrão JSON:

```json
{
  "item_id": "chips_lisa_cebola_salsa_115g",
  "historico": [
    {
      "data": "2026-10-02T14:30:00",
      "conferente": "João Silva",
      "status": "OK",
      "observacao": "Cores conferidas com o padrão mestre."
    },
    {
      "data": "2026-10-01T09:15:00",
      "conferente": "Maria Santos",
      "status": "OK",
      "observacao": ""
    }
  ]
}
```

---

## 3. Especificação do Template DOCX (`Descricao Tecnica.docx`)

O template em `resources/templates/docx_template.docx` deve obrigatoriamente seguir a hierarquia de títulos para correta conversão semântica via `mammoth`:

```markdown
# [Título 1] Nome do Produto (ex: Chips Lisa Cebola Salsa 115g)

## [Título 2] Identificação
* **Código SAP:** [Código]
* **Fornecedor:** [Nome do Fornecedor]
* **Versão da Arte:** [v1.0 - DD/MM/AAAA]
* **Data Aprovação:** [DD/MM/AAAA]
* **Aprovado por:** [Nome - Engenharia]

## [Título 2] Especificações Técnicas
### [Título 3] Dimensões
* **Largura:** [mm]
* **Comprimento:** [mm/m]
* **Espessura:** [µm]

### [Título 3] Material
* **Estrutura:** [ex: PET/PE, BOPP/PE]
* **Tratamento:** [Corona, Primer, etc.]

### [Título 3] Impressão
* **Cores:** [Pantone / CMYK + Especial]
* **Processo:** [Flexografia, Rotogravura]

### [Título 3] Acabamento
* **Faca / Corte:** [Código da faca]
* **Selagem:** [Temperatura, pressão, tempo]

## [Título 2] Validação Visual
* **Referência:** [Nome do arquivo PDF correspondente]
* **Observações:** [Campos textuais livres]
```

---

## 4. Padrão do Arquivo PDF (`Conferencia Visual.pdf`)

* **Quantidade de Páginas:**
  * Linha Chips: 3 páginas.
  * Linha Palha: 1 página.
* **Layout Página 1:** Arte técnica composta (Frente e Verso sobrepostos em posições padronizadas).
* **Layout Páginas 2 e 3:** Especificações vetoriais de faca, marcas de registro e guia de cores.
* **Resolução Mínima:** 300 DPI na origem da exportação.
* **Nomenclatura Obrigatória:** `Conferencia Visual.pdf` dentro da pasta individual do SKU.