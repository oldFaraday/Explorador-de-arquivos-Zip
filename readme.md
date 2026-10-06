# Explorador de Arquivos Zip

> Aplicação **standalone Windows (.exe)** para navegação, visualização e validação de arquivos em pacotes ZIP criptografados. Conecta **Especificações Técnicas** (definição de padrões) e **Inspeção de Recebimento** (conferência física).

---

## 🎯 Objetivo

Validar fisicamente itens recebidos contra especificações técnicas aprovadas, com registro de conferência offline-first e sincronização bidirecional com compartilhamento de rede.

### Funcionalidades Principais

| Funcionalidade | Descrição |
|----------------|-----------|
| **Navegação Hierárquica** | Marca → Linha → Categoria → Item (compatível com estrutura legada Categoria → Item) |
| **Especificação Técnica** | DOCX renderizado como HTML (mammoth) com zoom e impressão |
| **Visualizador PDF Integrado** | pypdfium2 nativo — zoom, rotação, pan, navegação de páginas, ajuste à largura |
| **Registro de Conferência** | Nome, data/hora, status (OK/NOK/PENDENTE), observações — persistido localmente |
| **Recarregar (F5)** | Atualiza especificações do ZIP de rede (AES-256) para cache local |
| **Sincronizar (Ctrl+S)** | Merge bidirecional de checklists (local ↔ ZIP) com deduplicação por (data, conferente) |
| **Descoberta Genérica** | Detecta itens por conteúdo (3 arquivos obrigatórios), não por caminho fixo |

---

## 📦 Escopo Inicial (MVP)

17 SKUs em 4 categorias:

| Categoria | Itens |
|-----------|-------|
| **Chips Lisa** | Cebola Salsa 115g, Churrasco 70g, Clássica 70g, Queijo 80g |
| **Chips Ondulada** | Clássica 115g, Clássica 68g, Picanha 115g, Pimenta Mexicana 115g |
| **Palha Extrafina** | Ervas Finas 100g, Sal Marinho 100g, Tradicional 100g, Tradicional 400g |
| **Palha Tradicional** | Cebola & Alho 200g, Tradicional 100g, Tradicional 200g |

---

## 🏗️ Arquitetura

```
ExploradorZip/
├── main.py                 # Entry point, inicialização, configurações UTF-8
├── crypto.py               # ZIP AES-256 (pyzipper), descoberta genérica de itens
├── parser.py               # DOCX→HTML (mammoth), PDF utils (pypdfium2)
├── sync.py                 # Merge bidirecional de checklists com dedup
├── ui.py                   # PySide6: MainWindow, TreeView, WebEngine, PDFViewer
├── state.py                # AppState singleton, cache local (%APPDATA%), migração IDs
├── models.py               # Dataclasses: Item, Checklist, ChecklistEntry, SyncState
├── build_exe.py            # PyInstaller build com hooks pypdfium2/PIL
├── gerar_zip_inicial.py    # Gera ZIP inicial com 17 SKUs de exemplo
├── requirements.txt        # Dependências
├── resources/
│   ├── icon.ico            # Ícone da aplicação
│   └── styles.qss          # Tema visual
└── docs/spec/              # Documentação técnica (Spec Kit)
```

### Fluxo de Dados

```
┌─────────────┐     AES-256      ┌────────────────────┐     Cache Local      ┌──────────────┐
│ Share Rede  │ ──────────────► │ ExploradorZip.exe  │ ──────────────────► │ %APPDATA%    │
│ Itens.zip   │    .zip         │  (offline-first)   │   itens + checklists │ \Explorador  │
└─────────────┘                 └────────────────────┘                    └──────────────┘
       ▲                              │                                      │
       │           Sincronização      │           Merge (data, conferente)   │
       └──────────────────────────────┴──────────────────────────────────────┘
```

---

## 🛠️ Stack Tecnológico

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **Python** | 3.11+ | Runtime |
| **PySide6** | 6.10+ | GUI nativa (Qt6) com WebEngine |
| **mammoth** | 1.9+ | DOCX → HTML semântico |
| **pypdfium2** | 5.13+ | Renderização PDF nativa (rápida, sem dependências externas) |
| **pyzipper** | 0.3+ | ZIP AES-256 (leitura/escrita) |
| **watchdog** | 3.0+ | Monitoramento de alterações (opcional) |

---

## 🚀 Build e Deploy

### 1. Ambiente de Desenvolvimento

```bash
# Clonar repositório
git clone <repo-url>
cd ExploradorZip

# Criar venv e instalar dependências
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Gerar ZIP de teste (opcional)
python gerar_zip_inicial.py

# Executar em modo dev
python main.py
```

### 2. Compilação para Produção

```bash
# Limpar builds anteriores e compilar
python build_exe.py

# Executável final: dist/ExploradorZip.exe (~220 MB)
# O tamanho inclui QtWebEngine (Chromium) + pypdfium2 + PIL
```

> **Nota:** O build usa hooks personalizados (`hooks/hook-pypdfium2.py`) para incluir `pypdfium2_raw/pdfium.dll` e `PIL` no executável — essencial para renderização de PDF funcionar no .exe compilado.

