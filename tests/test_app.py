"""Tests for the Flask routes and export writers in app.py."""

import io
import struct

import pytest
from PIL import Image


@pytest.fixture
def client():
    from app import app

    app.config.update(TESTING=True, ENABLE_SHUTDOWN=False)
    with app.test_client() as c:
        yield c


def _png_bytes(colors):
    """Build an in-memory PNG of stacked color bands."""
    total_rows = sum(h for _, h in colors)
    from PIL import Image

    import numpy as np

    arr = np.zeros((total_rows, 1, 3), dtype=np.uint8)
    row = 0
    for (r, g, b), h in colors:
        arr[row : row + h, 0, :] = (r, g, b)
        row += h
    img = Image.fromarray(arr, "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert b"Pixel Palette" in resp.data


def test_extract_no_file(client):
    resp = client.post("/extract")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_extract_disallowed_extension(client):
    data = {
        "image": (io.BytesIO(b"not an image"), "evil.exe"),
        "method": "kmeans",
        "num_colors": "16",
    }
    resp = client.post("/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "Unsupported" in resp.get_json()["error"]


def test_extract_invalid_method(client):
    data = {
        "image": (_png_bytes([((1, 2, 3), 4)]), "img.png"),
        "method": "bogus",
        "num_colors": "16",
    }
    resp = client.post("/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "Invalid method" in resp.get_json()["error"]


def test_extract_invalid_num_colors(client):
    data = {
        "image": (_png_bytes([((1, 2, 3), 4)]), "img.png"),
        "method": "kmeans",
        "num_colors": "abc",
    }
    resp = client.post("/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "Invalid color count" in resp.get_json()["error"]


def test_extract_garbage_image(client):
    data = {
        "image": (io.BytesIO(b"this is definitely not a valid image"), "img.png"),
        "method": "kmeans",
        "num_colors": "16",
    }
    resp = client.post("/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "Could not read image" in resp.get_json()["error"]


def test_extract_manual_returns_empty(client):
    data = {
        "image": (_png_bytes([((10, 20, 30), 4)]), "img.png"),
        "method": "manual",
        "num_colors": "16",
    }
    resp = client.post("/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["colors"] == []
    assert body["count"] == 0


@pytest.mark.parametrize("method", ["kmeans", "median"])
def test_extract_happy_path(client, method):
    colors = [
        ((255, 0, 0), 4),
        ((0, 255, 0), 2),
        ((0, 0, 255), 1),
    ]
    data = {
        "image": (_png_bytes(colors), "img.png"),
        "method": method,
        "num_colors": "3",
    }
    resp = client.post("/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 3
    assert body["method"] == method
    assert body["filename"] == "img.png"
    for color in body["colors"]:
        assert set(color.keys()) == {"hex", "rgb", "share"}
        assert color["hex"].startswith("#")
        assert len(color["rgb"]) == 3
    # Shares are percentages that sum to ~100 for an exact palette.
    assert sum(c["share"] for c in body["colors"]) == pytest.approx(100.0, abs=0.1)
    # Dominant color should lead the list.
    assert body["colors"][0]["rgb"] == [255, 0, 0]


def test_export_png(client):
    colors = [{"rgb": [255, 0, 0]}, {"rgb": [0, 255, 0]}, {"rgb": [0, 0, 255]}]
    resp = client.post("/export/png", json={"colors": colors})
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"

    img = Image.open(io.BytesIO(resp.data))
    assert img.size == (64 * 3, 48)
    # Corner pixel of the first swatch is red.
    assert img.getpixel((0, 0)) == (255, 0, 0)


def test_export_gpl(client):
    colors = [{"rgb": [255, 0, 0]}, {"rgb": [0, 255, 0]}]
    resp = client.post("/export/gpl", json={"colors": colors})
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"

    text = resp.get_data(as_text=True)
    assert text.startswith("GIMP Palette")
    assert "255   0   0" in text
    assert "ff0000" in text


def test_export_ase(client):
    colors = [{"rgb": [255, 0, 0]}, {"rgb": [0, 128, 255]}]
    resp = client.post("/export/ase", json={"colors": colors})
    assert resp.status_code == 200

    data = resp.data
    assert data[:4] == b"ASEF"
    major, minor, count = struct.unpack(">HHI", data[4:12])
    assert major == 1
    assert minor == 0
    assert count == 2

    # Header block count matches the number of color blocks present.
    assert data[12:14] == struct.pack(">H", 0x0001)  # a color block follows


def test_export_unsupported_format(client):
    resp = client.post("/export/xyz", json={"colors": [{"rgb": [1, 2, 3]}]})
    assert resp.status_code == 400
    assert "Unsupported format" in resp.get_json()["error"]


def test_export_missing_colors(client):
    resp = client.post("/export/png", json={})
    assert resp.status_code == 400
    assert "No palette" in resp.get_json()["error"]


def test_export_malformed_color(client):
    resp = client.post("/export/png", json={"colors": [{"rgb": ["bad"]}]})
    assert resp.status_code == 400
    assert "Malformed color data" in resp.get_json()["error"]


def test_shutdown_disabled_returns_403(client):
    # Default config has no ENABLE_SHUTDOWN, so this must be refused,
    # ensuring tests never kill a running server.
    resp = client.post("/shutdown")
    assert resp.status_code == 403
