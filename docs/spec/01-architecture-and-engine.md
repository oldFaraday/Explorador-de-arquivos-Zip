# Spec 01: Arquitetura Geral e Módulos Engine

## 1. Visão Geral da Arquitetura

O sistema opera com um modelo **Offline-First** utilizando um repositório centralizado compactado com criptografia AES-256 em um compartilhamento de rede (Share Windows).

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  SHARE DE REDE (\\Servidor\Share\Embalagens.zip)                             │
│  Criptografado com senha AES-256 (padrão 7-Zip/WinRAR)                       │
│  Estrutura interna:                                                          │
│  Embalagens.zip/                                                             │
│  ├── Chips Lisa/                                                             │
│  │   ├── Cebola Salsa 115g/                                                 │
│  │   │   ├── Conferencia Visual.pdf    ← Engenharia atualiza                │
│  │   │   ├── Descricao Tecnica.docx     ← Engenharia atualiza                │
│  │   │   └── checklist.json             ← Master (sincronização periódica)  │
│  │   └── Classica 70g/                                                      │
│  ├── Chips Ondulada/                                                         │
│  └── Palha/                                                                  │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                        [Recarregar]  │  [Sincronizar]
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  LOCAL (%APPDATA%\ValidadorEmbalagens\)                                     │
│  ├── cache/                    ← Extração do ZIP (PDF, DOCX) — read-only    │
│  │   └── chips_lisa/cebola_salsa_115g/                                      │
│  ├── checklists/               ← Checklists LOCAIS (escrita imediata)       │
│  │   └── chips_lisa_cebola_salsa_115g.json                                 │
│  └── sync_state.json           ← { zip_hash, ultimo_sync, versao_app }     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Princípios Fundamentais
* **Apenas Leitura no ZIP:** O aplicativo nunca modifica diretamente os arquivos de mídia no ZIP original.
* **Escrita Local Instantânea:** Qualquer registro de conferência é gravado no diretório `%APPDATA%` local imediatamente.
* **Sincronização Atômica:** O processo de sincronização faz a união bidirecional (merge) e reescreve o ZIP de forma segura com criação prévia de backup.

---

## 2. Especificação dos Módulos Core

### 2.1 Criptografia e Manipulação de ZIP (`crypto.py`)

Garante a manipulação segura do arquivo compactado e extração para o cache local.

#### Funções Chave
* `extrair_zip_seguro(zip_path: Path, senha: str, destino_cache: Path) -> bool`
  * Extrai o conteúdo para `%APPDATA%\ValidadorEmbalagens\cache\`.
  * Utilitário cria pasta temporária com GUID único e move atomicamente após a extração com sucesso.
* `hash_arquivo(path: Path) -> str`
  * Gera a assinatura SHA-256 do arquivo ZIP para detectar modificações no servidor de rede.
* `criar_zip_com_checklists(zip_path: Path, senha: str, cache_dir: Path, checklists_dict: dict) -> bool`
  * Atualiza o ZIP com a fusão dos arquivos `checklist.json`.
  * Cria um backup no formato `.backup_YYYYMMDD_HHMMSS.zip` antes da reescrita.
  * Testa o ZIP resultante (`testzip()`) antes de substituir o original via `os.replace()`.
  * Mantém até no máximo os últimos 5 backups históricos.
* `validar_estrutura_zip(zip_path: Path, senha: str) -> List[str]`
  * Retorna inconsistências e arquivos faltantes na estrutura das pastas.

---

### 2.2 Conversor de Documentos e Mídia (`parser.py`)

Transforma arquivos de especificação em formatos legíveis nativamente pela interface.

#### Funções Chave
* `docx_para_html(docx_path: Path) -> str`
  * Utiliza `mammoth.convert_to_html()` para converter o DOCX em HTML semântico.
  * Injeta CSS embutido customizado para formatar títulos (`h1`, `h2`, `h3`), listas, negritos e tabelas (`<table>`, `<thead>`, `<tbody>`).
  * Remove dependências de estilos externos de cabeçalho, rodapé e paginação.
* `extrair_texto_pdf(pdf_path: Path, max_chars: int = 500) -> str`
  * Utiliza `pdfium` para extração rápida de preview de texto da primeira página do PDF.

---

### 2.3 Motor de Sincronização (`sync.py`)

Algoritmo determinístico para fusão de histórico de conferências entre usuários.

#### Lógica do Processo (`sincronizar`)
1. Obtém o SHA-256 do arquivo ZIP no servidor.
2. Extrai temporariamente os arquivos `checklist.json` contidos no ZIP.
3. Carrega os checklists armazenados localmente no diretório da aplicação.
4. Executa o **Merge por Item (`item_id`)**:
   * Combina os históricos locais e do ZIP.
   * Aplica desduplicação rigorosa pela chave primária composta: `(data, conferente)`.
   * Preserva a ordem cronológica ascendente por data.
5. Reescreve o ZIP remoto atualizando os JSONs consolidados de cada item.
6. Atualiza o diretório local de checklists com a versão consolidada.
7. Atualiza o estado em `sync_state.json`.

#### Regras de Conflito e Consistência
* **Mesmo `(data, conferente)`:** Deduplica, mantendo uma única entrada.
* **Registros distintos:** Todos são preservados (modelo de histórico *append-only*).
* **Item removido do ZIP:** O histórico local é retido preventivamente para evitar perda de dados.
* **Novo SKU adicionado:** Cria estrutura local e inclui o histórico vazio na consolidação.
* **Alteração de especificações (PDF/DOCX):** O comando "Recarregar" baixa as mídias atualizadas sem impactar a base de checklists.

---

## 3. Segurança e Resiliência

### 3.1 Práticas de Segurança
* **Tratamento de Senhas:** A senha não é mantida em texto puro em memória persistente. A chave derivada utiliza PBKDF2.
* **Diretórios Temporários:** Limpeza garantida de temporários via manipuladores `atexit` e blocos `try...finally`.
* **Auditoria de Execução:** Logs mantidos em `%APPDATA%\ValidadorEmbalagens\logs\app_YYYYMMDD.log` com múltiplos níveis de criticidade (`INFO`, `WARNING`, `ERROR`).

### 3.2 Tratamento de Exceções e Edge Cases

| Erro / Resiliência | Ação do Sistema |
| :--- | :--- |
| **Senha incorreta** | Exibe diálogo de aviso e permite re-tentativa sem crashar o sistema. |
| **ZIP Corrompido** | Informa arquivo corrompido e possibilita restauração do backup atômico recente. |
| **Caminho de Rede Inacessível** | Alterna para modo *offline*, permitindo leitura local e retenção de auditoria. |
| **Sincronização Concorrente** | Execução determinística por timestamp garante coerência caso 2 usuários sincronizem simultaneamente. |
| **Falha no Renderizador de PDF** | Fallback com botão direto para "Abrir no visualizador nativo do Windows". |