# BUG: PDF não renderiza no executável compilado (PyInstaller)

## Sintoma
No modo desenvolvimento (python main.py) o PDF abre normalmente no visualizador interno. Quando compilado para .exe (build_exe.py) o PDF não renderiza — o usuário precisa clicar em "Abrir no Visualizador" para ver o arquivo.

## Causa raiz (já diagnosticada)
No arquivo `build_exe.py`:

1. **`PIL` está explicitamente na lista `excludes`** – o código de renderização (`ui.py` linha ~166 e `parser.py` linha ~139) usa `bitmap.to_pil()`, que depende do Pillow/PIL. No exe compilado essa função lança ImportError silenciosamente, cai no except e não renderiza nada.

2. **`pypdfium2` não tem hook PyInstaller adequado** – a extensão nativa `_pypdfium2.pyd` e a DLL `pypdfium2.dll` não entram no bundle, então `PdfDocument` falha mesmo se PIL estivesse presente.

3. **`hiddenimports` está incompleto** – faltam entradas explícitas para `PIL`, `PIL.Image` e `pypdfium2._pypdfium2`.

## Solução – o que alterar

### 1. Editar `build_exe.py`

```python
# REMOVER da lista excludes:
# 'PIL',

# ADICIONAR na lista hiddenimports:
'PIL',
'PIL.Image',
'pypdfium2._pypdfium2',

# ADICIONAR coleta de binários nativos antes do Analysis:
import pypdfium2, os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
binaries = collect_dynamic_libs('pypdfium2')
datas_pypdfium = collect_data_files('pypdfium2')

# No Analysis, alterar:
#   binaries=[],  →  binaries=binaries,
#   datas=[...],  →  datas=[...] + datas_pypdfium,
```

### 2. (Opcional mas recomendado) Criar `hooks/hook-pypdfium2.py`

```python
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
datas = collect_data_files('pypdfium2')
binaries = collect_dynamic_libs('pypdfium2')
```

E no `Analysis` alterar `hookspath=[]` para `hookspath=['./hooks']`.

## O que NÃO fazer
- Não remover `pypdfium2` dos imports do código fonte
- Não trocar a biblioteca de PDF (o código funciona em dev)
- Não editar `ui.py` para remover PIL sem substituição funcional

## Validação
Após aplicar as mudanças:
1. Limpar: `rmdir /s /q dist build`
2. Recompilar executando `python build_exe.py`
3. Rodar `dist\ValidadorEmbalagens.exe`
4. Selecionar um item → o PDF deve exibir inline no painel inferior (com zoom, navegação, etc.) sem precisar clicar em "Abrir no Visualizador".

## Tarefa extra
**Recompile o programa** assim que as correções estiverem aplicadas e verifique se o `.exe` gerado exibe o PDF inline corretamente.