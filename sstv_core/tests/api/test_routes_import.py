"""
Unit tests for import endpoints.

Tests /import/mmsstv, /import/validate, and /import/preview endpoints.
The MMSStvImporter and database layer are mocked - these tests cover the
HTTP contract only.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.api.routes import import_routes


@pytest.fixture(autouse=True)
def mock_db_session():
    """Override the import routes' DB dependency with a mock session."""
    mock_session = MagicMock()
    previous = app.dependency_overrides.get(import_routes.get_db)
    app.dependency_overrides[import_routes.get_db] = lambda: mock_session
    yield mock_session
    if previous is not None:
        app.dependency_overrides[import_routes.get_db] = previous
    else:
        del app.dependency_overrides[import_routes.get_db]


@pytest.fixture
def mock_importer():
    """Patch MMSStvImporter where the route imports it."""
    with patch("sstv_core.api.routes.import_routes.MMSStvImporter") as mock_cls:
        yield mock_cls.return_value


client = TestClient(app)


class TestImportMMSSTV:
    """Test POST /import/mmsstv endpoint."""

    def test_import_happy_path(self, tmp_path, mock_importer):
        """Should import a valid directory and return statistics."""
        mock_importer.import_directory.return_value = {
            "imported": 5,
            "skipped": 2,
            "errors": [],
            "total": 7,
        }

        response = client.post(
            "/api/v1/import/mmsstv",
            json={"directory_path": str(tmp_path), "recursive": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 5
        assert data["skipped"] == 2
        assert data["errors"] == []
        assert data["total"] == 7

        mock_importer.import_directory.assert_called_once_with(
            directory=tmp_path,
            recursive=False,
        )

    def test_import_nonexistent_directory(self, mock_importer):
        """Should return 404 for a directory that doesn't exist."""
        response = client.post(
            "/api/v1/import/mmsstv",
            json={"directory_path": "/nonexistent/mmsstv/library"},
        )

        assert response.status_code == 404
        assert "Directory not found" in response.json()["detail"]
        mock_importer.import_directory.assert_not_called()

    def test_import_path_is_file(self, tmp_path, mock_importer):
        """Should return 400 when the path is a file, not a directory."""
        file_path = tmp_path / "image.jpg"
        file_path.write_bytes(b"not a directory")

        response = client.post(
            "/api/v1/import/mmsstv",
            json={"directory_path": str(file_path)},
        )

        assert response.status_code == 400
        assert "not a directory" in response.json()["detail"]
        mock_importer.import_directory.assert_not_called()

    def test_import_relative_path_rejected(self, mock_importer):
        """Should reject relative paths at validation (422)."""
        response = client.post(
            "/api/v1/import/mmsstv",
            json={"directory_path": "relative/path"},
        )

        assert response.status_code == 422

    def test_import_missing_directory_path(self, mock_importer):
        """Should reject a request with no directory_path."""
        response = client.post("/api/v1/import/mmsstv", json={})

        assert response.status_code == 422

    def test_import_failure_returns_500(self, tmp_path, mock_importer):
        """Should return 500 with error detail when the importer fails."""
        mock_importer.import_directory.side_effect = RuntimeError("disk exploded")

        response = client.post(
            "/api/v1/import/mmsstv",
            json={"directory_path": str(tmp_path)},
        )

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert "Import operation failed" in detail
        assert "disk exploded" in detail


class TestValidateDirectory:
    """Test POST /import/validate endpoint."""

    def test_validate_happy_path(self, tmp_path, mock_importer):
        """Should return validation result for a valid directory."""
        mock_importer.validate_directory.return_value = {
            "valid": True,
            "exists": True,
            "is_directory": True,
            "image_count": 12,
            "error": None,
        }

        response = client.post(
            "/api/v1/import/validate",
            json={"directory_path": str(tmp_path)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["exists"] is True
        assert data["is_directory"] is True
        assert data["image_count"] == 12
        assert data["error"] is None

    def test_validate_invalid_directory(self, mock_importer):
        """Should return valid=False with an error message (still 200)."""
        mock_importer.validate_directory.return_value = {
            "valid": False,
            "exists": False,
            "is_directory": False,
            "image_count": 0,
            "error": "Directory does not exist",
        }

        response = client.post(
            "/api/v1/import/validate",
            json={"directory_path": "/nonexistent/mmsstv/library"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error"] == "Directory does not exist"

    def test_validate_failure_returns_500(self, tmp_path, mock_importer):
        """Should return 500 with error detail when validation fails."""
        mock_importer.validate_directory.side_effect = RuntimeError("db gone")

        response = client.post(
            "/api/v1/import/validate",
            json={"directory_path": str(tmp_path)},
        )

        assert response.status_code == 500
        assert "Validation operation failed" in response.json()["detail"]


class TestImportPreview:
    """Test POST /import/preview endpoint."""

    def test_preview_happy_path(self, tmp_path, mock_importer):
        """Should return sample files and validation for a directory."""
        mock_importer.get_import_preview.return_value = {
            "total_files": 3,
            "samples": [
                {
                    "filename": "20240101_120000_ScottieS1_W1AW.jpg",
                    "path": str(tmp_path / "20240101_120000_ScottieS1_W1AW.jpg"),
                    "metadata": {"mode": "ScottieS1", "callsign": "W1AW"},
                },
            ],
            "validation": {
                "valid": True,
                "exists": True,
                "is_directory": True,
                "image_count": 3,
                "error": None,
            },
        }

        response = client.post(
            "/api/v1/import/preview",
            json={"directory_path": str(tmp_path)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 3
        assert len(data["samples"]) == 1
        sample = data["samples"][0]
        assert sample["filename"] == "20240101_120000_ScottieS1_W1AW.jpg"
        assert sample["metadata"]["callsign"] == "W1AW"
        assert data["validation"]["valid"] is True

        mock_importer.get_import_preview.assert_called_once_with(
            tmp_path,
            max_samples=10,
        )

    def test_preview_invalid_directory(self, mock_importer):
        """Should return empty preview with invalid validation (still 200)."""
        mock_importer.get_import_preview.return_value = {
            "total_files": 0,
            "samples": [],
            "validation": {
                "valid": False,
                "exists": False,
                "is_directory": False,
                "image_count": 0,
                "error": "Directory does not exist",
            },
        }

        response = client.post(
            "/api/v1/import/preview",
            json={"directory_path": "/nonexistent/mmsstv/library"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 0
        assert data["samples"] == []
        assert data["validation"]["valid"] is False

    def test_preview_failure_returns_500(self, tmp_path, mock_importer):
        """Should return 500 with error detail when preview fails."""
        mock_importer.get_import_preview.side_effect = RuntimeError("boom")

        response = client.post(
            "/api/v1/import/preview",
            json={"directory_path": str(tmp_path)},
        )

        assert response.status_code == 500
        assert "Preview operation failed" in response.json()["detail"]
