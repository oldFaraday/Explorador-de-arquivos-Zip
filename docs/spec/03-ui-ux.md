# Spec 03: Interface de Usuário (UI/UX) e Jornadas

## 1. Arquitetura da Janela Principal (`MainWindow`)

A interface foi desenhada no framework **PySide6** focando em agilidade operacional no ambiente de fábrica/recebimento.

* **Dimensões:** Resolução padrão `1400x900` (Resolução mínima suportada: `1000x700`).
* **Estrutura Base:** `QSplitter` horizontal dividindo em 2 painéis principais:
  * Painel Esquerdo (25% de largura): Navegação e árvore de produtos.
  * Painel Direito (75% de largura): Especificação técnica e visualização gráfica.

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Barra de Ferramentas: [🔄 Recarregar] [☁ Sincronizar] [⚙ Config] [ℹ Sobre] [✕]   │
├──────────────────────┬───────────────────────────────────────────────────────────┤
│ 🔍 [ Buscar SKU... ] │ 📄 Descrição Técnica (DOCX → HTML via QWebEngineView)     │
├──────────────────────┤ [Zoom +] [Zoom -] [Reset] [Imprimir]                      │
│ 📁 Chips Lisa        ├───────────────────────────────────────────────────────────┤
│   ├── Cebola Salsa   │ 👁️ Conferência Visual (PDF via pdfium)                    │
│   └── Clássica 70g   │ [◀ Ante] [Pág X de Y] [Próx ▶] [Zoom % ▼] [Ajustar] [🔄]  │
│ 📁 Chips Ondulada    │                                                           │
│ 📁 Palha             │ [ 📝 Registra Conferência ("Conferir") ]                  │
├──────────────────────┴───────────────────────────────────────────────────────────┤
│ Status: Item: Chips Lisa 115g | Última conf.: João (02/10 OK) | ☁ Sync OK  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Detalhamento dos Componentes

### 2.1 Painel Esquerdo (Navegação)
* **Campo de Busca:** `QLineEdit` com filtro em tempo real sobre a lista de SKUs.
* **Árvore de Produtos:** `QTreeView` populado por `QStandardItemModel`.
  * Nós Raiz: Categorias (ex: *Chips Lisa*, *Palha*).
  * Nós Filhos: SKUs com nome amigável.
* **Menu de Contexto (Botão Direito):**
  * *Abrir pasta no cache* (abre o Windows Explorer no diretório local do item).
  * *Copiar ID do item* (copia o slug único para o clipboard).

### 2.2 Painel Direito (Visualização e Mídia)
Dividido por um `QSplitter` vertical (60% topo / 40% base):

* **Topo (Descrição Técnica):**
  * `QWebEngineView` para exibição do HTML gerado a partir do DOCX.
  * Barra de ferramentas rápida: Zoom In/Out, Reset e Imprimir.
* **Base (Conferência Visual):**
  * Visualizador PDF customizado derivado de `QWidget` renderizado via `pdfium-python` + `QPainter`.
  * Toolbars de atalho: Navegação entre páginas, controles de Zoom (50% a 200%, Ajustar Largura, Ajustar Página) e Rotação 90°.
  * Interações avançadas: Navegação pelas setas do teclado, Scroll + Ctrl para zoom e Drag-and-drop para Pan.

### 2.3 Barra de Status Inferior (`QStatusBar`)
* **Seção Esquerda:** SKU e Categoria ativos.
* **Seção Central:** Resumo da última conferência (`Conferente — Data/Hora — Status`).
* **Seção Direita:** Indicador visual do estado da sincronização (`☁ Sincronizado`, `⚠ Fora de Sync` ou `✓ Sync OK`).

---

## 3. Diálogos e Modais

### 3.1 Modal de Conferência (`Conferir`)
* **Campos:**
  * Conferente (`QLineEdit` com autocomplete das últimas entradas).
  * Status (`QComboBox`: `OK`, `NOK`, `PENDENTE`).
  * Observação (`QTextEdit` multinível opcional).
* **Ações:** `[Cancelar]`, `[Salvar Local]` e `[Salvar e Sincronizar Agora]`.

### 3.2 Modal de Sincronização
* Exibe barra de progresso e log de execução detalhado em tempo real (*Lendo ZIP...*, *Merge de Checklists...*, *Gravando...*).
* Exibe card com o resumo da operação (*Enviados: X*, *Recebidos: Y*, *Conflitos: Z*).

### 3.3 Modal de Configurações
* **Aba Geral:** Caminho do arquivo ZIP na rede, senha do ZIP (com visualização opcional) e opção de auto-recarregar ao iniciar.
* **Aba Avançado:** Exibição dos caminhos de cache/checklists com opções para limpeza de temporários.

---

## 4. Estilização Visual (`styles.qss`)
* Tema profissional claro (Branco, Cinza Claro e Azul `#0056A0`).
* Cor de seleção e destaque: `#0056A0`.
* Fundo do visualizador de PDF em tom escuro (`#2D2D2D`) para contraste de validação de cores de embalagem.

---

## 5. Jornadas do Usuário (User Journeys)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Primeira Execução                                                   │
│ Exe copiado → App Solicita Senha ZIP → Extrai Cache → Exibe Árvore     │
└────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. Rotina de Recebimento (Qualidade)                                   │
│ Clica "Recarregar" → Seleciona SKU → Confere DOCX + PDF vs. Físico →    │
│ Clica "Conferir" → Digita Dados → Salva Local → "Sincronizar"         │
└────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. Rotina de Atualização (Engenharia)                                  │
│ Substitui PDF/DOCX no Embalagens.zip de Rede → Notifica Qualidade      │
└────────────────────────────────────────────────────────────────────────┘
```