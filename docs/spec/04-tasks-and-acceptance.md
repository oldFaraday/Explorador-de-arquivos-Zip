# Spec 04: Plano de Testes, Backlog e Critérios de Aceite

## 1. Estratégia de Testes e Validação

### 1.1 Testes Unitários (`pytest`)
* **Módulo `crypto`:** Teste de extração de ZIPs válidos e inválidos, verificação de hash SHA-256 e gravação atômica com backup.
* **Módulo `parser`:** Garantia de integridade da estrutura HTML na conversão de DOCX com tabelas e listas complexas.
* **Módulo `sync`:** Testar união de listas com itens duplicados, resolução determinística e inclusão de novos registros.
* **Módulo `models`:** Validação da serialização e desserialização JSON.

### 1.2 Cenários de Testes de Integração
1. **Atualização da Engenharia:** Atualizar um PDF no ZIP de rede, acionar "Recarregar" no App e validar se a nova arte foi exibida.
2. **Registro de Auditoria:** Realizar conferências locais, acionar "Sincronizar" e checar a integridade da fusão no ZIP compartilhado.
3. **Sincronização Simultânea:** Executar o processo de Sync em dois computadores com conferências distintas no mesmo instante.
4. **Resiliência a Falhas:** Simular encerramento abrupto do processo no meio de um Sync e verificar a restauração do backup.
5. **Operação Offline:** Desconectar a rede, realizar conferências locais e sincronizar após restabelecimento da conexão.

### 1.3 Metas de Performance
* **Inicialização a Frio:** $< 5$ segundos com ZIP de 50MB.
* **Ação de Recarregar:** $< 3$ segundos.
* **Sincronização:** $< 10$ segundos para 100 checklists.
* **Renderização da Primeira Página do PDF:** $< 500$ milissegundos.

---

## 2. Backlog Ordenado de Desenvolvimento

- [ ] **Task 1: Estrutura Base:** Criar repositório, `main.py`, `models.py`, `state.py` e `requirements.txt`.
- [ ] **Task 2: Módulo Crypto (`crypto.py`):** Desenvolver extrator seguro, manipulador de hash SHA-256 e salvamento atômico com backup.
- [ ] **Task 3: Módulo Parser (`parser.py`):** Implementar conversor DOCX->HTML com Mammoth, inclusão de estilos CSS e leitor PDF.
- [ ] **Task 4: Engine de Sincronização (`sync.py`):** Criar lógica de fusão de JSONs com deduplicação por chave composta.
- [ ] **Task 5: Interface PySide6 (`ui.py`):** Construir Janela Principal, `QTreeView`, visualizador `QWebEngineView` e o visualizador customizado de PDF com PDFium.
- [ ] **Task 6: Diálogos Modais:** Criar telas para Conferência, Sincronização com barra de progresso e Configurações.
- [ ] **Task 7: Estilização:** Aplicar folha de estilo `styles.qss` e ícones da aplicação.
- [ ] **Task 8: Script de Compilação (`build_exe.py`):** Configurar PyInstaller e gerar executável final otimizado.
- [ ] **Task 9: Gerador de Base Inicial (`gerar_zip_inicial.py`):** Criar script de população com os 17 SKUs padrão do MVP.
- [ ] **Task 10: Execução de Testes:** Executar cenários unitários e de integração de 1 a 5.
- [ ] **Task 11: Documentação Operacional:** Redigir `README.md` e guia rápido de uso para o usuário de fábrica.

---

## 3. Critérios de Aceite (Definition of Done)

O MVP será considerado concluído e pronto para homologação quando:

1. Executável *standalone* rodar em máquinas Windows 10/11 sem pré-requisitos de instalação.
2. Solicitar senha na abertura e carregar corretamente a árvore com os 17 SKUs.
3. Exibir com precisão a ficha técnica do Word renderizada em HTML e o PDF na interface gráfica.
4. O botão "Conferir" registrar dados locais no diretório `%APPDATA%`.
5. O botão "Recarregar" atualizar as especificações alteradas pela Engenharia sem corromper mídias.
6. O botão "Sincronizar" realizar o merge bidirecional, criando backups atômicos do ZIP.
7. O estado das conferências for mantido após reiniciar a aplicação.
8. Executável final contido em tamanho $< 60$ MB, com consumo de RAM $< 200$ MB.

---

## 4. Roteiro de Expansão Futura (Pós-MVP)

* Suporte a novas linhas de insumos (Caixas de papelão, Rótulos e Filmes estruturados).
* Captura e anexo de fotos de não-conformidade diretamente na tela de conferência.
* Assinatura digital em tela *touchscreen*.
* Dashboard Web executável para gestão com métricas do recebimento.
* Integração via API com SAP ERP.