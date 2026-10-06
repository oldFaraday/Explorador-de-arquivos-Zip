"""Conversão de documentos e utilitários de mídia."""

import logging
import re
from pathlib import Path
from typing import List, Optional

import mammoth
import pypdfium2 as pdfium

logger = logging.getLogger(__name__)

# CSS customizado para renderização da Descrição Técnica
CUSTOM_CSS = """
<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; line-height: 1.5; color: #1a1a1a; margin: 20px; }
    h1 { color: #0056A0; font-size: 22px; border-bottom: 2px solid #0056A0; padding-bottom: 8px; margin-top: 0; }
    h2 { color: #0056A0; font-size: 18px; margin-top: 24px; margin-bottom: 8px; border-left: 4px solid #0056A0; padding-left: 12px; }
    h3 { color: #333; font-size: 15px; margin-top: 16px; margin-bottom: 6px; }
    h4 { color: #444; font-size: 14px; margin-top: 12px; margin-bottom: 4px; }
    p { margin: 8px 0; }
    ul, ol { margin: 8px 0; padding-left: 24px; }
    li { margin: 4px 0; }
    strong { font-weight: 600; color: #222; }
    table { border-collapse: collapse; width: 100%; max-width: 100%; margin: 12px 0; font-size: 12px; }
    th, td { border: 1px solid #ddd; padding: 8px 10px; text-align: left; vertical-align: top; }
    th { background-color: #0056A0; color: white; font-weight: 600; }
    tr:nth-child(even) td { background-color: #f7f9fc; }
    code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-family: Consolas, monospace; font-size: 12px; }
    hr { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
    .identificacao-item { display: flex; margin: 6px 0; }
    .identificacao-label { font-weight: 600; min-width: 180px; color: #0056A0; }
    .identificacao-value { flex: 1; }
</style>
"""


def docx_para_html(docx_path: Path) -> str:
    """
    Converte DOCX para HTML semântico usando mammoth.
    Injeta CSS customizado para formatação consistente.
    """
    if not docx_path.exists():
        return _html_erro(f"Arquivo não encontrado: {docx_path}")
    
    try:
        # Converter com mammoth
        result = mammoth.convert_to_html(str(docx_path))
        html = result.value
        
        # Log de avisos do mammoth
        for msg in result.messages:
            logger.warning(f"Mammoth: {msg.message}")
        
        # Injetar CSS customizado
        if "<body>" in html:
            html = html.replace("<body>", f"<body>{CUSTOM_CSS}")
        elif "<html>" in html:
            html = html.replace("<html>", f"<html>{CUSTOM_CSS}")
        else:
            html = CUSTOM_CSS + html
        
        # Pós-processamento: melhorar formatação de listas de identificação
        html = _melhorar_formatacao_identificacao(html)
        
        return html
        
    except Exception as e:
        logger.error(f"Erro ao converter DOCX {docx_path}: {e}")
        return _html_erro(f"Erro na conversão: {e}")


def _melhorar_formatacao_identificacao(html: str) -> str:
    """Melhora a renderização da seção de Identificação (label: value)."""
    # Padrão: <p><strong>Label:</strong> Value</p> -> div com classes
    pattern = r'<p><strong>([^:]+:)</strong>\s*([^<]*)</p>'
    
    def replace(match):
        label = match.group(1).strip()
        value = match.group(2).strip()
        return f'<div class="identificacao-item"><span class="identificacao-label">{label}</span><span class="identificacao-value">{value}</span></div>'
    
    return re.sub(pattern, replace, html)


def _html_erro(mensagem: str) -> str:
    """Gera HTML de erro padronizado."""
    return f"""
    <html><head>{CUSTOM_CSS}</head><body>
    <div style="background: #fff3f3; border: 1px solid #ff6b6b; border-radius: 8px; padding: 20px; color: #c00;">
        <h2>⚠ Erro ao Carregar Especificação</h2>
        <p>{mensagem}</p>
        <p><small>Verifique se o arquivo Descricao Tecnica.docx existe e não está corrompido.</small></p>
    </div>
    </body></html>
    """


def extrair_texto_pdf(pdf_path: Path, max_chars: int = 500) -> str:
    """Extrai preview de texto da primeira página do PDF."""
    if not pdf_path.exists():
        return ""
    
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        if len(pdf) > 0:
            page = pdf[0]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            pdf.close()
            return text[:max_chars].strip()
    except Exception as e:
        logger.warning(f"Erro ao extrair texto do PDF {pdf_path}: {e}")
    return ""


