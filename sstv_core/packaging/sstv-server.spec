# PyInstaller spec for the engine the desktop shell spawns (#143).
#
# One folder, not one file. A one-file build unpacks itself to a temp
# directory on every launch: slower to start, and it re-extracts the native
# libraries (PortAudio, libsndfile, the NumPy/SciPy/OpenCV stack) each time,
# which is exactly the kind of thing that works on this machine and fails on
# someone else's. Tauri bundles the folder happily.
#
# Build it with scripts/build_engine.py, which names the binary the way Tauri
# requires and puts it where the bundler looks.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT = Path(SPECPATH).parent
SRC = PROJECT / "src"

# Alembic reads these off disk at runtime: init_database() upgrades an
# existing install by script_location, so the migration scripts have to ship
# as files rather than be frozen into the binary.
datas = [
    (str(SRC / "sstv_core" / "database" / "migrations"), "sstv_core/database/migrations"),
    (str(PROJECT / "templates"), "templates"),
]

# Smart-reply templates and anything else a package carries as data.
datas += collect_data_files("sstv_core")

hiddenimports = [
    # uvicorn picks its implementation at runtime, so the analysis cannot see
    # these from the import graph.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    # Alembic loads env.py and each revision by path at runtime.
    "alembic.config",
    "alembic.script",
    "alembic.runtime.migration",
]
# Every decoder, encoder and route is reached through a string in one place or
# another (mode dispatch, router includes), so take the package wholesale.
hiddenimports += collect_submodules("sstv_core")

a = Analysis(
    [str(PROJECT / "packaging" / "server_entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Nothing here draws a window: the shell is the UI. Excluding the GUI
    # toolkits keeps the bundle from carrying a second one.
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sstv-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="sstv-server",
)
