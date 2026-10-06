# Spec 05: Descoberta Genérica de Estrutura no ZIP — Arquitetura Adaptável

## 1. Contexto Atual

O arquivo de referência **`ITENS PARA CONFERÊNCIA.zip`** (estrutura hierárquica 4 níveis: Raiz → Marca → Linha → Item) foi removido/renomeado. O único ZIP presente no projeto é **`Embalagens.zip`** (estrutura legada MVP, 2 níveis: Categoria → Item).

A pasta `PDF/` contém apenas 6 PDFs da linha Palha (os 11 PDFs de Chips foram removidos).

> **Decisão de projeto:** O código **não deve assumir estrutura fixa**. A descoberta de itens deve ser **genérica e baseada em heurística de conteúdo** (presença dos 3 arquivos obrigatórios), funcionando para qualquer organização de pastas — seja a legada, a hierárquica removida, ou futuras variações.

---

## 2. Princípio: Descoberta por Conteúdo, Não por Caminho

Uma pasta é **item (SKU)** se e somente se contiver os **3 arquivos obrigatórios**:

| Arquivo | Nome | Obrigatório? | Observação |
|---------|------|--------------|------------|
| Especificação técnica | `Descricao Tecnica.docx` | **Sim** | Nome fixo |
| Checklist | `checklist.json` | **Sim** | Nome fixo |
| Conferência visual | `*.pdf` (qualquer nome) | **Sim** | **Único** PDF na pasta |

```python
# crypto.py — Heurística única de detecção
def eh_pasta_item(arquivos: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Retorna (True, nome_do_pdf) se a pasta contém os 3 arquivos obrigatórios.
    Funciona para QUALQUER profundidade e nomenclatura de pastas.
    """
    tem_docx = 'Descricao Tecnica.docx' in arquivos
    tem_checklist = 'checklist.json' in arquivos
    pdfs = [f for f in arquivos if f.lower().endswith('.pdf')]
    
    if tem_docx and tem_checklist and len(pdfs) == 1:
        return True, pdfs[0]
    return False, None
```

**Consequências:**
- Estrutura legada (`Categoria/Item/`) → funciona
- Estrutura hierárquica (`Marca/Linha/Categoria/Item/`) → funciona
- Estrutura futura (`Fornecedor/Tipo/Material/Item/`) → funciona
- Pastas de agrupamento sem os 3 arquivos → ignoradas automaticamente

---

## 3. Geração de `item_id` (Slug Único e Estável)

Derivado do **caminho relativo completo** da pasta do item dentro do ZIP:

```python
def gerar_item_id(caminho_relativo: Path) -> str:
    """
    Exemplo legada:     'Chips Lisa/Cebola Salsa 115g'           → 'chips_lisa_cebola_salsa_115g'
    Exemplo hierárquica: 'BOBINAS DE EMBALAGEM/ASSAÍ/CHIPS/...' → 'bobinas_embalagem_assai_chips_lisa_cebola_e_salsa_115g'
    """
    slug = str(caminho_relativo).replace('\\', '/').lower()
    slug = slug.replace(' ', '_')
    # Normalização básica de acentos
    for a, b in [('ç','c'),('á','a'),('à','a'),('ã','a'),('é','e'),('ê','e'),('í','i'),('ó','o'),('ô','o'),('õ','o'),('ú','u')]:
        slug = slug.replace(a, b)
    slug = re.sub(r'[^a-z0-9_]', '', slug)
    return slug
```

> **Garantia:** Mesmo caminho → mesmo `item_id` → checklists locais e sync funcionam sem migração, independente da estrutura.

---

## 4. Modelo `Item` Atualizado (`models.py`)

```python
@dataclass
class Item:
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
```

**Extração automática de metadados hierárquicos (opcional, para UI):**
```python
def extrair_metadados_do_caminho(pasta_zip: str) -> Tuple[str, str, str]:
    partes = pasta_zip.split('/')
    # Assume: [raiz]/[marca]/[linha]/[categoria]/[item]  OU  [categoria]/[item]
    if len(partes) >= 4:
        return partes[-4], partes[-3], partes[-2]  # marca, linha, categoria
    elif len(partes) >= 2:
        return '', partes[-2], ''  # apenas categoria (legado)
    return '', '', ''
```

---

## 5. Função Principal: `descobrir_itens_zip()` (`crypto.py`)

