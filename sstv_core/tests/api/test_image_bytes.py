"""Serving image bytes and thumbnails (#54).

The gallery, the canvas and the thumbnail strip all need to display a
picture, and until now nothing could: `api/routes/images.py` had two JSON
metadata GETs, `thumbnail_path` was a declared field nothing ever wrote,
and `filepath` handed clients an absolute local path -- useless to a
webview and a needless disclosure of the operator's directory layout.

Storage stays filesystem-native. This is about serving bytes that already
exist on disk, never about putting them in the database.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _write_image(path: Path, size: tuple[int, int] = (320, 256)) -> Path:
    """A picture with structure, so a resize can be told from a blank."""
    rng = np.random.default_rng(0)
    data = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(data).save(path)
    return path


class TestThumbnailGeneration:
    def test_a_thumbnail_is_written_beside_the_image(self, tmp_path: Path) -> None:
        from sstv_core.api.thumbnails import generate_thumbnail

        source = _write_image(tmp_path / "rx.png")
        thumb = generate_thumbnail(source)

        assert thumb is not None
        assert thumb.exists()
        assert thumb != source

    def test_the_thumbnail_is_smaller_than_the_original(self, tmp_path: Path) -> None:
        from sstv_core.api.thumbnails import THUMBNAIL_MAX_PX, generate_thumbnail

        source = _write_image(tmp_path / "rx.png", size=(640, 496))
        thumb = generate_thumbnail(source)

        assert thumb is not None
        with Image.open(thumb) as img:
            assert max(img.size) <= THUMBNAIL_MAX_PX

    def test_aspect_ratio_survives(self, tmp_path: Path) -> None:
        """SSTV modes are not square. A stretched thumbnail misrepresents
        the picture in the one view an operator scans quickly."""
        from sstv_core.api.thumbnails import generate_thumbnail

        source = _write_image(tmp_path / "rx.png", size=(320, 256))
        thumb = generate_thumbnail(source)

        assert thumb is not None
        with Image.open(thumb) as img:
            assert img.size[0] / img.size[1] == pytest.approx(320 / 256, abs=0.05)

    def test_an_image_smaller_than_the_cap_is_not_upscaled(
        self, tmp_path: Path
    ) -> None:
        """Blowing a Robot 36 up to 512 px would invent detail."""
        from sstv_core.api.thumbnails import generate_thumbnail

        source = _write_image(tmp_path / "small.png", size=(160, 120))
        thumb = generate_thumbnail(source)

        assert thumb is not None
        with Image.open(thumb) as img:
            assert img.size == (160, 120)

    def test_a_missing_source_returns_none_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        """A decode that saved nothing must not fail on its thumbnail."""
        from sstv_core.api.thumbnails import generate_thumbnail

        assert generate_thumbnail(tmp_path / "nope.png") is None

    def test_a_corrupt_source_returns_none(self, tmp_path: Path) -> None:
        from sstv_core.api.thumbnails import generate_thumbnail

        broken = tmp_path / "broken.png"
        broken.write_bytes(b"this is not a PNG")

        assert generate_thumbnail(broken) is None

    def test_regenerating_is_idempotent(self, tmp_path: Path) -> None:
        from sstv_core.api.thumbnails import generate_thumbnail

        source = _write_image(tmp_path / "rx.png")
        first = generate_thumbnail(source)
        second = generate_thumbnail(source)

        assert first == second


class TestServingBytes:
    """The endpoints the gallery and canvas actually fetch."""

    @staticmethod
    def _client():
        """Drive the assembled app.

        `routes/images.py` cannot be imported on its own -- it imports
        `api.main` for `get_db_session` and `api.main` imports it back.
        That cycle predates this change, and a client request is what
        the endpoints exist to answer anyway.
        """
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        return TestClient(app)

    def test_the_file_endpoint_answers(self) -> None:
        """404 for an unknown id, not 405 or 404-because-no-such-route.

        A missing route and a missing image both look like 404 from the
        status alone, so this asserts the endpoint exists by checking it
        rejects the *method* it does not serve.
        """
        from uuid import uuid4

        response = self._client().post(f"/api/v1/images/{uuid4()}/file")

        assert response.status_code == 405, (
            "no endpoint serves image bytes, so nothing can display a picture"
        )

    def test_the_thumbnail_endpoint_answers(self) -> None:
        from uuid import uuid4

        response = self._client().post(f"/api/v1/images/{uuid4()}/thumbnail")

        assert response.status_code == 405

    def test_an_unknown_id_is_404_not_500(self) -> None:
        from uuid import uuid4

        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        client = TestClient(app)
        response = client.get(f"/api/v1/images/{uuid4()}/file")

        assert response.status_code == 404


class TestPathsDoNotLeak:
    """`filepath` is an absolute local path.

    A webview client cannot use it, and shipping it discloses the
    operator's directory layout for no benefit. The URL a client can
    actually fetch is what belongs in the response.
    """

    def test_metadata_offers_fetchable_urls(self) -> None:
        from sstv_core.api.models import ImageMetadata

        fields = ImageMetadata.model_fields
        assert "url" in fields, (
            "clients get an absolute filesystem path and no URL, so they "
            "cannot display the image they were just told about"
        )
        assert "thumbnail_url" in fields


class TestPathTraversal:
    """An image row's filepath decides what bytes get served.

    Anything that lets a caller steer that outside the library turns an
    image endpoint into a file-read primitive.
    """

    def test_a_path_outside_the_library_is_refused(self, tmp_path: Path) -> None:
        from sstv_core.api.thumbnails import is_servable

        library = tmp_path / "images"
        library.mkdir()
        inside = _write_image(library / "ok.png")
        outside = _write_image(tmp_path / "secret.png")

        assert is_servable(inside, [library]) is True
        assert is_servable(outside, [library]) is False

    def test_a_traversal_path_is_refused(self, tmp_path: Path) -> None:
        from sstv_core.api.thumbnails import is_servable

        library = tmp_path / "images"
        library.mkdir()

        assert is_servable(library / ".." / "secret.png", [library]) is False

    def test_a_symlink_out_of_the_library_is_refused(self, tmp_path: Path) -> None:
        """resolve() before comparing, or a symlink walks straight out."""
        from sstv_core.api.thumbnails import is_servable

        library = tmp_path / "images"
        library.mkdir()
        outside = _write_image(tmp_path / "secret.png")
        link = library / "sneaky.png"
        link.symlink_to(outside)

        assert is_servable(link, [library]) is False


class TestTheGuardFailsClosed:
    """An unreadable config must refuse, not serve everything.

    The first version of `_library_roots` swallowed its failure and
    returned an empty list, and the check read `if roots and not
    is_servable(...)` -- so a config that would not load skipped the path
    check on every request. mypy caught the call that would have failed
    (ConfigManager takes a session), which is the only reason it was
    found: every test here exercised `is_servable` directly rather than
    through the route.
    """

    def test_roots_returns_none_when_config_is_unreadable(self) -> None:
        from unittest.mock import patch

        from sstv_core.api.routes import images

        with patch.object(
            images, "Session", side_effect=RuntimeError("no database")
        ):
            with patch(
                "sstv_core.config.manager.ConfigManager",
                side_effect=RuntimeError("no config"),
            ):
                assert images._library_roots(None) is None  # type: ignore[arg-type]

    def test_none_roots_means_refuse(self) -> None:
        """The caller's contract: None is 'refuse', never 'allow all'."""
        import inspect

        from sstv_core.api.routes import images

        source = inspect.getsource(images._serve)

        assert "roots is None or not is_servable" in source, (
            "the guard must refuse when the roots are unknown -- an empty "
            "list read as 'no restriction' is a guard that fails open"
        )
