"""Unit tests for MMSSTV library importer."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image as PILImage

from sstv_core.database.models import SSTVImage, init_database
from sstv_core.filesystem.mmsstv_importer import MMSStvImporter


@pytest.fixture
def temp_library_dir():
    """Create a temporary MMSSTV library directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_session():
    """Create an in-memory database session for testing."""
    engine, session_factory = init_database(":memory:")
    with session_factory() as session:
        yield session


@pytest.fixture
def create_test_image():
    """Factory fixture to create test images."""
    def _create(filepath: Path, width: int = 320, height: int = 256):
        """Create a simple test image."""
        img = PILImage.new("RGB", (width, height), color=(73, 109, 137))
        img.save(filepath)
    return _create


# ============================================================================
# Directory Scanning Tests
# ============================================================================


def test_scan_directory_finds_images(db_session, temp_library_dir, create_test_image):
    """Test directory scanning finds all image files."""
    # Create test images
    create_test_image(temp_library_dir / "test1.jpg")
    create_test_image(temp_library_dir / "test2.png")
    create_test_image(temp_library_dir / "test3.bmp")

    importer = MMSStvImporter(db_session)
    files = importer._scan_directory(temp_library_dir, recursive=False)

    assert len(files) == 3
    assert all(f.suffix.lower() in [".jpg", ".png", ".bmp"] for f in files)


def test_scan_directory_recursive(db_session, temp_library_dir, create_test_image):
    """Test recursive directory scanning."""
    # Create subdirectory structure
    subdir1 = temp_library_dir / "subdir1"
    subdir2 = subdir1 / "subdir2"
    subdir1.mkdir()
    subdir2.mkdir()

    # Create images at different levels
    create_test_image(temp_library_dir / "root.jpg")
    create_test_image(subdir1 / "level1.jpg")
    create_test_image(subdir2 / "level2.jpg")

    importer = MMSStvImporter(db_session)
    files = importer._scan_directory(temp_library_dir, recursive=True)

    assert len(files) == 3


def test_scan_directory_non_recursive(db_session, temp_library_dir, create_test_image):
    """Test non-recursive directory scanning."""
    # Create subdirectory
    subdir = temp_library_dir / "subdir"
    subdir.mkdir()

    # Create images
    create_test_image(temp_library_dir / "root.jpg")
    create_test_image(subdir / "subdir.jpg")

    importer = MMSStvImporter(db_session)
    files = importer._scan_directory(temp_library_dir, recursive=False)

    assert len(files) == 1  # Only root level


def test_scan_directory_filters_non_images(db_session, temp_library_dir, create_test_image):
    """Test directory scanning filters out non-image files."""
    create_test_image(temp_library_dir / "image.jpg")
    (temp_library_dir / "document.txt").write_text("not an image")
    (temp_library_dir / "data.json").write_text("{}")

    importer = MMSStvImporter(db_session)
    files = importer._scan_directory(temp_library_dir, recursive=False)

    assert len(files) == 1


# ============================================================================
# Batch Import Tests
# ============================================================================


def test_import_directory_basic(db_session, temp_library_dir, create_test_image):
    """Test basic directory import."""
    # Create test images
    for i in range(5):
        create_test_image(temp_library_dir / f"test_{i}.jpg")

    importer = MMSStvImporter(db_session)
    result = importer.import_directory(temp_library_dir, recursive=False)

    assert result["imported"] == 5
    assert result["skipped"] == 0
    assert len(result["errors"]) == 0
    assert result["total"] == 5


def test_import_directory_skips_existing(db_session, temp_library_dir, create_test_image):
    """Test import skips already-imported images."""
    # Create test images
    for i in range(3):
        create_test_image(temp_library_dir / f"test_{i}.jpg")

    importer = MMSStvImporter(db_session)

    # First import
    result1 = importer.import_directory(temp_library_dir)
    assert result1["imported"] == 3

    # Second import (all should be skipped)
    result2 = importer.import_directory(temp_library_dir)
    assert result2["imported"] == 0
    assert result2["skipped"] == 3


def test_import_directory_with_progress_callback(db_session, temp_library_dir, create_test_image):
    """Test import calls progress callback."""
    # Create test images
    for i in range(3):
        create_test_image(temp_library_dir / f"test_{i}.jpg")

    progress_calls = []

    def progress_callback(current, total):
        progress_calls.append((current, total))

    importer = MMSStvImporter(db_session)
    result = importer.import_directory(
        temp_library_dir,
        progress_callback=progress_callback,
    )

    assert result["imported"] == 3
    assert len(progress_calls) == 3
    assert progress_calls[-1] == (3, 3)