```python
def descobrir_itens_zip(zip_path: Path, senha: str, cache_dir: Path) -> List[Item]:
    """
    1. Extrai ZIP para cache_dir (função existente extrair_zip_seguro).
    2. Percorre recursivamente (os.walk) a partir da raiz extraída.
    3. Para cada diretório, aplica eh_pasta_item().
    4. Se True: cria Item com metadados derivados do caminho.
    5. Retorna lista ordenada alfabeticamente por (marca, linha, categoria, nome).
    """
    itens = []
    for root, dirs, files in os.walk(cache_dir):
        rel_root = Path(root).relative_to(cache_dir)
        if rel_root == Path('.'):
            continue
        
        eh_item, pdf_nome = eh_pasta_item(files)
        if not eh_item:
            continue
        
        caminho_relativo = str(rel_root).replace('\\', '/')
        item_id = gerar_item_id(rel_root)
        marca, linha, categoria = extrair_metadados_do_caminho(caminho_relativo)
        nome_pasta = rel_root.parts[-1]
        nome_amigavel = nome_pasta.replace('_', ' ').title()
        
        itens.append(Item(
            id=item_id,
            nome=nome_amigavel,
            marca=marca.title() if marca else '',
            linha=linha.title() if linha else '',
            categoria=categoria.title() if categoria else '',
            pasta_zip=caminho_relativo,
            pdf_nome=pdf_nome,
            pdf_path=Path(root) / pdf_nome,
            docx_path=Path(root) / 'Descricao Tecnica.docx',
            checklist=Checklist(item_id, [])
        ))
    
    return sorted(itens, key=lambda i: (i.marca or 'zzz', i.linha or 'zzz', i.categoria or 'zzz', i.nome))
```

---

## 6. Validação de Estrutura (`validar_estrutura_zip`)

```python
def validar_estrutura_zip(zip_path: Path, senha: str) -> List[str]:
    erros = []
    avisos = []
    
    with tempfile.TemporaryDirectory() as tmp:
        extrair_zip_seguro(zip_path, senha, Path(tmp))
        itens = descobrir_itens_zip(zip_path, senha, Path(tmp))
        
        if not itens:
            erros.append("Nenhum item (SKU) válido encontrado. Verifique se as pastas contêm: Descricao Tecnica.docx, checklist.json e exatamente 1 arquivo .pdf")
        
        # Duplicatas de item_id
        ids = [i.id for i in itens]
        duplicados = [id_ for id_ in set(ids) if ids.count(id_) > 1]
        if duplicados:
            erros.append(f"IDs duplicados (conflito de slug): {duplicados}")
        
        # Avisos informativos
        for item in itens:
            if not item.marca and not item.linha and not item.categoria:
                avisos.append(f"Item sem hierarquia detectada (estrutura plana): {item.pasta_zip}")
            if item.pdf_nome != 'Conferencia Visual.pdf':
                avisos.append(f"PDF com nome não-padrão: {item.pasta_zip}/{item.pdf_nome}")
    
    return erros + avisos
```

---

## 7. Adaptações na Interface (`ui.py` / `state.py`)

### 7.1 TreeView — Construção Dinâmica por Profundidade

```python
def popular_arvore(self, itens: List[Item]):
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(['Produtos'])
    
    # Agrupa dinamicamente pelos metadados disponíveis
    raizes = {}  # marca → node
    for item in itens:
        if item.marca:
            # Estrutura hierárquica: Marca → Linha → Categoria → Item
            marca_node = raizes.get(item.marca)
            if not marca_node:
                marca_node = QStandardItem(f'🏷️  {item.marca}')
                marca_node.setData({'tipo': 'marca'}, Qt.UserRole)
                model.appendRow(marca_node)
                raizes[item.marca] = marca_node
            
            linha_node = self._get_or_create_child(marca_node, item.linha, 'linha')
            cat_node = self._get_or_create_child(linha_node, item.categoria, 'categoria')
            parent = cat_node
        else:
            # Estrutura plana (legado): Categoria → Item
            cat_node = raizes.get(item.categoria or 'Geral')
            if not cat_node:
                cat_node = QStandardItem(f'📁  {item.categoria or "Geral"}')
                cat_node.setData({'tipo': 'categoria'}, Qt.UserRole)
                model.appendRow(cat_node)
                raizes[item.categoria or 'Geral'] = cat_node
            parent = cat_node
        
        item_node = QStandardItem(f'📦  {item.nome}')
        item_node.setData({'tipo': 'item', 'item_id': item.id}, Qt.UserRole)
        item_node.setToolTip(item.pasta_zip)
        parent.appendRow(item_node)
    
    self.tree_view.setModel(model)
    self.tree_view.expandAll()
```

