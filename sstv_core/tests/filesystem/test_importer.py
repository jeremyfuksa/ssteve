"""Unit tests for image importer and metadata parsing."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image as PILImage

from sstv_core.database.models import SSTVImage, init_database
from sstv_core.filesystem.importer import (
    ImageImporter,
    parse_image_metadata,
    _parse_filename,
    _extract_exif_metadata,
)


@pytest.fixture
def temp_image_dir():
    """Create a temporary directory for test images."""
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
    """Factory fixture to create test images with EXIF data."""
    def _create(
        filepath: Path,
        width: int = 320,
        height: int = 256,
        exif_data: dict = None,
    ):
        """Create a test image file with optional EXIF data."""
        # Create a simple test image
        img = PILImage.new("RGB", (width, height), color=(73, 109, 137))

        # Add EXIF data if provided
        if exif_data:
            from PIL import Image as PILImage
            from PIL.ExifTags import TAGS

            exif_dict = {}
            for tag_name, value in exif_data.items():
                # Find tag ID from name
                tag_id = None
                for tid, name in TAGS.items():
                    if name == tag_name:
                        tag_id = tid
                        break
                if tag_id:
                    exif_dict[tag_id] = value

            if exif_dict:
                exif = PILImage.Exif()
                for tag_id, value in exif_dict.items():
                    exif[tag_id] = value
                img.save(filepath, exif=exif)
                return

        # Save without EXIF
        img.save(filepath)

    return _create


# ============================================================================
# Filename Parsing Tests
# ============================================================================


def test_parse_filename_full_format():
    """Test parsing filename with all fields."""
    result = _parse_filename("20260115_143022_ScottieS1_K0ABC")

    assert result is not None
    assert result["timestamp"] == datetime(2026, 1, 15, 14, 30, 22)
    assert result["mode"] == "ScottieS1"
    assert result["callsign"] == "K0ABC"


def test_parse_filename_no_callsign():
    """Test parsing filename without callsign."""
    result = _parse_filename("20260115_143022_MartinM1")

    assert result is not None
    assert result["timestamp"] == datetime(2026, 1, 15, 14, 30, 22)
    assert result["mode"] == "MartinM1"
    assert "callsign" not in result


def test_parse_filename_no_mode():
    """Test parsing filename without mode."""
    result = _parse_filename("20260115_143022")

    assert result is not None
    assert result["timestamp"] == datetime(2026, 1, 15, 14, 30, 22)
    assert "mode" not in result


def test_parse_filename_case_insensitive_mode():
    """Test parsing filename with case-insensitive mode."""
    result = _parse_filename("20260115_143022_scotties1")

    assert result is not None
    assert result["mode"] == "ScottieS1"  # Should normalize to correct case


def test_parse_filename_invalid_format():
    """Test parsing filename that doesn't match pattern."""
    result = _parse_filename("random_filename")
    assert result is None

    result = _parse_filename("2026-01-15_143022")  # Wrong date separator
    assert result is None


def test_parse_filename_invalid_timestamp():
    """Test parsing filename with invalid timestamp."""
    result = _parse_filename("20261332_143022_ScottieS1")  # Invalid month
    assert result is None


# ============================================================================
# EXIF Extraction Tests
# ============================================================================


def test_extract_exif_datetime(temp_image_dir, create_test_image):
    """Test EXIF datetime extraction."""
    filepath = temp_image_dir / "test.jpg"
    create_test_image(
        filepath,
        exif_data={"DateTime": "2026:01:15 14:30:22"}
    )

    metadata = _extract_exif_metadata(filepath)

    assert metadata is not None
    assert "timestamp" in metadata
    assert metadata["timestamp"] == datetime(2026, 1, 15, 14, 30, 22)


def test_extract_exif_artist(temp_image_dir, create_test_image):
    """Test EXIF Artist (operator name) extraction."""
    filepath = temp_image_dir / "test.jpg"
    create_test_image(
        filepath,
        exif_data={"Artist": "John Doe KB1ABC"}
    )

    metadata = _extract_exif_metadata(filepath)

    assert metadata is not None
    assert metadata.get("operator_name") == "John Doe KB1ABC"


