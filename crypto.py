"""Manipulação segura de ZIP com criptografia AES-256 e descoberta genérica de itens."""

import os
import hashlib
import shutil
import tempfile
import logging
import re
import json
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

import pyzipper

logger = logging.getLogger(__name__)

# Constantes
MAX_BACKUPS = 5
CHUNK_SIZE = 8192


# =============================================================================
# Descoberta Genérica de Itens (Spec 05)
# =============================================================================

def eh_pasta_item(arquivos: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Retorna (True, nome_do_pdf) se a pasta contém os 3 arquivos obrigatórios.
    Funciona para QUALQUER profundidade e nomenclatura de pastas.
    
    Obrigatórios:
    - Descricao Tecnica.docx
    - checklist.json
    - Exatamente 1 arquivo .pdf (qualquer nome)
    """
    tem_docx = 'Descricao Tecnica.docx' in arquivos
    tem_checklist = 'checklist.json' in arquivos
    pdfs = [f for f in arquivos if f.lower().endswith('.pdf')]
    
    if tem_docx and tem_checklist and len(pdfs) == 1:
        return True, pdfs[0]
    return False, None


def _normalizar_slug(texto: str) -> str:
    """Normaliza texto para slug: minúsculas, remove acentos, substitui não-alfanuméricos por _."""
    # Remover acentos básicos
    substituicoes = {
        'ç': 'c', 'á': 'a', 'à': 'a', 'ã': 'a', 'é': 'e', 'ê': 'e',
        'í': 'i', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ú': 'u',
        'ü': 'u', 'ñ': 'n'
    }
    texto = texto.lower()
    for a, b in substituicoes.items():
        texto = texto.replace(a, b)
    # Substituir espaços e caracteres especiais por underscore
    texto = re.sub(r'[^a-z0-9]+', '_', texto)
    return texto.strip('_')


def gerar_item_id(caminho_relativo: Path) -> str:
    """
    Gera item_id único e estável a partir do caminho relativo completo.
    
    Exemplos:
    - 'Chips Lisa/Cebola Salsa 115g' → 'chips_lisa_cebola_salsa_115g'
    - 'BOBINAS DE EMBALAGEM/ASSAÍ/CHIPS/Lisa/Cebola Salsa 115g' 
      → 'bobinas_de_embalagem_assai_chips_lisa_cebola_salsa_115g'
    """
    slug = str(caminho_relativo).replace('\\', '/')
    return _normalizar_slug(slug)


def extrair_metadados_do_caminho(pasta_zip: str) -> Tuple[str, str, str]:
    """
    Extrai marca, linha, categoria do caminho relativo.
    
    Estruturas suportadas:
    - [raiz]/[marca]/[linha]/[categoria]/[item]  (5 partes) -> marca, linha, categoria
    - [marca]/[linha]/[categoria]/[item]          (4 partes) -> marca, linha, categoria
    - [linha]/[categoria]/[item]                  (3 partes) -> '', linha, categoria
    - [categoria]/[item]                          (2 partes) -> '', '', categoria
    
    Retorna (marca, linha, categoria) - strings vazias se não aplicável.
    """
    partes = [p for p in pasta_zip.split('/') if p]
    n = len(partes)
    
    if n >= 5:
        # [raiz]/[marca]/[linha]/[categoria]/[item]
        return partes[-5], partes[-4], partes[-3]
    elif n == 4:
        # [marca]/[linha]/[categoria]/[item] - assume marca/linha/categoria
        return partes[-4], partes[-3], partes[-2]
    elif n == 3:
        # [linha]/[categoria]/[item] ou [marca]/[categoria]/[item]
        # Heurística: se primeira parte parece marca (maiúsculas), usa como marca
        if partes[0].isupper():
            return partes[0], '', partes[1]
        return '', partes[0], partes[1]
    elif n == 2:
        # [categoria]/[item] - legado
        return '', '', partes[0]
    return '', '', ''


def descobrir_itens_zip(zip_path: Path, senha: str, cache_dir: Path) -> List:
    """
    Descobre todos os itens (SKUs) no ZIP de forma genérica.
    
    1. Extrai ZIP para cache_dir (usa extrair_zip_seguro existente).
    2. Percorre recursivamente (os.walk) a partir da raiz extraída.
    3. Para cada diretório, aplica eh_pasta_item().
    4. Se True: cria Item com metadados derivados do caminho.
    5. Retorna lista ordenada alfabeticamente por (marca, linha, categoria, nome).
    """
    from models import Item, Checklist
    
    # Extrair ZIP para cache
    if not extrair_zip_seguro(zip_path, senha, cache_dir):
        return []
    
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
        nome_amigavel = nome_pasta.replace('_', ' ').replace('-', ' ').title()
        
        # Para itens legados sem marca/linha, usar categoria como fallback
        if not marca and not linha and categoria:
            pass  # categoria já preenchida
        elif not marca and not linha and not categoria:
            # Estrutura totalmente plana
            categoria = 'Geral'
        
        item = Item(
            id=item_id,
            nome=nome_amigavel,
            marca=marca.title() if marca else '',
            linha=linha.title() if linha else '',
            categoria=categoria.title() if categoria else '',
            pasta_zip=caminho_relativo,
            pdf_nome=pdf_nome,
            pdf_path=Path(root) / pdf_nome,
            docx_path=Path(root) / 'Descricao Tecnica.docx',
            checklist=Checklist(item_id=item_id)
        )
        itens.append(item)
    
    # Ordenar: marca, linha, categoria, nome (itens sem marca/linha vão para o final)
    def sort_key(i):
        return (
            i.marca.lower() if i.marca else 'zzz',
            i.linha.lower() if i.linha else 'zzz',
            i.categoria.lower() if i.categoria else 'zzz',
            i.nome.lower()
        )
    
    return sorted(itens, key=sort_key)


def validar_estrutura_zip(zip_path: Path, senha: str) -> List[str]:
    """
    Valida a estrutura do ZIP usando descoberta genérica.
    Retorna lista de erros e avisos.
    """
    erros = []
    avisos = []
    
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            
            # Extrair e descobrir
            if not extrair_zip_seguro(zip_path, senha, tmp_path):
                erros.append("Falha ao extrair ZIP para validação")
                return erros
            
            itens = descobrir_itens_zip(zip_path, senha, tmp_path)
            
            if not itens:
                erros.append(
                    "Nenhum item (SKU) válido encontrado. "
                    "Verifique se as pastas contêm: "
                    "Descricao Tecnica.docx, checklist.json e exatamente 1 arquivo .pdf"
                )
            
            # Duplicatas de item_id
            ids = [i.id for i in itens]
            duplicados = [id_ for id_ in set(ids) if ids.count(id_) > 1]
            if duplicados:
                erros.append(f"IDs duplicados (conflito de slug): {duplicados}")
            
            # Avisos informativos
            for item in itens:
                if not item.marca and not item.linha and item.categoria == 'Geral':
                    avisos.append(f"Item sem hierarquia detectada (estrutura plana): {item.pasta_zip}")
                if item.pdf_nome != 'Conferencia Visual.pdf':
                    avisos.append(f"PDF com nome não-padrão: {item.pasta_zip}/{item.pdf_nome}")
    
    except pyzipper.BadZipFile:
        erros.append("Arquivo ZIP corrompido ou inválido")
    except RuntimeError as e:
        if "password" in str(e).lower():
            erros.append("Senha incorreta para o arquivo ZIP")
        else:
            erros.append(f"Erro ao ler ZIP: {e}")
    except Exception as e:
        erros.append(f"Erro inesperado na validação: {e}")
    
    return erros + avisos


def hash_arquivo(path: Path) -> str:
    """Gera hash SHA-256 do arquivo."""
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.error(f"Erro ao calcular hash de {path}: {e}")
        raise


def _limpar_backups_antigos(zip_path: Path) -> None:
    """Mantém apenas os últimos MAX_BACKUPS arquivos de backup."""
    pasta = zip_path.parent
    padrao = f"{zip_path.stem}.backup_*.zip"
    backups = sorted(pasta.glob(padrao), key=lambda p: p.stat().st_mtime, reverse=True)
    for backup in backups[MAX_BACKUPS:]:
        try:
            backup.unlink()
            logger.info(f"Backup antigo removido: {backup.name}")
        except Exception as e:
            logger.warning(f"Erro ao remover backup {backup}: {e}")


def validar_estrutura_zip(zip_path: Path, senha: str) -> List[str]:
    """Valida a estrutura interna do ZIP, retornando lista de inconsistências."""
    erros = []
    try:
        with pyzipper.AESZipFile(zip_path, 'r', compression=pyzipper.ZIP_DEFLATED) as zf:
            zf.setpassword(senha.encode('utf-8'))
            zf.testzip()  # Testa integridade CRC
            
            # Verificar estrutura esperada: Categoria/Item/Arquivos
            arquivos = zf.namelist()
            
            if not arquivos:
                erros.append("ZIP vazio")
                return erros
            
            # Agrupar por pasta de item (profundidade 2: Categoria/Item/)
            itens_encontrados = set()
            for nome in arquivos:
                partes = nome.rstrip('/').split('/')
                if len(partes) >= 2:
                    item_path = '/'.join(partes[:2])
                    itens_encontrados.add(item_path)
            
            # Verificar arquivos obrigatórios por item
            for item_path in sorted(itens_encontrados):
                tem_pdf = any(f.startswith(item_path + '/') and f.endswith('Conferencia Visual.pdf') for f in arquivos)
                tem_docx = any(f.startswith(item_path + '/') and f.endswith('Descricao Tecnica.docx') for f in arquivos)
                tem_checklist = any(f.startswith(item_path + '/') and f.endswith('checklist.json') for f in arquivos)
                
                if not tem_pdf:
                    erros.append(f"{item_path}: 'Conferencia Visual.pdf' ausente")
                if not tem_docx:
                    erros.append(f"{item_path}: 'Descricao Tecnica.docx' ausente")
                if not tem_checklist:
                    erros.append(f"{item_path}: 'checklist.json' ausente")
                    
    except pyzipper.BadZipFile:
        erros.append("Arquivo ZIP corrompido ou inválido")
    except RuntimeError as e:
        if "password" in str(e).lower():
            erros.append("Senha incorreta para o arquivo ZIP")
        else:
            erros.append(f"Erro ao ler ZIP: {e}")
    except Exception as e:
        erros.append(f"Erro inesperado: {e}")
    
    return erros


def extrair_zip_seguro(zip_path: Path, senha: str, destino_cache: Path) -> bool:
    """
    Extrai o ZIP para o cache local de forma atômica.
    Usa pasta temporária com GUID e move atomicamente após sucesso.
    Preserva nomes de arquivos com acentos (UTF-8).
    """
    import uuid
    
    temp_dir = destino_cache.parent / f".tmp_extract_{uuid.uuid4().hex[:8]}"
    
    try:
        # Limpar temp anterior se existir
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        temp_dir.mkdir(parents=True)
        
        with pyzipper.AESZipFile(zip_path, 'r', compression=pyzipper.ZIP_DEFLATED) as zf:
            zf.setpassword(senha.encode('utf-8'))
            
            # Testar integridade antes de extrair
            bad_file = zf.testzip()
            if bad_file:
                raise RuntimeError(f"Arquivo corrompido no ZIP: {bad_file}")
            
            # Extrair tudo para temp preservando UTF-8
            # pyzipper/pyzipfile usa UTF-8 por padrão para nomes de arquivos
            zf.extractall(temp_dir)
        
        # Remover cache antigo se existir
        if destino_cache.exists():
            shutil.rmtree(destino_cache, ignore_errors=True)
        
        # Mover atomicamente (os.replace é atômico no Windows)
        os.replace(temp_dir, destino_cache)
        
        logger.info(f"ZIP extraído com sucesso para {destino_cache}")
        return True
        
    except RuntimeError as e:
        if "password" in str(e).lower():
            logger.error("Senha incorreta para o ZIP")
            raise ValueError("Senha incorreta") from e
        logger.error(f"Erro na extração: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro inesperado na extração: {e}")
        raise
    finally:
        # Limpeza garantida do temp
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def _coletar_checklists_do_zip(zip_path: Path, senha: str, temp_dir: Path) -> dict:
    """Extrai apenas os checklists.json do ZIP para um diretório temporário."""
    checklists = {}
    try:
        with pyzipper.AESZipFile(zip_path, 'r', compression=pyzipper.ZIP_DEFLATED) as zf:
            zf.setpassword(senha.encode('utf-8'))
            for nome in zf.namelist():
                if nome.endswith('checklist.json'):
                    # Extrair para temp mantendo estrutura
                    zf.extract(nome, temp_dir)
                    # Ler conteúdo
                    arquivo = temp_dir / nome
                    if arquivo.exists():
                        import json
                        with open(arquivo, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        checklists[data.get('item_id', nome)] = data
    except Exception as e:
        logger.error(f"Erro ao coletar checklists do ZIP: {e}")
    return checklists


def _atualizar_checklists_no_zip(zip_path: Path, senha: str, checklists_dict: dict, temp_dir: Path) -> bool:
    """
    Reescreve o ZIP atualizando apenas os arquivos checklist.json.
    Mantém todos os outros arquivos (PDF, DOCX) inalterados.
    """
    try:
        # 1. Ler todo o ZIP original para memória
        with pyzipper.AESZipFile(zip_path, 'r', compression=pyzipper.ZIP_DEFLATED) as zf_in:
            zf_in.setpassword(senha.encode('utf-8'))
            
            # Preparar dados dos checklists atualizados
            checklist_bytes = {}
            for item_id, data in checklists_dict.items():
                import json
                # Encontrar o caminho original do checklist no ZIP
                # Assumindo estrutura Categoria/Item/checklist.json
                # Precisamos mapear item_id -> caminho no ZIP
                pass  # Será implementado na função principal
        
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar checklists no ZIP: {e}")
        return False


def criar_zip_com_checklists(zip_path: Path, senha: str, cache_dir: Path, checklists_dict: dict) -> bool:
    """
    Atualiza o ZIP remoto com a fusão dos checklists.
    Cria backup antes, testa o resultado, substitui atomicamente.
    """
    import uuid
    import json
    
    # 1. Criar backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = zip_path.parent / f"{zip_path.stem}.backup_{timestamp}.zip"
    
    try:
        shutil.copy2(zip_path, backup_path)
        logger.info(f"Backup criado: {backup_path}")
    except Exception as e:
        logger.error(f"Falha ao criar backup: {e}")
        return False
    
    # 2. Limpar backups antigos
    _limpar_backups_antigos(zip_path)
    
    # 3. Preparar diretório temporário para novo ZIP
    temp_zip = zip_path.parent / f".tmp_{uuid.uuid4().hex[:8]}.zip"
    temp_extract = zip_path.parent / f".tmp_extract_{uuid.uuid4().hex[:8]}"
    
    try:
        # Extrair ZIP original para temp
        with pyzipper.AESZipFile(zip_path, 'r', compression=pyzipper.ZIP_DEFLATED) as zf_in:
            zf_in.setpassword(senha.encode('utf-8'))
            zf_in.extractall(temp_extract)
        
        # Atualizar checklists.json na estrutura extraída
        for item_id, checklist_data in checklists_dict.items():
            # Encontrar o arquivo checklist correspondente
            for root, dirs, files in os.walk(temp_extract):
                for file in files:
                    if file == 'checklist.json':
                        checklist_path = Path(root) / file
                        # Ler para verificar item_id
                        try:
                            with open(checklist_path, 'r', encoding='utf-8') as f:
                                existing = json.load(f)
                            if existing.get('item_id') == item_id:
                                # Atualizar
                                with open(checklist_path, 'w', encoding='utf-8') as f:
                                    json.dump(checklist_data, f, indent=2, ensure_ascii=False)
                                logger.debug(f"Checklist atualizado: {checklist_path}")
                        except Exception:
                            pass
        
        # Criar novo ZIP a partir da estrutura atualizada
        with pyzipper.AESZipFile(
            temp_zip, 'w', 
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES
        ) as zf_out:
            zf_out.setpassword(senha.encode('utf-8'))
            
            for root, dirs, files in os.walk(temp_extract):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(temp_extract).as_posix()
                    zf_out.write(file_path, arcname)
        
        # 4. Testar o novo ZIP
        with pyzipper.AESZipFile(temp_zip, 'r', compression=pyzipper.ZIP_DEFLATED) as zf_test:
            zf_test.setpassword(senha.encode('utf-8'))
            bad = zf_test.testzip()
            if bad:
                raise RuntimeError(f"ZIP gerado corrompido: {bad}")
        
        # 5. Substituir atomicamente
        os.replace(temp_zip, zip_path)
        logger.info(f"ZIP atualizado com sucesso: {zip_path}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao criar ZIP com checklists: {e}")
        # Tentar restaurar backup
        try:
            if backup_path.exists():
                os.replace(backup_path, zip_path)
                logger.info("Backup restaurado após falha")
        except Exception as restore_err:
            logger.critical(f"FALHA CRÍTICA: Não foi possível restaurar backup: {restore_err}")
        return False
    finally:
        # Limpeza
        for d in [temp_zip, temp_extract]:
            if d.exists():
                if d.is_file():
                    d.unlink(missing_ok=True)
                else:
                    shutil.rmtree(d, ignore_errors=True)


def extrair_checklists_zip(zip_path: Path, senha: str) -> dict:
    """Extrai apenas os checklists.json do ZIP remoto."""
    import uuid
    import json
    
    temp_dir = zip_path.parent / f".tmp_checklists_{uuid.uuid4().hex[:8]}"
    checklists = {}
    
    try:
        temp_dir.mkdir(parents=True)
        
        with pyzipper.AESZipFile(zip_path, 'r', compression=pyzipper.ZIP_DEFLATED) as zf:
            zf.setpassword(senha.encode('utf-8'))
            for nome in zf.namelist():
                if nome.endswith('checklist.json'):
                    zf.extract(nome, temp_dir)
                    arquivo = temp_dir / nome
                    if arquivo.exists():
                        with open(arquivo, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        checklists[data.get('item_id', nome)] = data
        
        return checklists
    except Exception as e:
        logger.error(f"Erro ao extrair checklists do ZIP: {e}")
        return {}
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)