### 7.2 Busca Recursiva (Funciona em Qualquer Estrutura)

```python
def filtrar_arvore(self, texto: str):
    proxy = QSortFilterProxyModel(self)
    proxy.setSourceModel(self.tree_model)
    proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
    proxy.setFilterKeyColumn(0)
    proxy.setFilterFixedString(texto)
    proxy.setRecursiveFilteringEnabled(True)  # Mostra pais se filho der match
    self.tree_view.setModel(proxy)
```

### 7.3 Resolução de PDF no Painel Direito

```python
def ao_selecionar_item(self, index):
    item_data = index.data(Qt.UserRole)
    if not item_data or item_data.get('tipo') != 'item':
        self.limpar_painel_direito()
        return
    
    item = self.state.get_item(item_data['item_id'])
    
    # PDF: usa pdf_nome detectado (funciona para 'Conferencia Visual.pdf' OU 'Palha Extrafina 100g.pdf')
    self.pdf_viewer.carregar(item.pdf_path)
    
    # DOCX: sempre 'Descricao Tecnica.docx'
    html = docx_para_html(item.docx_path)
    self.web_view.setHtml(html)
    
    # Status bar
    self.atualizar_statusbar(item)
```

---

## 8. Compatibilidade com Estruturas Conhecidas

| Estrutura ZIP | Funciona? | Observação |
|---------------|-----------|------------|
| `Embalagens.zip` (atual, legada) | ✅ | 2 níveis, PDF fixo `Conferencia Visual.pdf` |
| `ITENS PARA CONFERÊNCIA.zip` (removido) | ✅ | 4 níveis, PDF variável na linha Palha |
| Qualquer nova estrutura | ✅ | Desde que respeite a regra dos 3 arquivos |

---

## 9. Migração de Checklists Locais (Se houver mudança de `item_id`)

Se a estrutura do ZIP mudar e alterar os caminhos relativos → `item_id` muda → checklists locais ficam "órfãos".

**Solução:** Mapeamento hardcoded para os SKUs conhecidos do MVP (executa uma vez na 1ª inicialização):

```python
MAPA_MIGRACAO_LEGADO = {
    # Estrutura legada → Nova estrutura (se aplicável)
    'chips_lisa_cebola_salsa_115g': 'bobinas_embalagem_assai_chips_lisa_cebola_e_salsa_115g',
    'chips_lisa_cebola_salsa_70g': 'bobinas_embalagem_assai_chips_lisa_cebola_e_salsa_70g',
    'chips_lisa_classica_115g': 'bobinas_embalagem_assai_chips_lisa_classica_115g',
    'chips_lisa_classica_70g': 'bobinas_embalagem_assai_chips_lisa_classica_70g',
    'chips_ondulada_cebola_salsa_115g': 'bobinas_embalagem_assai_chips_ondulada_cebola_e_salsa_115g',
    'chips_ondulada_cebola_salsa_68g': 'bobinas_embalagem_assai_chips_ondulada_cebola_e_salsa_68g',
    'chips_ondulada_cheddar_bacon_115g': 'bobinas_embalagem_assai_chips_ondulada_cheddar_e_bacon_115g',
    'chips_ondulada_classica_115g': 'bobinas_embalagem_assai_chips_ondulada_classica_115g',
    'chips_ondulada_classica_68g': 'bobinas_embalagem_assai_chips_ondulada_classica_68g',
    'chips_ondulada_picanha_115g': 'bobinas_embalagem_assai_chips_ondulada_picanha_115g',
    'chips_ondulada_pimenta_mexicana_115g': 'bobinas_embalagem_assai_chips_ondulada_pimenta_mexicana_115g',
    'palha_extrafina_100g': 'bobinas_embalagem_assai_palha_extrafina_100g',
    'palha_extrafina_400g': 'bobinas_embalagem_assai_palha_extrafina_400g',
    'palha_tradicional_100g': 'bobinas_embalagem_assai_palha_tradicional_100g',
    'palha_tradicional_200g': 'bobinas_embalagem_assai_palha_tradicional_200g',
    'palha_tradicional_400g': 'bobinas_embalagem_assai_palha_tradicional_400g',
    'palha_tradicional_800g': 'bobinas_embalagem_assai_palha_tradicional_800g',
}

def migrar_checklists_se_necessario(checklists_dir: Path):
    for antigo, novo in MAPA_MIGRACAO_LEGADO.items():
        old_path = checklists_dir / f'{antigo}.json'
        new_path = checklists_dir / f'{novo}.json'
        if old_path.exists() and not new_path.exists():
            shutil.move(old_path, new_path)
            logger.info(f'Checklist migrado: {antigo} → {novo}')
```

