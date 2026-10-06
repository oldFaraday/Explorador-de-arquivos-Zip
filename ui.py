"""Interface PySide6: Janela principal, widgets e sinais."""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTreeView, QLineEdit,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolBar,
    QStatusBar, QMessageBox, QDialog, QComboBox, QTextEdit,
    QProgressDialog, QFileDialog, QMenu, QAbstractItemView,
    QStyle, QHeaderView, QApplication
)
from PySide6.QtCore import (
    Qt, QModelIndex, QSortFilterProxyModel, QStandardPaths,
    QTimer, Signal, QObject, QThread, QSize, QRect
)
from PySide6.QtGui import (
    QStandardItemModel, QStandardItem, QIcon, QAction,
    QFont, QColor, QPixmap, QImage, QPainter, QDesktopServices
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

import pypdfium2 as pdfium
from state import app_state, APPDATA_DIR, CHECKLISTS_DIR
from models import Item, ChecklistEntry
from sync import sincronizar_checklists, get_status_sync, verificar_fora_de_sync
from crypto import extrair_zip_seguro, hash_arquivo
from parser import docx_para_html, get_pdf_page_count, renderizar_pagina_pdf

logger = logging.getLogger(__name__)

VERSAO_APP = "1.0.0"


# =============================================================================
# Worker Threads para operações longas
# =============================================================================

class RecarregarWorker(QObject):
    """Worker para recarregar ZIP em background."""
    finished = Signal(bool, str)
    progress = Signal(int, str)
    
    def __init__(self, zip_path: Path, senha: str):
        super().__init__()
        self.zip_path = zip_path
        self.senha = senha
    
    def run(self):
        try:
            self.progress.emit(10, "Validando ZIP...")
            from crypto import validar_estrutura_zip
            erros = validar_estrutura_zip(self.zip_path, self.senha)
            if erros:
                logger.warning(f"Estrutura ZIP com avisos: {len(erros)} itens")
            
            self.progress.emit(40, "Extraindo para cache...")
            if not extrair_zip_seguro(self.zip_path, self.senha, APPDATA_DIR / "cache"):
                self.finished.emit(False, "Falha na extração. Verifique a senha.")
                return
            
            self.progress.emit(70, "Reconstruindo árvore...")
            from parser import construir_arvore_itens
            checklists_locais = app_state.carregar_checklists_locais()
            itens = construir_arvore_itens(APPDATA_DIR / "cache", checklists_locais)
            app_state.definir_itens(itens)
            
            self.progress.emit(100, "Concluído!")
            self.finished.emit(True, f"{len(itens)} itens carregados")
        except ValueError as e:
            if "senha" in str(e).lower():
                self.finished.emit(False, "Senha incorreta para o ZIP.")
            else:
                self.finished.emit(False, str(e))
        except Exception as e:
            logger.error(f"Erro no recarregar: {e}")
            self.finished.emit(False, f"Erro: {e}")


class SyncWorker(QObject):
    """Worker para sincronização em background."""
    finished = Signal(object)  # SyncResult
    progress = Signal(int, str)
    
    def run(self):
        def cb(pct, msg):
            self.progress.emit(pct, msg)
        
        result = sincronizar_checklists(cb)
        self.finished.emit(result)


# =============================================================================
# Visualizador PDF Customizado
# =============================================================================

class PDFViewer(QWidget):
    """Visualizador de PDF com zoom, navegação e pan."""
    
    page_changed = Signal(int, int)  # current, total
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        
        self._pdf_path: Optional[Path] = None
        self._pdf_doc = None
        self._current_page = 0
        self._total_pages = 0
        self._scale = 1.0
        self._rotation = 0
        self._page_image: Optional[QImage] = None
        
        # Pan
        self._panning = False
        self._pan_start = None
        self._offset = QPoint(0, 0)
        
        # Cores
        self.setStyleSheet("background-color: #2D2D2D;")
    
    def carregar_pdf(self, pdf_path: Path) -> bool:
        """Carrega um arquivo PDF."""
        self._pdf_path = pdf_path
        self._current_page = 0
        self._offset = QPoint(0, 0)
        
        try:
            if self._pdf_doc:
                self._pdf_doc.close()
            self._pdf_doc = pdfium.PdfDocument(str(pdf_path))
            self._total_pages = len(self._pdf_doc)
            self._renderizar_pagina_atual()
            # Ajustar à largura após carregar para garantir que caiba no widget
            QTimer.singleShot(0, self.ajustar_largura)
            self.page_changed.emit(self._current_page + 1, self._total_pages)
            return True
        except Exception as e:
            logger.error(f"Erro ao carregar PDF {pdf_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._total_pages = 0
            self._page_image = None
            self.update()
            return False
    
    def _renderizar_pagina_atual(self):
        if not self._pdf_doc or self._current_page >= self._total_pages:
            return
        
        try:
            page = self._pdf_doc[self._current_page]
            
            # Calcular escala para ajustar à largura se necessário
            if self._scale <= 0:
                self._scale = 1.0
            
            bitmap = page.render(
                scale=self._scale,
                rotation=self._rotation
            )
            pil_image = bitmap.to_pil()
            
            # Debug: log widget size and image size
            logger.debug(f"PDFViewer: widget size={self.width()}x{self.height()}, "
                        f"page size={page.get_width():.0f}x{page.get_height():.0f}, "
                        f"scale={self._scale}, rendered image={pil_image.size}")
            
            # Converter para QImage
            from io import BytesIO
            buffer = BytesIO()
            pil_image.save(buffer, format="PNG")
            buffer.seek(0)
            
            self._page_image = QImage()
            self._page_image.loadFromData(buffer.getvalue())
            
            logger.debug(f"PDFViewer: QImage loaded, size={self._page_image.width()}x{self._page_image.height()}")
            
            self.update()
        except Exception as e:
            logger.error(f"Erro ao renderizar página: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._page_image = None
            self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#2D2D2D"))
        
        if self._page_image and not self._page_image.isNull():
            # Centralizar com offset de pan
            x = (self.width() - self._page_image.width()) // 2 + self._offset.x()
            y = (self.height() - self._page_image.height()) // 2 + self._offset.y()
            painter.drawImage(x, y, self._page_image)
        else:
            # Placeholder
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 
                           "Nenhum PDF carregado\nClique em 'Recarregar' ou selecione um item")
    
    # --- Controles de navegação ---
    def pagina_anterior(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._offset = QPoint(0, 0)
            self._renderizar_pagina_atual()
            self.page_changed.emit(self._current_page + 1, self._total_pages)
    
    def proxima_pagina(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._offset = QPoint(0, 0)
            self._renderizar_pagina_atual()
            self.page_changed.emit(self._current_page + 1, self._total_pages)
    
    def ir_para_pagina(self, pagina: int):  # 1-based
        if 1 <= pagina <= self._total_pages:
            self._current_page = pagina - 1
            self._offset = QPoint(0, 0)
            self._renderizar_pagina_atual()
            self.page_changed.emit(self._current_page + 1, self._total_pages)
    
    def set_zoom(self, scale: float):
        self._scale = max(0.1, min(5.0, scale))
        self._renderizar_pagina_atual()
    
    def zoom_in(self):
        self.set_zoom(self._scale * 1.2)
    
    def zoom_out(self):
        self.set_zoom(self._scale / 1.2)
    
    def reset_zoom(self):
        self.set_zoom(1.0)
    
    def ajustar_largura(self):
        if not self._pdf_doc or not self._page_image:
            return
        page = self._pdf_doc[self._current_page]
        page_width = page.get_width()
        scale = (self.width() - 40) / page_width
        self.set_zoom(scale)
    
    def ajustar_pagina(self):
        if not self._pdf_doc or not self._page_image:
            return
        page = self._pdf_doc[self._current_page]
        page_width = page.get_width()
        page_height = page.get_height()
        scale_w = (self.width() - 40) / page_width
        scale_h = (self.height() - 40) / page_height
        self.set_zoom(min(scale_w, scale_h))
    
    def rotacionar(self):
        self._rotation = (self._rotation + 90) % 360
        self._renderizar_pagina_atual()
    
    def abrir_nativo(self):
        if self._pdf_path and self._pdf_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._pdf_path)))
    
    # --- Eventos de mouse para Pan ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
    
    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start:
            delta = event.position().toPoint() - self._pan_start
            self._offset += delta
            self._pan_start = event.position().toPoint()
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def wheelEvent(self, event):
        # Ctrl+Wheel = Zoom, Wheel = Pan vertical
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            # Scroll vertical normal
            self._offset.setY(self._offset.y() + event.angleDelta().y() // 2)
            self.update()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.pagina_anterior()
        elif event.key() == Qt.Key.Key_Right:
            self.proxima_pagina()
        elif event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
            self.zoom_in()
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_out()
        elif event.key() == Qt.Key.Key_0:
            self.reset_zoom()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Re-render PDF when widget is resized to maintain proper scale."""
        super().resizeEvent(event)
        if self._pdf_doc and self._page_image and not self._page_image.isNull():
            # Re-render at current scale (or re-apply fit-to-width if needed)
            self._renderizar_pagina_atual()


# =============================================================================
# Diálogos
# =============================================================================

class ConferirDialog(QDialog):
    """Diálogo para registrar conferência."""
    
    def __init__(self, item: Item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(f"Registrar Conferência - {item.nome}")
        self.setModal(True)
        self.setFixedSize(450, 350)
        
        layout = QVBoxLayout(self)
        
        # Conferente
        layout.addWidget(QLabel("Conferente:"))
        self.conferente_input = QComboBox()
        self.conferente_input.setEditable(True)
        self.conferente_input.setPlaceholderText("Seu nome")
        # Carregar últimos conferentes
        self._carregar_conferentes_recentes()
        layout.addWidget(self.conferente_input)
        
        # Status
        layout.addWidget(QLabel("Status:"))
        self.status_combo = QComboBox()
        self.status_combo.addItems(["OK", "NOK", "PENDENTE"])
        layout.addWidget(self.status_combo)
        
        # Observação
        layout.addWidget(QLabel("Observação (opcional):"))
        self.obs_input = QTextEdit()
        self.obs_input.setMaximumHeight(100)
        self.obs_input.setPlaceholderText("Observações sobre a conferência...")
        layout.addWidget(self.obs_input)
        
        # Botões
        botoes = QHBoxLayout()
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_salvar = QPushButton("Salvar Local")
        self.btn_salvar.clicked.connect(self._salvar_local)
        self.btn_salvar_sync = QPushButton("Salvar e Sincronizar Agora")
        self.btn_salvar_sync.clicked.connect(self._salvar_e_sincronizar)
        botoes.addWidget(self.btn_cancelar)
        botoes.addWidget(self.btn_salvar)
        botoes.addWidget(self.btn_salvar_sync)
        layout.addLayout(botoes)
    
    def _carregar_conferentes_recentes(self):
        """Carrega nomes de conferentes recentes dos checklists locais."""
        nomes = set()
        for checklist in app_state.carregar_checklists_locais().values():
            for entry in checklist.historico:
                nomes.add(entry.conferente)
        self.conferente_input.addItems(sorted(nomes))
    
    def _salvar_local(self):
        conferente = self.conferente_input.currentText().strip()
        if not conferente:
            QMessageBox.warning(self, "Aviso", "Informe o nome do conferente.")
            return
        
        entry = ChecklistEntry.create(conferente, self.status_combo.currentText(), self.obs_input.toPlainText())
        self.item.checklist.adicionar_entrada(entry)
        app_state.salvar_checklist_local(self.item.checklist)
        
        QMessageBox.information(self, "Sucesso", "Conferência registrada localmente.")
        self.accept()
    
    def _salvar_e_sincronizar(self):
        self._salvar_local()
        # Sinalizar para sincronizar
        self.done(2)  # Código customizado


class SyncDialog(QDialog):
    """Diálogo de sincronização com progresso."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sincronizando Checklists")
        self.setModal(True)
        self.setFixedSize(500, 400)
        
        layout = QVBoxLayout(self)
        
        self.progress_bar = QProgressDialog("Iniciando...", "Cancelar", 0, 100, self)
        self.progress_bar.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_bar.setAutoClose(False)
        self.progress_bar.setAutoReset(False)
        self.progress_bar.canceled.connect(self._cancelar)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        self.btn_fechar = QPushButton("Fechar")
        self.btn_fechar.clicked.connect(self.accept)
        self.btn_fechar.setEnabled(False)
        layout.addWidget(self.btn_fechar)
        
        self._worker = None
        self._thread = None
    
    def iniciar_sync(self):
        self.log_text.clear()
        self._log("Iniciando sincronização...")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.btn_fechar.setEnabled(False)
        
        self._thread = QThread()
        self._worker = SyncWorker()
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()
    
    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_bar.setLabelText(msg)
        self._log(msg)
    
    def _on_finished(self, result):
        self.progress_bar.setValue(100)
        self.progress_bar.hide()
        self.btn_fechar.setEnabled(True)
        
        if result.sucesso:
            self._log("✓ Sincronização concluída com sucesso!")
            self._log(result.resumo())
        else:
            self._log("✗ Falha na sincronização")
            for err in result.erros:
                self._log(f"  ERRO: {err}")
        
        self._thread.quit()
        self._thread.wait()
    
    def _cancelar(self):
        if self._thread and self._thread.isRunning():
            self._thread.terminate()
            self._thread.wait()
        self._log("Operação cancelada pelo usuário")
        self.btn_fechar.setEnabled(True)
    
    def _log(self, msg: str):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())