def test_extract_exif_description(temp_image_dir, create_test_image):
    """Test EXIF ImageDescription (comments) extraction."""
    filepath = temp_image_dir / "test.jpg"
    create_test_image(
        filepath,
        exif_data={"ImageDescription": "Test SSTV image"}
    )

    metadata = _extract_exif_metadata(filepath)

    assert metadata is not None
    assert metadata.get("comments") == "Test SSTV image"


def test_extract_exif_no_data(temp_image_dir, create_test_image):
    """Test EXIF extraction from image without EXIF data."""
    filepath = temp_image_dir / "test.jpg"
    create_test_image(filepath)  # No EXIF

    metadata = _extract_exif_metadata(filepath)
    assert metadata is None


# ============================================================================
# Metadata Parsing Integration Tests
# ============================================================================


def test_parse_image_metadata_from_filename(temp_image_dir, create_test_image):
    """Test metadata parsing prioritizing filename."""
    filepath = temp_image_dir / "20260115_143022_ScottieS1_K0ABC.jpg"
    create_test_image(filepath)

    metadata = parse_image_metadata(filepath)

    assert metadata["timestamp"] == datetime(2026, 1, 15, 14, 30, 22)
    assert metadata["mode"] == "ScottieS1"
    assert metadata["callsign"] == "K0ABC"
    assert metadata["is_received"] is True


def test_parse_image_metadata_transmitted_directory(temp_image_dir, create_test_image):
    """Test metadata parsing recognizes 'transmitted' directory."""
    tx_dir = temp_image_dir / "transmitted"
    tx_dir.mkdir()
    filepath = tx_dir / "20260115_143022_ScottieS1.jpg"
    create_test_image(filepath)

    metadata = parse_image_metadata(filepath)

    assert metadata["is_received"] is False  # In transmitted dir


def test_parse_image_metadata_fallback_to_mtime(temp_image_dir, create_test_image):
    """Test metadata parsing falls back to file mtime when no timestamp."""
    filepath = temp_image_dir / "random_name.jpg"
    create_test_image(filepath)

    metadata = parse_image_metadata(filepath)

    assert metadata["timestamp"] is not None
    assert isinstance(metadata["timestamp"], datetime)
    assert metadata["mode"] == "Unknown"


def test_parse_image_metadata_exif_overrides_filename(temp_image_dir, create_test_image):
    """Test EXIF timestamp overrides filename timestamp."""
    filepath = temp_image_dir / "20260115_143022_ScottieS1.jpg"
    create_test_image(
        filepath,
        exif_data={
            "DateTime": "2026:01:16 10:00:00",
            "Artist": "Jane Doe",
        }
    )

    metadata = parse_image_metadata(filepath)

    # EXIF timestamp should override filename
    assert metadata["timestamp"] == datetime(2026, 1, 16, 10, 0, 0)
    # Filename metadata should still be present
    assert metadata["mode"] == "ScottieS1"
    # EXIF artist should be present
    assert metadata["operator_name"] == "Jane Doe"


# ============================================================================
# ImageImporter Tests
# ============================================================================


def test_import_image_creates_record(db_session, temp_image_dir, create_test_image):
    """Test importing a new image creates database record."""
    filepath = temp_image_dir / "20260115_143022_ScottieS1_K0ABC.jpg"
    create_test_image(filepath)

    importer = ImageImporter(db_session)
    image = importer.import_image(filepath)

    assert image is not None
    assert image.id is not None
    assert image.filename == "20260115_143022_ScottieS1_K0ABC.jpg"
    assert str(filepath.resolve()) in image.filepath
    assert image.mode == "ScottieS1"
    assert image.callsign == "K0ABC"
    assert image.is_received is True


def test_import_image_skips_existing(db_session, temp_image_dir, create_test_image):
    """Test importing an existing image returns the existing record."""
    filepath = temp_image_dir / "test.jpg"
    create_test_image(filepath)

    importer = ImageImporter(db_session)

    # Import once
    image1 = importer.import_image(filepath)
    image1_id = image1.id

    # Import again
    image2 = importer.import_image(filepath)

    assert image2.id == image1_id  # Same record