### 3. Implantação no Share de Rede

```
\\Servidor\Share\ExploradorZip\
├── ExploradorZip.exe              # Executável compilado
├── Itens.zip                      # ZIP AES-256 com especificações (senha configurável)
└── Explorador de Arquivos Zip.lnk # Atalho para usuários finais
```

**Requisitos do Share:**
- Leitura/escrita para usuários de Recebimento
- Backup automático do ZIP (o app cria `.backup_YYYYMMDD_HHMMSS.zip` antes de sincronizar)

---

## 🔐 Segurança

- **ZIP criptografado:** AES-256 via `pyzipper` (compatível WinZip/7-Zip)
- **Senha padrão:** configurável na primeira execução
- **Checklists locais:** JSON em `%APPDATA%\ExploradorZip\checklists\`
- **Logs:** `%APPDATA%\ExploradorZip\logs\app_YYYYMMDD.log`
- **Migração de IDs:** Executada uma única vez ao detectar mudança de estrutura de pastas

---

## 📋 Uso (Usuário Final)

1. **Abrir:** Clique no atalho `Explorador de Arquivos Zip.lnk`
2. **Primeira execução:** Digite a senha do ZIP e caminho do share (salvo localmente)
3. **Navegar:** Use a árvore lateral ou busca (`🔍 Buscar SKU...`)
4. **Conferir:**
   - Selecione um item → Especificação técnica (topo) + PDF visual (base)
   - Clique **📝 Registrar Conferência**
   - Preencha: Nome, Status (OK/NOK/PENDENTE), Observação
   - Salvar → Entrada adicionada ao histórico local
5. **Atualizar specs:** **Recarregar (F5)** → Baixa novo ZIP do share
6. **Sincronizar equipe:** **Sincronizar (Ctrl+S)** → Merge checklists local ↔ share

---

## 📚 Documentação Técnica (Spec Kit)

- [01. Arquitetura e Módulos](docs/spec/01-architecture-and-engine.md)
- [02. Modelos de Dados e Templates](docs/spec/02-data-and-templates.md)
- [03. Interface de Usuário (UI/UX)](docs/spec/03-ui-ux.md)
- [04. Backlog, Testes e Critérios de Aceite](docs/spec/04-tasks-and-acceptance.md)
- [05. Atualização da Estrutura de Pastas (Descoberta Genérica)](docs/spec/05-atualizacao-da-estrutura-de-pastas.md)
- [BUG: PDF não renderiza no .exe](docs/spec/BUG-pdf-nao-renderiza-exe.md) — *corrigido via hooks PyInstaller*

---

## 🧪 Testes de Aceite (Resumo)

| Critério | Status |
|----------|--------|
| 17 SKUs carregados e navegáveis | ✅ |
| DOCX renderizado como HTML fiel | ✅ |
| PDF renderiza inline (zoom, pan, rotação) | ✅ |
| Conferência persiste offline | ✅ |
| Recarregar atualiza cache do ZIP | ✅ |
| Sincronizar faz merge bidirecional sem perda | ✅ |
| Descoberta genérica funciona em qualquer profundidade | ✅ |
| Migração IDs legados → hierárquicos | ✅ |
| Executável roda sem Python instalado | ✅ |
| UTF-8 nativo (acentos em pastas/arquivos) | ✅ |

---

## 📄 Licença

Este projeto está licenciado sob a **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.

Você tem permissão para:
- **Compartilhar** — copiar e redistribuir o material em qualquer suporte ou formato
- **Adaptar** — remixar, transformar e criar a partir do material

Sob as seguintes condições:
- **Atribuição** — Você deve dar o crédito apropriado, fornecer um link para a licença e indicar se foram feitas alterações
- **Não Comercial** — Você não pode usar o material para fins comerciais
- **Sem restrições adicionais** — Você não pode aplicar termos legais ou medidas tecnológicas que restrinjam legalmente outros de fazerem algo que a licença permita

Consulte o texto completo em: https://creativecommons.org/licenses/by-nc/4.0/

---

## 📞 Contatos

| Papel | Responsável |
|-------|-------------|
| **Especificações Técnicas (Owner Specs)** | *Preencher* |
| **Inspeção de Recebimento (Owner Conferência)** | *Preencher* |
| **TI / Desenvolvimento** | *Preencher* |
| **Gestor da Área** | *Preencher* |

---

## 📝 Changelog

### v1.1.0 (2026-10-06)
- ✅ Correção renderização PDF no .exe (hooks pypdfium2_raw + PIL)
- ✅ UTF-8 nativo no Windows (PYTHONUTF8=1, locale pt_BR)
- ✅ Ícones nativos Qt (SP_*) — visíveis em todas as versões Windows
- ✅ Toolbars com texto + ícone (ToolButtonTextBesideIcon)
- ✅ Descoberta genérica de itens (Spec 05) — qualquer profundidade
- ✅ Auto-fit PDF ao carregar e redimensionar janela

### v1.0.0 (2026-10-05)
- MVP completo: 17 SKUs, 4 categorias
- ZIP AES-256, cache offline, sync bidirecional
- UI PySide6 com tema profissional
- Build PyInstaller funcional