> **Nota:** Como o `ITENS PARA CONFERÊNCIA.zip` foi removido, esta migração só será necessária se um novo ZIP com estrutura hierárquica for introduzido no futuro. O código fica pronto.

---

## 10. Atualização do `gerar_zip_inicial.py`

Deve gerar a estrutura **atualmente em uso** (`Embalagens.zip` legada) como padrão, mas preparado para expansão:

```python
ESTRUTURA_PADRAO = {
    'Chips Lisa': [
        'Cebola Salsa 115g',
        'Cebola Salsa 70g',
        'Classica 115g',
        'Classica 70g',
    ],
    'Chips Ondulada': [
        'Cebola Salsa 115g',
        'Cebola Salsa 68g',
        'Cheddar Bacon 115g',
        'Classica 115g',
        'Classica 68g',
        'Picanha 115g',
        'Pimenta Mexicana 115g',
    ],
    'Palha Extrafina': [
        '100g',
        '400g',
    ],
    'Palha Tradicional': [
        '100g',
        '200g',
        '400g',
        '800g',
    ],
}
# PDFs sempre 'Conferencia Visual.pdf' (padrão legada)
# Futuro: adicionar opção de gerar estrutura hierárquica com marcas
```

---

## 11. Checklist de Validação

| Teste | Critério |
|-------|----------|
| Carregar `Embalagens.zip` atual | 17 itens descobertos, árvore 2 níveis (Categoria → Item) |
| PDFs `Conferencia Visual.pdf` | Abrem corretamente no visualizador |
| Busca por "Cebola" | Filtra itens de Chips Lisa e Ondulada |
| Busca por "Tradicional" | Filtra itens de Palha |
| Conferir → Sync → Recarregar | Histórico preservado, merge OK |
| Simular ZIP hierárquico (teste) | Descoberta automática 4 níveis, PDFs variáveis funcionam |
| Migração checklists | Se houver `item_id` antigo órfão, migra para novo |

---

## 12. Arquivos a Modificar (Resumo)

| Arquivo | Função/Classe | Ação |
|---------|---------------|------|
| `crypto.py` | `eh_pasta_item()`, `gerar_item_id()`, `descobrir_itens_zip()`, `validar_estrutura_zip()` | **Adicionar/Atualizar** — núcleo da descoberta genérica |
| `models.py` | `Item` | **Estender** — adicionar `pasta_zip`, `pdf_nome`, `marca`, `linha`, `categoria` |
| `state.py` | `carregar_arvore()` | **Atualizar** — usar `descobrir_itens_zip()` |
| `ui.py` | `popular_arvore()`, `filtrar_arvore()`, `ao_selecionar_item()` | **Atualizar** — TreeView dinâmica, busca recursiva, resolução PDF por `pdf_nome` |
| `gerar_zip_inicial.py` | `ESTRUTURA_PADRAO` | **Atualizar** — gerar estrutura legada atual |
| `main.py` | `inicializar()` | **Adicionar** — chamada a `migrar_checklists_se_necessario()` na 1ª execução |

---

## 13. Observações Finais

1. **Zero dependência de estrutura fixa** — o código descobre itens pelo conteúdo, não pelo caminho.
2. **PDFs com nomes variáveis** — suportado nativamente via detecção do único `.pdf` na pasta.
3. **Hierarquia opcional na UI** — se o ZIP tiver profundidade ≥ 3, a TreeView mostra Marca/Linha/Categoria; se for plana, mostra apenas Categoria.
4. **Futuro-proof** — qualquer nova organização de pastas (fornecedores, tipos, materiais) funcionará sem mudança de código.
5. **`ITENS PARA CONFERÊNCIA.zip` removido** — este spec documenta a capacidade genérica; o ZIP legada `Embalagens.zip` é o padrão atual.

---

*Documento atualizado em 05/10/2026 — Versão 2.0*  
*Reflete a remoção do arquivo de referência hierárquico e a decisão por descoberta genérica baseada em conteúdo.*