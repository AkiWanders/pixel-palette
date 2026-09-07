"""Tests for the palette extraction algorithms in extractor.py."""

import numpy as np
import pytest
from PIL import Image

from extractor import (
    MAX_SAMPLES,
    _load_samples,
    extract_palette,
)


def image_of(bands):
    """Build an RGB image from a list of (color, height) bands stacked VERTICALLY.

    bands: list of (rgb, pixel_count). The image width is fixed at one pixel,
    so each band contributes that many rows -> the total pixel count equals the
    sum of band heights, and the pixel distribution per color is exact.
    """
    total_rows = sum(h for _, h in bands)
    arr = np.zeros((total_rows, 1, 3), dtype=np.uint8)
    row = 0
    for (r, g, b), h in bands:
        arr[row : row + h, 0, :] = (r, g, b)
        row += h
    return Image.fromarray(arr, "RGB")


@pytest.mark.parametrize(
    "method", ["kmeans", "median"]
)
def test_short_circuit_returns_exact_unique_colors(method):
    # 3 unique colors, asking for 3 -> exact colors returned by frequency.
    img = image_of([((255, 0, 0), 4), ((0, 255, 0), 2), ((0, 0, 255), 1)])

    palette = extract_palette(img, method, 3)

    colors = [c for c, _ in palette]
    assert colors == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    shares = [s for _, s in palette]
    assert shares == [4 / 7, 2 / 7, 1 / 7]


def test_short_circuit_counts_real_pixels_not_samples():
    # With <= num_colors unique colors, counts come from the whole image,
    # not the (downsampled) sample set.
    colors = [((i, i, i), 1) for i in range(3)]
    img = image_of(colors)

    palette = extract_palette(img, "kmeans", 3)

    assert sum(s for _, s in palette) == pytest.approx(1.0)


def test_padding_when_requesting_more_than_unique():
    # 2 unique colors but ask for 4 -> padded with cloned colors, share 0.
    img = image_of([((200, 100, 50), 3), ((10, 20, 30), 1)])

    palette = extract_palette(img, "median", 4)

    assert len(palette) == 4
    colors = [c for c, _ in palette]
    assert colors[0] == (200, 100, 50)  # dominant first (3 px)
    assert colors[1] == (10, 20, 30)
    # Padded entries reuse the palette cyclically with zero share.
    assert colors[2] in ((10, 20, 30), (200, 100, 50))
    assert colors[3] in ((10, 20, 30), (200, 100, 50))
    assert palette[2][1] == 0.0
    assert palette[3][1] == 0.0


def test_pad_black_when_palette_empty():
    from extractor import _pad_with_shares

    result = _pad_with_shares([], [], 3)
    assert len(result) == 3
    assert all(c == (0, 0, 0) for c, _ in result)
    assert all(s == 0.0 for _, s in result)


def test_num_colors_clamped_low():
    img = image_of([((1, 2, 3), 5), ((9, 8, 7), 5)])
    palette = extract_palette(img, "median", 1)  # below min 2
    assert len(palette) == 2


def test_num_colors_clamped_high():
    img = image_of([((i, 0, 0), 1) for i in range(0, 90, 3)])  # 30 unique colors
    palette = extract_palette(img, "median", 1000)  # above max 64
    assert len(palette) == 64


def test_output_out_of_bounds_has_required_shape():
    # A noisy image forces the clustering path (unique_count > num_colors).
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")

    for method in ("kmeans", "median"):
        palette = extract_palette(img, method, 8)
        assert len(palette) == 8
        for c, share in palette:
            for ch in c:
                assert 0 <= ch <= 255
            assert 0.0 <= share <= 1.0


def test_median_is_deterministic():
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, size=(24, 24, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")

    a = extract_palette(img, "median", 6)
    b = extract_palette(img, "median", 6)

    assert a == b


def test_kmeans_returns_exact_count_and_range():
    rng = np.random.default_rng(7)
    arr = rng.integers(0, 256, size=(20, 20, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")

    palette = extract_palette(img, "kmeans", 5)

    assert len(palette) == 5
    for c, _ in palette:
        assert all(0 <= ch <= 255 for ch in c)


def test_load_samples_counts_exact():
    # Verify _load_samples counts pixels correctly (including downsampling).
    colors = [((255, 0, 0), 3), ((0, 255, 0), 2)]
    img = image_of(colors[:1] * 1)  # 3 px of red only

    samples, counts, unique_count, total = _load_samples(img)
    assert total == 3
    assert unique_count == 1
    assert counts == {(255, 0, 0): 3}


def test_load_samples_downsampled_when_huge():
    # Build an image larger than the sample cap and confirm sampling kicks in.
    # The sample cap is passed explicitly (the extractor's default is bound at
    # definition time, so monkeypatching the module constant would not apply).
    arr = np.zeros((20, 10, 3), dtype=np.uint8)  # 200 px > 100
    arr[:, :, 0] = np.arange(10)
    img = Image.fromarray(arr, "RGB")

    samples, counts, unique_count, total = _load_samples(img, max_samples=100)
    assert total == 200
    assert samples.shape[0] == 100  # downsampled to the cap
    assert unique_count == 10  # counts still reflect full image
    # Each distinct red level appears exactly 20 times in the full image.
    assert all(n == 20 for n in counts.values())
