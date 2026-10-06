#!/usr/bin/env python3
"""Explorador de Arquivos Zip - Ponto de entrada principal."""

import sys
import os
import locale
import logging
from pathlib import Path

# Forçar UTF-8 no Windows
if sys.platform == "win32":
    # Python 3.7+: usar UTF-8 mode
    os.environ["PYTHONUTF8"] = "1"
    # Configurar locale para UTF-8
    try:
        locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, "C.UTF-8")
        except locale.Error:
            pass  # Usa padrão do sistema

VERSAO_APP = "1.1.0"

# Configurar logging antes de importar módulos locais
def setup_logging():
    log_dir = Path.home() / "AppData" / "Roaming" / "ExploradorZip" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    from datetime import datetime
    log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# Adicionar diretório do script ao path para imports locais
sys.path.insert(0, str(Path(__file__).parent))

from state import app_state, APPDATA_DIR, migrar_checklists_se_necessario
from ui import MainWindow
from crypto import validar_estrutura_zip, extrair_zip_seguro, hash_arquivo
from sync import sincronizar_checklists
from parser import docx_para_html

from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon


class SenhaDialog(QDialog):
    """Diálogo para solicitar senha do ZIP."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Explorador de Arquivos Zip - Autenticação")
        self.setModal(True)
        self.setFixedSize(400, 180)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Digite a senha do arquivo Itens.zip:"))
        
        self.senha_input = QLineEdit()
        self.senha_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.senha_input.setPlaceholderText("Senha AES-256")
        layout.addWidget(self.senha_input)
        
        self.mostrar_senha = QPushButton("Mostrar")
        self.mostrar_senha.setCheckable(True)
        self.mostrar_senha.toggled.connect(self._toggle_senha)
        layout.addWidget(self.mostrar_senha)
        
        botoes = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        botoes.addWidget(self.btn_ok)
        botoes.addWidget(self.btn_cancelar)
        layout.addLayout(botoes)
        
        self.senha_input.returnPressed.connect(self.accept)
        self.senha_input.setFocus()
    
    def _toggle_senha(self, checked: bool):
        self.senha_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        self.mostrar_senha.setText("Ocultar" if checked else "Mostrar")
    
    def get_senha(self) -> str:
        return self.senha_input.text()


class ConfigDialog(QDialog):
    """Diálogo de configuração inicial."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração Inicial")
        self.setModal(True)
        self.setFixedSize(500, 250)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Configure o caminho do arquivo ZIP na rede:"))
        
        self.zip_path_input = QLineEdit()
        self.zip_path_input.setPlaceholderText(r"\\Servidor\Share\ExploradorZip\Itens.zip")
        layout.addWidget(self.zip_path_input)
        
        layout.addWidget(QLabel("Senha do ZIP (AES-256):"))
        self.senha_input = QLineEdit()
        self.senha_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.senha_input)
        
        botoes = QHBoxLayout()
        self.btn_ok = QPushButton("Salvar e Continuar")
        self.btn_ok.clicked.connect(self._validar_e_aceitar)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        botoes.addWidget(self.btn_ok)
        botoes.addWidget(self.btn_cancelar)
        layout.addLayout(botoes)
    
    def _validar_e_aceitar(self):
        zip_path = self.zip_path_input.text().strip()
        senha = self.senha_input.text()
        
        if not zip_path:
            QMessageBox.warning(self, "Aviso", "Informe o caminho do arquivo ZIP.")
            return
        
        if not senha:
            QMessageBox.warning(self, "Aviso", "Informe a senha do ZIP.")
            return
        
        path = Path(zip_path)
        if not path.exists():
            resp = QMessageBox.question(
                self, "Arquivo não encontrado",
                f"O arquivo não foi encontrado em:\n{zip_path}\n\nDeseja continuar mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        
        app_state.zip_path = path
        app_state.zip_senha = senha
        self.accept()


def inicializar_aplicacao() -> bool:
    """Inicializa a aplicação: diretórios, config, cache."""
    logger.info("=== Iniciando Explorador de Arquivos Zip ===")
    
    # 1. Criar diretórios locais
    app_state.inicializar_diretorios()
    
    # 2. Carregar configuração salva
    config = app_state.carregar_config()
    
    # 3. Se não houver config, solicitar
    if not config.get("zip_path") or not config.get("zip_senha"):
        dialog = ConfigDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            logger.info("Configuração cancelada pelo usuário")
            return False
    
    # 4. Verificar se ZIP existe
    zip_path = app_state.zip_path
    if not zip_path or not zip_path.exists():
        QMessageBox.critical(
            None, "Erro",
            f"Arquivo ZIP não encontrado:\n{zip_path}\n\n"
            "Verifique o caminho nas configurações."
        )
        return False
    
    # 5. Validar estrutura do ZIP
    logger.info(f"Validando estrutura do ZIP: {zip_path}")
    erros = validar_estrutura_zip(zip_path, app_state.zip_senha)
    if erros:
        msg = "Problemas na estrutura do ZIP:\n" + "\n".join(erros[:10])
        if len(erros) > 10:
            msg += f"\n... e mais {len(erros) - 10} erros"
        QMessageBox.warning(None, "Aviso - Estrutura do ZIP", msg)
        # Não bloquear, apenas avisar
    
    # 6. Migrar checklists legados se necessário (após validar ZIP)
    logger.info("Verificando migração de checklists...")
    migrados = migrar_checklists_se_necessario()
    if migrados > 0:
        logger.info(f"{migrados} checklists migrados para nova estrutura de IDs")
    
    # 7. Carregar itens do ZIP (descoberta genérica + checklists locais)
    logger.info("Carregando itens do ZIP...")
    itens = app_state.carregar_itens_do_zip()
    app_state.definir_itens(itens)
    
    if not itens:
        QMessageBox.warning(None, "Aviso", "Nenhum item encontrado no ZIP.")
    
    # 8. Carregar estado de sync
    app_state.carregar_sync_state()
    
    logger.info("Inicialização concluída com sucesso")
    return True


def main():
    """Função principal."""
    app = QApplication(sys.argv)
    app.setApplicationName("Explorador de Arquivos Zip")
    app.setApplicationVersion(VERSAO_APP)
    app.setOrganizationName("ExploradorZip")
    
    # Ícone da aplicação
    icon_path = Path(__file__).parent / "resources" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # Carregar stylesheet
    qss_path = Path(__file__).parent / "resources" / "styles.qss"
    if qss_path.exists():
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    
    # Inicialização assíncrona para não travar a UI
    def on_inicializacao_completa(sucesso: bool):
        if sucesso:
            window = MainWindow()
            window.show()
        else:
            app.quit()
    
    # Usar QTimer para permitir que a UI de configuração apareça
    QTimer.singleShot(100, lambda: on_inicializacao_completa(inicializar_aplicacao()))
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())