class ConfigDialog(QDialog):
    """Diálogo de configurações."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.setModal(True)
        self.setFixedSize(550, 350)
        
        layout = QVBoxLayout(self)
        
        # Aba Geral
        layout.addWidget(QLabel("<b>Caminho do ZIP na rede:</b>"))
        h_zip = QHBoxLayout()
        self.zip_path_input = QLineEdit()
        self.zip_path_input.setText(str(app_state.zip_path) if app_state.zip_path else "")
        self.zip_path_input.setPlaceholderText(r"\\Servidor\Share\Validador\Embalagens.zip")
        self.btn_browse = QPushButton("Procurar...")
        self.btn_browse.clicked.connect(self._browse_zip)
        h_zip.addWidget(self.zip_path_input)
        h_zip.addWidget(self.btn_browse)
        layout.addLayout(h_zip)
        
        layout.addWidget(QLabel("<b>Senha do ZIP (AES-256):</b>"))
        h_senha = QHBoxLayout()
        self.senha_input = QLineEdit()
        self.senha_input.setText(app_state.zip_senha)
        self.senha_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_mostrar = QPushButton("Mostrar")
        self.btn_mostrar.setCheckable(True)
        self.btn_mostrar.toggled.connect(lambda c: self.senha_input.setEchoMode(
            QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        h_senha.addWidget(self.senha_input)
        h_senha.addWidget(self.btn_mostrar)
        layout.addLayout(h_senha)
        
        self.auto_recarregar = QCheckBox("Recarregar automaticamente ao iniciar")
        self.auto_recarregar.setChecked(app_state.auto_recarregar)
        layout.addWidget(self.auto_recarregar)
        
        layout.addWidget(QLabel(""))  # espaçador
        
        # Aba Avançado (simplificada)
        layout.addWidget(QLabel("<b>Diretórios locais:</b>"))
        self.lbl_cache = QLabel(f"Cache: {APPDATA_DIR / 'cache'}")
        self.lbl_checklists = QLabel(f"Checklists: {CHECKLISTS_DIR}")
        self.lbl_logs = QLabel(f"Logs: {APPDATA_DIR / 'logs'}")
        for lbl in [self.lbl_cache, self.lbl_checklists, self.lbl_logs]:
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(lbl)
        
        self.btn_limpar_cache = QPushButton("Limpar Cache e Temporários")
        self.btn_limpar_cache.clicked.connect(self._limpar_cache)
        layout.addWidget(self.btn_limpar_cache)
        
        # Botões
        botoes = QHBoxLayout()
        self.btn_ok = QPushButton("Salvar")
        self.btn_ok.clicked.connect(self._salvar)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        botoes.addStretch()
        botoes.addWidget(self.btn_ok)
        botoes.addWidget(self.btn_cancelar)
        layout.addLayout(botoes)
    
    def _browse_zip(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Embalagens.zip", "", "ZIP Files (*.zip)")
        if path:
            self.zip_path_input.setText(path)
    
    def _limpar_cache(self):
        resp = QMessageBox.question(
            self, "Confirmar",
            "Isso removerá todos os arquivos extraídos do cache local.\n"
            "Eles serão rebaixados no próximo 'Recarregar'.\n\nContinuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            import shutil
            cache_dir = APPDATA_DIR / "cache"
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            cache_dir.mkdir(parents=True)
            self._log("Cache limpo.")
    
    def _salvar(self):
        zip_path = Path(self.zip_path_input.text().strip()) if self.zip_path_input.text().strip() else None
        senha = self.senha_input.text()
        
        if not zip_path or not senha:
            QMessageBox.warning(self, "Aviso", "Preencha caminho e senha do ZIP.")
            return
        
        app_state.zip_path = zip_path
        app_state.zip_senha = senha
        app_state.auto_recarregar = self.auto_recarregar.isChecked()
        
        QMessageBox.information(self, "Salvo", "Configurações salvas. Clique em 'Recarregar' para aplicar.")
        self.accept()
    
    def _log(self, msg: str):
        pass


class SobreDialog(QDialog):
    """Diálogo Sobre."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sobre Validador de Embalagens")
        self.setModal(True)
        self.setFixedSize(400, 250)
        
        layout = QVBoxLayout(self)
        layout.addStretch()
        
        layout.addWidget(QLabel("<h2>Explorador de Arquivos Zip</h2>"))
        layout.addWidget(QLabel(f"Versão {VERSAO_APP}"))
        layout.addWidget(QLabel(""))
        layout.addWidget(QLabel("Aplicação para navegação, visualização e validação\nde arquivos em pacotes ZIP criptografados."))
        layout.addWidget(QLabel(""))
        layout.addWidget(QLabel("Desenvolvido para Especificações Técnicas / Inspeção de Recebimento"))
        layout.addStretch()
        
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)