def test_import_image_nonexistent_file(db_session, temp_image_dir):
    """Test importing a nonexistent file returns None."""
    filepath = temp_image_dir / "nonexistent.jpg"

    importer = ImageImporter(db_session)
    result = importer.import_image(filepath)

    assert result is None


def test_update_image_metadata(db_session, temp_image_dir, create_test_image):
    """Test updating metadata for an existing image."""
    filepath = temp_image_dir / "20260115_143022_ScottieS1.jpg"
    create_test_image(filepath)

    importer = ImageImporter(db_session)
    image = importer.import_image(filepath)
    original_id = image.id

    # Recreate image with different EXIF
    filepath.unlink()
    create_test_image(
        filepath,
        exif_data={"Artist": "Updated Operator"}
    )

    # Update metadata
    updated = importer.update_image_metadata(filepath)

    assert updated.id == original_id  # Same record
    assert updated.operator_name == "Updated Operator"


def test_remove_image(db_session, temp_image_dir, create_test_image):
    """Test removing an image from the database."""
    filepath = temp_image_dir / "test.jpg"
    create_test_image(filepath)

    importer = ImageImporter(db_session)
    image = importer.import_image(filepath)
    image_id = image.id

    # Remove image
    result = importer.remove_image(filepath)
    assert result is True

    # Verify removed
    removed = db_session.get(SSTVImage, image_id)
    assert removed is None


def test_remove_nonexistent_image(db_session, temp_image_dir):
    """Test removing a nonexistent image returns False."""
    filepath = temp_image_dir / "nonexistent.jpg"

    importer = ImageImporter(db_session)
    result = importer.remove_image(filepath)

    assert result is False


def test_move_image(db_session, temp_image_dir, create_test_image):
    """Test moving/renaming an image updates the database."""
    src_path = temp_image_dir / "20260115_143022_ScottieS1.jpg"
    dest_path = temp_image_dir / "20260115_143022_MartinM1_K0ABC.jpg"

    create_test_image(src_path)

    importer = ImageImporter(db_session)
    image = importer.import_image(src_path)
    original_id = image.id

    # Move file
    src_path.rename(dest_path)

    # Update database
    moved = importer.move_image(src_path, dest_path)

    assert moved.id == original_id  # Same record
    assert moved.filename == "20260115_143022_MartinM1_K0ABC.jpg"
    assert moved.mode == "MartinM1"  # Updated from new filename
    assert moved.callsign == "K0ABC"


def test_import_directory(db_session, temp_image_dir, create_test_image):
    """Test batch importing all images from a directory."""
    # Create test images
    for i in range(5):
        filepath = temp_image_dir / f"test_{i}.jpg"
        create_test_image(filepath)

    importer = ImageImporter(db_session)
    imported, skipped, errors = importer.import_directory(temp_image_dir, recursive=False)

    assert imported == 5
    assert skipped == 0
    assert len(errors) == 0

    # Verify all imported
    images = db_session.query(SSTVImage).all()
    assert len(images) == 5


def test_import_directory_recursive(db_session, temp_image_dir, create_test_image):
    """Test recursive directory import."""
    # Create subdirectory
    subdir = temp_image_dir / "subdir"
    subdir.mkdir()

    # Create images in both directories
    create_test_image(temp_image_dir / "test1.jpg")
    create_test_image(subdir / "test2.jpg")

    importer = ImageImporter(db_session)
    imported, skipped, errors = importer.import_directory(temp_image_dir, recursive=True)

    assert imported == 2
    assert skipped == 0


def test_import_directory_filters_extensions(db_session, temp_image_dir, create_test_image):
    """Test directory import only imports supported formats."""
    # Create supported formats
    create_test_image(temp_image_dir / "test.jpg")
    create_test_image(temp_image_dir / "test.png")

    # Create unsupported format
    (temp_image_dir / "test.txt").write_text("not an image")

    importer = ImageImporter(db_session)
    imported, skipped, errors = importer.import_directory(temp_image_dir, recursive=False)

    assert imported == 2  # Only jpg and png
    assert skipped == 0