def test_import_directory_handles_errors(db_session, temp_library_dir, create_test_image):
    """Test import continues despite errors."""
    # Create valid images
    create_test_image(temp_library_dir / "valid1.jpg")
    create_test_image(temp_library_dir / "valid2.jpg")

    # Create corrupted image
    (temp_library_dir / "corrupted.jpg").write_bytes(b"not a valid image")

    importer = MMSStvImporter(db_session)
    result = importer.import_directory(temp_library_dir)

    # Should import valid images despite error
    assert result["imported"] >= 2
    # Error should be logged but import continues
    # (exact count depends on Pillow's error handling)


def test_import_directory_batch_commits(db_session, temp_library_dir, create_test_image):
    """Test import commits in batches."""
    # Create many images (more than batch size)
    num_images = 150  # More than BATCH_SIZE (100)
    for i in range(num_images):
        create_test_image(temp_library_dir / f"test_{i:03d}.jpg")

    importer = MMSStvImporter(db_session)
    result = importer.import_directory(temp_library_dir)

    assert result["imported"] == num_images
    assert result["total"] == num_images

    # Verify all images are in database
    images = db_session.query(SSTVImage).all()
    assert len(images) == num_images


# ============================================================================
# Directory Validation Tests
# ============================================================================


def test_validate_directory_valid(db_session, temp_library_dir, create_test_image):
    """Test validation of valid directory."""
    create_test_image(temp_library_dir / "test.jpg")

    importer = MMSStvImporter(db_session)
    validation = importer.validate_directory(temp_library_dir)

    assert validation["valid"] is True
    assert validation["exists"] is True
    assert validation["is_directory"] is True
    assert validation["image_count"] == 1
    assert validation["error"] is None


def test_validate_directory_not_exists(db_session, temp_library_dir):
    """Test validation of non-existent directory."""
    nonexistent = temp_library_dir / "nonexistent"

    importer = MMSStvImporter(db_session)
    validation = importer.validate_directory(nonexistent)

    assert validation["valid"] is False
    assert validation["exists"] is False
    assert validation["error"] is not None


def test_validate_directory_not_directory(db_session, temp_library_dir):
    """Test validation of file path (not directory)."""
    filepath = temp_library_dir / "file.txt"
    filepath.write_text("not a directory")

    importer = MMSStvImporter(db_session)
    validation = importer.validate_directory(filepath)

    assert validation["valid"] is False
    assert validation["is_directory"] is False
    assert validation["error"] is not None


def test_validate_directory_empty(db_session, temp_library_dir):
    """Test validation of empty directory."""
    importer = MMSStvImporter(db_session)
    validation = importer.validate_directory(temp_library_dir)

    assert validation["valid"] is False
    assert validation["image_count"] == 0
    assert validation["error"] is not None
    assert "No importable images" in validation["error"]


# ============================================================================
# Import Preview Tests
# ============================================================================


def test_get_import_preview(db_session, temp_library_dir, create_test_image):
    """Test getting import preview."""
    # Create test images with SSTV filenames
    for i in range(20):
        filename = f"20260115_14302{i % 10}_ScottieS1_K0ABC.jpg"
        create_test_image(temp_library_dir / filename)

    importer = MMSStvImporter(db_session)
    preview = importer.get_import_preview(temp_library_dir, max_samples=10)

    assert preview["total_files"] == 20
    assert len(preview["samples"]) == 10  # Limited to max_samples
    assert preview["validation"]["valid"] is True

    # Verify samples have metadata
    for sample in preview["samples"]:
        assert "filename" in sample
        assert "path" in sample
        assert "metadata" in sample


def test_get_import_preview_few_files(db_session, temp_library_dir, create_test_image):
    """Test preview with fewer files than max_samples."""
    # Create only 3 images
    for i in range(3):
        create_test_image(temp_library_dir / f"test_{i}.jpg")

    importer = MMSStvImporter(db_session)
    preview = importer.get_import_preview(temp_library_dir, max_samples=10)

    assert preview["total_files"] == 3
    assert len(preview["samples"]) == 3  # All files


def test_get_import_preview_invalid_directory(db_session, temp_library_dir):
    """Test preview of invalid directory."""
    nonexistent = temp_library_dir / "nonexistent"

    importer = MMSStvImporter(db_session)
    preview = importer.get_import_preview(nonexistent)

    assert preview["total_files"] == 0
    assert len(preview["samples"]) == 0
    assert preview["validation"]["valid"] is False


def test_get_import_preview_metadata_parsing(db_session, temp_library_dir, create_test_image):
    """Test preview parses metadata correctly."""
    filename = "20260115_143022_ScottieS1_K0ABC.jpg"
    create_test_image(temp_library_dir / filename)

    importer = MMSStvImporter(db_session)
    preview = importer.get_import_preview(temp_library_dir)

    assert len(preview["samples"]) == 1
    sample = preview["samples"][0]

    assert sample["filename"] == filename
    assert sample["metadata"]["mode"] == "ScottieS1"
    assert sample["metadata"]["callsign"] == "K0ABC"
