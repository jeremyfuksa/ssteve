"""
Unit tests for image gallery endpoints.

Tests GET /images and GET /images/{id} endpoints.
"""

import pytest
from uuid import uuid4
from datetime import datetime
from fastapi.testclient import TestClient

from sstv_core.api.main import app


client = TestClient(app)


class TestListImages:
    """Test GET /images endpoint."""

    def test_list_empty_gallery(self):
        """Should return empty list when no images."""
        response = client.get("/api/v1/images")

        assert response.status_code == 200
        data = response.json()

        assert "images" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        assert data["images"] == []
        assert data["total"] == 0

    def test_list_with_pagination(self):
        """Should respect pagination parameters."""
        response = client.get("/api/v1/images?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_pagination_limit_validation(self):
        """Should enforce limit constraints (1-100)."""
        # Too low
        response = client.get("/api/v1/images?limit=0")
        assert response.status_code == 422

        # Too high
        response = client.get("/api/v1/images?limit=101")
        assert response.status_code == 422

        # Valid
        response = client.get("/api/v1/images?limit=50")
        assert response.status_code == 200

    def test_filter_by_direction(self):
        """Should filter by direction (rx/tx)."""
        response = client.get("/api/v1/images?direction=rx")
        assert response.status_code == 200

        response = client.get("/api/v1/images?direction=tx")
        assert response.status_code == 200

    def test_filter_invalid_direction_rejected(self):
        """Should reject invalid direction."""
        response = client.get("/api/v1/images?direction=invalid")
        assert response.status_code == 422

    def test_filter_by_mode(self):
        """Should filter by SSTV mode."""
        response = client.get("/api/v1/images?mode=MartinM1")
        assert response.status_code == 200

    def test_filter_by_callsign(self):
        """Should filter by callsign."""
        response = client.get("/api/v1/images?callsign=W1AW")
        assert response.status_code == 200

    def test_combined_filters(self):
        """Should support multiple filters."""
        response = client.get(
            "/api/v1/images?direction=rx&mode=ScottieS1&callsign=N0CALL"
        )
        assert response.status_code == 200


class TestGetImage:
    """Test GET /images/{id} endpoint."""

    def test_get_nonexistent_image(self):
        """Should return 404 for nonexistent image."""
        fake_id = uuid4()
        response = client.get(f"/api/v1/images/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "IMAGE_NOT_FOUND"

    def test_get_invalid_uuid(self):
        """Should return 422 for invalid UUID."""
        response = client.get("/api/v1/images/not-a-uuid")
        assert response.status_code == 422
