"""Verify project setup and dependencies are correctly installed."""

import importlib.metadata
import sys


def test_python_version():
    """Ensure Python 3.10+ is being used."""
    assert sys.version_info >= (3, 10), "Python 3.10+ required"


def test_core_dependencies_installed():
    """Verify all core dependencies are importable."""
    required_packages = [
        "numpy",
        "scipy",
        "PIL",  # Pillow
        "sqlalchemy",
        "alembic",
        "fastapi",
        "uvicorn",
        "websockets",
        "pydantic",
        "serial",  # pyserial
        "watchdog",
    ]

    for package in required_packages:
        try:
            __import__(package)
        except ImportError as e:
            raise AssertionError(f"Required package '{package}' not installed: {e}")


def test_dependency_versions():
    """Check minimum versions of key dependencies."""
    version_requirements = {
        "numpy": "1.24",
        "scipy": "1.10",
        "Pillow": "10.0",
        "SQLAlchemy": "2.0",
        "fastapi": "0.104",
        "pydantic": "2.0",
    }

    for package, min_version in version_requirements.items():
        installed_version = importlib.metadata.version(package)
        # Simple version comparison (major.minor)
        installed_parts = [int(x) for x in installed_version.split(".")[:2]]
        required_parts = [int(x) for x in min_version.split(".")[:2]]

        assert installed_parts >= required_parts, (
            f"{package} version {installed_version} < required {min_version}"
        )


def test_sstv_core_package_importable():
    """Verify the sstv_core package can be imported."""
    # This will work once installed in development mode
    # For now, just verify the structure exists
    import pathlib

    src_dir = pathlib.Path(__file__).parent.parent / "src" / "sstv_core"
    assert src_dir.exists(), f"Source directory not found: {src_dir}"
    assert (src_dir / "__init__.py").exists(), "Missing __init__.py in sstv_core"
    assert (src_dir / "api" / "__init__.py").exists(), "Missing api/__init__.py"
    assert (src_dir / "database" / "__init__.py").exists(), "Missing database/__init__.py"
    assert (src_dir / "engine" / "__init__.py").exists(), "Missing engine/__init__.py"


def test_sounddevice_package_info():
    """Check sounddevice is installed (runtime requires PortAudio)."""
    version = importlib.metadata.version("sounddevice")
    assert version, "sounddevice package not found"
    # Note: Actually importing sounddevice requires libportaudio2 system library