def renderizar_pagina_pdf(pdf_path: Path, page_index: int, scale: float = 1.0, rotation: int = 0) -> Optional["QImage"]:
    """
    Renderiza uma página do PDF para QImage usando pdfium.
    Requer import do PySide6 no contexto de uso.
    """
    if not pdf_path.exists():
        return None
    
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        if page_index >= len(pdf):
            pdf.close()
            return None
        
        page = pdf[page_index]
        
        # Aplicar rotação
        if rotation:
            page.set_rotation(rotation)
        
        # Renderizar
        bitmap = page.render(scale=scale, rotation=rotation)
        image = bitmap.to_pil()
        pdf.close()
        
        # Converter PIL para QImage
        from PySide6.QtGui import QImage
        from io import BytesIO
        
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        
        qimage = QImage()
        qimage.loadFromData(buffer.getvalue())
        return qimage
        
    except Exception as e:
        logger.error(f"Erro ao renderizar PDF {pdf_path} página {page_index}: {e}")
        return None


def get_pdf_page_count(pdf_path: Path) -> int:
    """Retorna o número de páginas do PDF."""
    if not pdf_path.exists():
        return 0
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        count = len(pdf)
        pdf.close()
        return count
    except Exception as e:
        logger.error(f"Erro ao ler PDF {pdf_path}: {e}")
        return 0


def construir_arvore_itens(cache_dir: Path, checklists_locais: dict) -> List:
    """
    Constrói a lista de itens a partir da estrutura de pastas no cache.
    Retorna lista de objetos Item.
    """
    from models import Item, Checklist
    
    itens = []
    
    if not cache_dir.exists():
        logger.warning(f"Diretório de cache não existe: {cache_dir}")
        return itens
    
    # Estrutura esperada: cache/Categoria/Item/
    for categoria_dir in sorted(cache_dir.iterdir()):
        if not categoria_dir.is_dir():
            continue
        
        categoria = categoria_dir.name
        
        for item_dir in sorted(categoria_dir.iterdir()):
            if not item_dir.is_dir():
                continue
            
            item_nome = item_dir.name
            
            # Gerar ID slug
            item_id = _gerar_slug(f"{categoria}_{item_nome}")
            
            # Caminhos dos arquivos
            pdf_path = item_dir / "Conferencia Visual.pdf"
            docx_path = item_dir / "Descricao Tecnica.docx"
            
            # Checklist (local ou vazio)
            checklist_data = checklists_locais.get(item_id)
            if checklist_data:
                if isinstance(checklist_data, Checklist):
                    checklist = checklist_data
                else:
                    checklist = Checklist.from_dict(checklist_data)
            else:
                checklist = Checklist(item_id=item_id)
            
            # Nome legível
            nome_legivel = _formatar_nome_legivel(categoria, item_nome)
            
            # Caminho relativo no ZIP
            pasta_zip = f"{categoria}/{item_nome}"
            
            item = Item(
                id=item_id,
                nome=nome_legivel,
                categoria=categoria,
                pasta_zip=pasta_zip,
                pdf_path=pdf_path,
                docx_path=docx_path,
                checklist=checklist
            )
            itens.append(item)
    
    logger.info(f"Árvore construída: {len(itens)} itens")
    return itens


def _gerar_slug(texto: str) -> str:
    """Gera slug único a partir de texto."""
    # Normalizar: minúsculas, remover acentos, substituir espaços/especiais por _
    import unicodedata
    texto = unicodedata.normalize('NFKD', texto)
    texto = texto.encode('ascii', 'ignore').decode('ascii')
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9]+', '_', texto)
    texto = texto.strip('_')
    return texto


def _formatar_nome_legivel(categoria: str, item_nome: str) -> str:
    """Formata nome legível para exibição."""
    # Mapear nomes de pastas para nomes comerciais
    mapa_categoria = {
        "Chips Lisa": "Chips Lisa",
        "Chips Ondulada": "Chips Ondulada",
        "Palha Tradicional": "Palha Tradicional",
        "Palha Extrafina": "Palha Extrafina",
    }
    
    cat_formatada = mapa_categoria.get(categoria, categoria)
    return f"{cat_formatada} {item_nome}"