# =============================================================================
# Modelo da Árvore com Filtro
# =============================================================================

class TreeProxyModel(QSortFilterProxyModel):
    """Proxy model para filtrar a árvore em tempo real."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)  # Filtrar em todas as colunas
        self.setRecursiveFilteringEnabled(True)
    
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        # Sempre aceitar categorias (raiz)
        if not source_parent.isValid():
            return True
        # Para filhos, usar filtro padrão
        return super().filterAcceptsRow(source_row, source_parent)


# =============================================================================
# Janela Principal
# =============================================================================

class MainWindow(QMainWindow):
    """Janela principal da aplicação."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Explorador de Arquivos Zip v{VERSAO_APP}")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 700)
        
        self._build_ui()
        self._popular_arvore()
        self._atualizar_status_sync()
        
        # Timer para verificar status de sync periodicamente
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._atualizar_status_sync)
        self._sync_timer.start(30000)  # 30 segundos
    
    def _build_ui(self):
        # Toolbar principal
        toolbar = QToolBar("Principal")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        
        style = self.style()
        
        # Ações da toolbar
        self.act_recarregar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Recarregar", self)
        self.act_recarregar.setToolTip("Recarregar especificações do ZIP de rede (F5)")
        self.act_recarregar.setShortcut("F5")
        self.act_recarregar.triggered.connect(self._on_recarregar)
        toolbar.addAction(self.act_recarregar)
        
        self.act_sincronizar = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "Sincronizar", self)
        self.act_sincronizar.setToolTip("Sincronizar checklists com o ZIP de rede (Ctrl+S)")
        self.act_sincronizar.setShortcut("Ctrl+S")
        self.act_sincronizar.triggered.connect(self._on_sincronizar)
        toolbar.addAction(self.act_sincronizar)
        
        toolbar.addSeparator()
        
        self.act_config = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Configurações", self)
        self.act_config.triggered.connect(self._on_config)
        toolbar.addAction(self.act_config)
        
        self.act_sobre = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation), "Sobre", self)
        self.act_sobre.triggered.connect(self._on_sobre)
        toolbar.addAction(self.act_sobre)
        
        toolbar.addSeparator()
        
        self.act_sair = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton), "Sair", self)
        self.act_sair.setShortcut("Ctrl+Q")
        self.act_sair.triggered.connect(self.close)
        toolbar.addAction(self.act_sair)
        
        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)
        
        # --- Painel Esquerdo ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        
        # Busca
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Buscar SKU...")
        self.search_input.textChanged.connect(self._filtrar_arvore)
        left_layout.addWidget(self.search_input)
        
        # Árvore
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["Produtos"])
        
        self.proxy_model = TreeProxyModel()
        self.proxy_model.setSourceModel(self.tree_model)
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.proxy_model)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setExpandsOnDoubleClick(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(16)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.tree_view.selectionModel().selectionChanged.connect(self._on_selecao_mudou)
        
        left_layout.addWidget(self.tree_view)
        
        splitter.addWidget(left_widget)
        
        # --- Painel Direito ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(4)
        
        # Splitter vertical (Descrição Técnica / PDF)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_layout.addWidget(right_splitter)
        
        # Topo: Descrição Técnica (HTML)
        self.web_view = QWebEngineView()
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self.web_view.setMinimumHeight(300)
        
        # Toolbar HTML
        html_toolbar = QToolBar()
        html_toolbar.setIconSize(QSize(20, 20))
        html_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        
        # Usar ícones padrão do Qt (SP_*) que funcionam em todas as plataformas
        style = self.style()
        self.act_zoom_in = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Zoom +", self)
        self.act_zoom_in.triggered.connect(lambda: self._web_zoom(1.2))
        self.act_zoom_out = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView), "Zoom -", self)
        self.act_zoom_out.triggered.connect(lambda: self._web_zoom(1/1.2))
        self.act_zoom_reset = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Reset", self)
        self.act_zoom_reset.triggered.connect(lambda: self._web_zoom(1.0, True))
        self.act_print = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "Imprimir", self)
        self.act_print.triggered.connect(self._imprimir_html)
        for act in [self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset, self.act_print]:
            html_toolbar.addAction(act)
        
        html_container = QWidget()
        html_layout = QVBoxLayout(html_container)
        html_layout.setContentsMargins(0, 0, 0, 0)
        html_layout.setSpacing(2)
        html_layout.addWidget(html_toolbar)
        html_layout.addWidget(self.web_view)
        
        right_splitter.addWidget(html_container)
        
        # Base: Conferência Visual (PDF)
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.page_changed.connect(self._on_pdf_page_changed)
        
        # Toolbar PDF
        pdf_toolbar = QToolBar()
        pdf_toolbar.setIconSize(QSize(20, 20))
        pdf_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        
        style = self.style()
        self.act_pdf_prev = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowLeft), "Anterior", self)
        self.act_pdf_prev.triggered.connect(self.pdf_viewer.pagina_anterior)
        self.act_pdf_next = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight), "Próxima", self)
        self.act_pdf_next.triggered.connect(self.pdf_viewer.proxima_pagina)
        
        self.lbl_pagina = QLabel("Pág 0 de 0")
        self.lbl_pagina.setMinimumWidth(80)
        
        self.act_pdf_zoom_in = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Zoom +", self)
        self.act_pdf_zoom_in.triggered.connect(self.pdf_viewer.zoom_in)
        self.act_pdf_zoom_out = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView), "Zoom -", self)
        self.act_pdf_zoom_out.triggered.connect(self.pdf_viewer.zoom_out)
        
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "Ajustar Largura", "Ajustar Página"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo)
        
        self.act_pdf_rotate = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Rotacionar 90°", self)
        self.act_pdf_rotate.triggered.connect(self.pdf_viewer.rotacionar)
        
        self.act_pdf_native = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Abrir no Visualizador", self)
        self.act_pdf_native.triggered.connect(self.pdf_viewer.abrir_nativo)
        
        for w in [self.act_pdf_prev, self.lbl_pagina, self.act_pdf_next, 
                  self.act_pdf_zoom_out, self.zoom_combo, self.act_pdf_zoom_in,
                  self.act_pdf_rotate, self.act_pdf_native]:
            if isinstance(w, QAction):
                pdf_toolbar.addAction(w)
            else:
                pdf_toolbar.addWidget(w)
        
        pdf_container = QWidget()
        pdf_layout = QVBoxLayout(pdf_container)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        pdf_layout.setSpacing(2)
        pdf_layout.addWidget(pdf_toolbar)
        pdf_layout.addWidget(self.pdf_viewer)
        
        right_splitter.addWidget(pdf_container)
        
        # Proporção 60/40
        right_splitter.setStretchFactor(0, 60)
        right_splitter.setStretchFactor(1, 40)
        
        # Botão Conferir
        self.btn_conferir = QPushButton("📝 Registrar Conferência")
        self.btn_conferir.setMinimumHeight(40)
        self.btn_conferir.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_conferir.clicked.connect(self._on_conferir)
        self.btn_conferir.setEnabled(False)
        right_layout.addWidget(self.btn_conferir)
        
        splitter.addWidget(right_widget)
        
        # Proporção 25/75
        splitter.setStretchFactor(0, 25)
        splitter.setStretchFactor(1, 75)
        
        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.lbl_status_item = QLabel("Nenhum item selecionado")
        self.lbl_status_ultima = QLabel("")
        self.lbl_status_sync = QLabel("☁ Verificando...")
        
        self.status_bar.addWidget(self.lbl_status_item, 1)
        self.status_bar.addPermanentWidget(self.lbl_status_ultima, 1)
        self.status_bar.addPermanentWidget(self.lbl_status_sync, 0)
    
    def _popular_arvore(self):
        """Popula a árvore dinamicamente baseada na hierarquia dos itens (marca/linha/categoria)."""
        self.tree_model.clear()
        self.tree_model.setHorizontalHeaderLabels(["Produtos"])
        
        # Agrupa itens por hierarquia disponível
        # Estrutura: marca → linha → categoria → item
        # Se não houver marca/linha, usa categoria como raiz (compatibilidade legada)
        raizes = {}  # chave composta -> QStandardItem
        
        for item in sorted(app_state.itens.values(), key=lambda i: (i.marca or 'zzz', i.linha or 'zzz', i.categoria or 'zzz', i.nome)):
            if item.marca:
                # Estrutura hierárquica completa: Marca → Linha → Categoria → Item
                marca_key = f"marca:{item.marca}"
                if marca_key not in raizes:
                    marca_node = QStandardItem(f"🏷️  {item.marca}")
                    marca_node.setFont(QFont("", 11, QFont.Weight.Bold))
                    marca_node.setForeground(QColor("#0056A0"))
                    marca_node.setEditable(False)
                    marca_node.setData({'tipo': 'marca', 'valor': item.marca}, Qt.ItemDataRole.UserRole)
                    self.tree_model.appendRow(marca_node)
                    raizes[marca_key] = marca_node
                else:
                    marca_node = raizes[marca_key]
                
                linha_key = f"{marca_key}:linha:{item.linha}"
                if linha_key not in raizes:
                    linha_node = QStandardItem(f"📂  {item.linha}")
                    linha_node.setFont(QFont("", 10, QFont.Weight.DemiBold))
                    linha_node.setEditable(False)
                    linha_node.setData({'tipo': 'linha', 'valor': item.linha}, Qt.ItemDataRole.UserRole)
                    marca_node.appendRow(linha_node)
                    raizes[linha_key] = linha_node
                else:
                    linha_node = raizes[linha_key]
                
                cat_key = f"{linha_key}:categoria:{item.categoria}"
                if cat_key not in raizes:
                    cat_node = QStandardItem(f"📁  {item.categoria}")
                    cat_node.setFont(QFont("", 10))
                    cat_node.setEditable(False)
                    cat_node.setData({'tipo': 'categoria', 'valor': item.categoria}, Qt.ItemDataRole.UserRole)
                    linha_node.appendRow(cat_node)
                    raizes[cat_key] = cat_node
                else:
                    cat_node = raizes[cat_key]
                
                parent = cat_node
            else:
                # Estrutura plana (legado): Categoria → Item
                cat_key = f"categoria:{item.categoria or 'Geral'}"
                if cat_key not in raizes:
                    cat_node = QStandardItem(f"📁  {item.categoria or 'Geral'}")
                    cat_node.setFont(QFont("", 11, QFont.Weight.Bold))
                    cat_node.setForeground(QColor("#0056A0"))
                    cat_node.setEditable(False)
                    cat_node.setData({'tipo': 'categoria', 'valor': item.categoria or 'Geral'}, Qt.ItemDataRole.UserRole)
                    self.tree_model.appendRow(cat_node)
                    raizes[cat_key] = cat_node
                else:
                    cat_node = raizes[cat_key]
                parent = cat_node
            
            # Item folha
            item_node = QStandardItem(f"📦  {item.nome}")
            item_node.setEditable(False)
            item_node.setData({'tipo': 'item', 'item_id': item.id}, Qt.ItemDataRole.UserRole)
            item_node.setToolTip(f"ID: {item.id}\nCaminho: {item.pasta_zip}")
            parent.appendRow(item_node)
        
        # Expandir tudo
        self.tree_view.expandAll()
    
    def _filtrar_arvore(self, texto: str):
        self.proxy_model.setFilterFixedString(texto)
        if texto:
            self.tree_view.expandAll()
        else:
            self.tree_view.collapseAll()
    
    def _on_selecao_mudou(self):
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if not indexes:
            self._limpar_painel_direito()
            return
        
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        item = self.tree_model.itemFromIndex(source_index)
        
        if not item or item.parent() is None:
            # É uma categoria/marca/linha
            self._limpar_painel_direito()
            return
        
        user_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(user_data, dict) and user_data.get('tipo') == 'item':
            item_id = user_data.get('item_id')
            if item_id:
                self._carregar_item(item_id)
            else:
                self._limpar_painel_direito()
        else:
            self._limpar_painel_direito()
    
    def _carregar_item(self, item_id: str):
        item = app_state.get_item(item_id)
        if not item:
            return
        
        app_state.item_atual_id = item_id
        self.btn_conferir.setEnabled(True)
        
        # Descrição Técnica (HTML)
        html = docx_para_html(item.docx_path)
        self.web_view.setHtml(html)
        self._web_zoom_factor = 1.0
        
        # PDF - usa o nome real do PDF detectado
        self.pdf_viewer.carregar_pdf(item.pdf_path)
        
        # Status bar - mostra hierarquia completa se disponível
        partes_status = [f"Item: {item.nome}"]
        if item.marca:
            partes_status.append(f"Marca: {item.marca}")
        if item.linha:
            partes_status.append(f"Linha: {item.linha}")
        if item.categoria:
            partes_status.append(f"Categoria: {item.categoria}")
        self.lbl_status_item.setText(" | ".join(partes_status))
        
        ultima = item.checklist.ultima_entrada()
        if ultima:
            from datetime import datetime
            dt = datetime.fromisoformat(ultima.data).strftime("%d/%m/%Y %H:%M")
            self.lbl_status_ultima.setText(f"Última: {ultima.conferente} ({dt} - {ultima.status})")
        else:
            self.lbl_status_ultima.setText("Sem conferências registradas")
    
    def _limpar_painel_direito(self):
        app_state.item_atual_id = None
        self.btn_conferir.setEnabled(False)
        self.web_view.setHtml("<html><body style='color:#888;text-align:center;padding:40px;'>Selecione um item na árvore</body></html>")
        self.pdf_viewer._page_image = None
        self.pdf_viewer._total_pages = 0
        self.pdf_viewer.update()
        self.lbl_pagina.setText("Pág 0 de 0")
        self.lbl_status_item.setText("Nenhum item selecionado")
        self.lbl_status_ultima.setText("")
    
    def _on_pdf_page_changed(self, current: int, total: int):
        self.lbl_pagina.setText(f"Pág {current} de {total}")
    
    def _on_zoom_combo(self, text: str):
        if text.endswith("%"):
            scale = float(text.rstrip("%")) / 100.0
            self.pdf_viewer.set_zoom(scale)
        elif text == "Ajustar Largura":
            self.pdf_viewer.ajustar_largura()
        elif text == "Ajustar Página":
            self.pdf_viewer.ajustar_pagina()
    
    def _web_zoom(self, factor: float, absolute: bool = False):
        if absolute:
            self._web_zoom_factor = factor
        else:
            self._web_zoom_factor *= factor
        self._web_zoom_factor = max(0.5, min(3.0, self._web_zoom_factor))
        self.web_view.setZoomFactor(self._web_zoom_factor)
    
    def _imprimir_html(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.web_view.page().print(printer, lambda success: None)
    
    def _on_conferir(self):
        item = app_state.item_atual
        if not item:
            return
        
        dialog = ConferirDialog(item, self)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            self._carregar_item(item.id)  # Atualizar UI
        elif result == 2:  # Salvar e Sincronizar
            self._on_sincronizar()
    
    def _on_recarregar(self):
        if not app_state.zip_path or not app_state.zip_path.exists():
            QMessageBox.warning(self, "Aviso", "Caminho do ZIP não configurado ou arquivo não encontrado.")
            self._on_config()
            return
        
        self.act_recarregar.setEnabled(False)
        
        self._recarregar_thread = QThread()
        self._recarregar_worker = RecarregarWorker(app_state.zip_path, app_state.zip_senha)
        self._recarregar_worker.moveToThread(self._recarregar_thread)
        self._recarregar_worker.progress.connect(self._on_recarregar_progress)
        self._recarregar_worker.finished.connect(self._on_recarregar_finished)
        self._recarregar_thread.started.connect(self._recarregar_worker.run)
        self._recarregar_thread.start()
    
    def _on_recarregar_progress(self, pct: int, msg: str):
        self.statusBar().showMessage(f"Recarregando: {msg} ({pct}%)")
    
    def _on_recarregar_finished(self, sucesso: str, msg: str):
        self._recarregar_thread.quit()
        self._recarregar_thread.wait()
        self.act_recarregar.setEnabled(True)
        self.statusBar().clearMessage()
        
        if sucesso:
            self._popular_arvore()
            # Manter seleção se possível
            if app_state.item_atual_id:
                self._carregar_item(app_state.item_atual_id)
            QMessageBox.information(self, "Sucesso", msg)
        else:
            QMessageBox.critical(self, "Erro", msg)
    
    def _on_sincronizar(self):
        dialog = SyncDialog(self)
        dialog.iniciar_sync()
        dialog.exec()
        self._atualizar_status_sync()
        # Atualizar UI do item atual
        if app_state.item_atual_id:
            self._carregar_item(app_state.item_atual_id)
    
    def _on_config(self):
        dialog = ConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Recarregar automaticamente se config mudou
            self._on_recarregar()
    
    def _on_sobre(self):
        SobreDialog(self).exec()
    
    def _on_tree_context_menu(self, pos):
        index = self.tree_view.indexAt(pos)
        if not index.isValid():
            return
        
        source_index = self.proxy_model.mapToSource(index)
        item = self.tree_model.itemFromIndex(source_index)
        
        if not item or item.parent() is None:
            return  # É categoria/marca/linha
        
        user_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(user_data, dict) and user_data.get('tipo') == 'item':
            item_id = user_data.get('item_id')
            if not item_id:
                return
            item_obj = app_state.get_item(item_id)
            if not item_obj:
                return
            
            menu = QMenu(self)
            
            act_abrir_cache = menu.addAction("Abrir pasta no cache")
            act_abrir_cache.triggered.connect(lambda: self._abrir_pasta_cache(item_obj))
            
            act_copiar_id = menu.addAction("Copiar ID do item")
            act_copiar_id.triggered.connect(lambda: QApplication.clipboard().setText(item_id))
            
            menu.exec(self.tree_view.viewport().mapToGlobal(pos))
    
    def _abrir_pasta_cache(self, item: Item):
        import subprocess
        pasta = item.pdf_path.parent
        if pasta.exists():
            subprocess.Popen(f'explorer "{pasta}"')
    
    def _atualizar_status_sync(self):
        status = get_status_sync()
        
        if status.get("erro"):
            self.lbl_status_sync.setText(f"⚠ {status['erro']}")
            self.lbl_status_sync.setStyleSheet("color: #c00;")
        elif status["sincronizado"]:
            self.lbl_status_sync.setText("☁ Sincronizado")
            self.lbl_status_sync.setStyleSheet("color: #080;")
        else:
            self.lbl_status_sync.setText("⚠ Fora de Sync")
            self.lbl_status_sync.setStyleSheet("color: #c80;")
    
    def closeEvent(self, event):
        # Limpar recursos
        if self.pdf_viewer._pdf_doc:
            self.pdf_viewer._pdf_doc.close()
        event.accept()


# Import faltante
from PySide6.QtCore import QPoint, QUrl
from PySide6.QtWidgets import QCheckBox