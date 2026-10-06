#!/usr/bin/env python3
"""Script de compilação PyInstaller para Explorador de Arquivos Zip."""

import sys
import shutil
from pathlib import Path
import subprocess


def main():
    project_root = Path(__file__).parent
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    
    # Limpar builds anteriores
    for d in [dist_dir, build_dir]:
        if d.exists():
            print(f"Limpando {d}...")
            shutil.rmtree(d, ignore_errors=True)
    
    # Arquivo spec personalizado
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import pypdfium2, os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
binaries = collect_dynamic_libs('pypdfium2') + collect_dynamic_libs('pypdfium2_raw')
datas_pypdfium = collect_data_files('pypdfium2') + collect_data_files('pypdfium2_raw')

a = Analysis(
    ['main.py'],
    pathex=['{project_root.as_posix()}'],
    binaries=binaries,
    datas=[
        ('{project_root.as_posix()}/resources', 'resources'),
    ] + datas_pypdfium,
    hiddenimports=[
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineWidgets', 
        'PySide6.QtWebEngineCore',
        'PySide6.QtPrintSupport',
        'mammoth',
        'pypdfium2',
        'pyzipper',
        'watchdog',
        'pkg_resources.py2_warn',
        'PIL',
        'PIL.Image',
        'pypdfium2._pypdfium2',
        'pypdfium2_raw',
        'pypdfium2_raw.bindings',
    ],
    hookspath=['./hooks'],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'cv2',
        'test',
        'unittest',
        'pydoc',
        'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ExploradorZip',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='{project_root.as_posix()}/resources/icon.ico',
)
'''
    
    spec_file = project_root / "ExploradorZip.spec"
    spec_file.write_text(spec_content, encoding="utf-8")
    
    print("Executando PyInstaller...")
    result = subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file)
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print("ERRO na compilação:")
        print(result.stdout)
        print(result.stderr)
        return 1
    
    print("\nCompilação concluída com sucesso!")
    exe_path = dist_dir / "ExploradorZip.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"Executável: {exe_path}")
        print(f"Tamanho: {size_mb:.1f} MB")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())