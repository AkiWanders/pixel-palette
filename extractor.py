"""Pixel art palette extraction algorithms.

Two methods are provided:
  * K-means clustering (uses scikit-learn)
  * Median cut (pure Python, no extra deps)

extract_palette returns a list of (color, share) pairs where color is an
(r, g, b) tuple and share is that color's dominance as a fraction of the
image's pixels (0..1). Results are ordered by dominance, descending.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

Color = Tuple[int, int, int]
PalettedColor = Tuple[Color, float]

MAX_SAMPLES = 200_000


def _load_samples(image, max_samples: int = MAX_SAMPLES):
    """Return downsampled pixel samples plus true per-color pixel counts.

    Returns (samples, counts, unique_count, total_pixels) where:
      * samples is numpy array (N, 3) of pixels, downsampled if huge.
      * counts maps each unique color (as a plain int triple) to the number
        of image pixels that have exactly that color.
      * unique_count is the number of distinct colors in the image.
      * total_pixels is the raw pixel count (shape h*w).
    """
    img = image.convert("RGB")
    arr = np.array(img)
    h, w, _ = arr.shape
    total = h * w
    flat = arr.reshape(total, 3)

    unique, counts_arr = np.unique(flat, axis=0, return_counts=True)
    counts = {tuple(map(int, c)): int(n) for c, n in zip(unique, counts_arr)}
    unique_count = len(counts)

    samples = flat
    if total > max_samples:
        rng = np.random.default_rng(0)
        idx = rng.choice(total, size=max_samples, replace=False)
        samples = flat[idx]

    return samples, counts, unique_count, total


def extract_palette(image, method: str, num_colors: int) -> List[PalettedColor]:
    """Extract a palette from a PIL image.

    Args:
        image: PIL.Image instance.
        method: "kmeans" or "median".
        num_colors: desired number of colors (clamped to 2..64).

    Returns a list of (color, share) pairs ordered by dominance, padded to
    exactly num_colors entries (padding carries a zero share).
    """
    method = method.lower()
    num_colors = max(2, min(64, int(num_colors)))

    samples, counts, unique_count, total = _load_samples(image)

    if unique_count <= num_colors:
        # Image already qualifies as a palette: return unique colors
        # ordered by real pixel frequency.
        ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        palette = [c for c, _ in ordered]
        shares = [n / total for _, n in ordered]
        return _pad_with_shares(palette, shares, num_colors)

    if method == "median":
        palette = _median_cut(samples, num_colors)
    else:
        palette = _kmeans(samples, num_colors)

    ordered, shares = _order_by_dominance(palette, samples)

    return _pad_with_shares(ordered, shares, num_colors)


def _order_by_dominance(
    palette: List[Color], samples: np.ndarray
) -> Tuple[List[Color], List[float]]:
    """Assign every sample pixel to its nearest palette color and rank by count."""
    arr = np.asarray(palette, dtype=np.float64)
    diff = samples[:, None, :].astype(np.float64) - arr[None, :, :]
    dist = np.einsum("ijk,ijk->ij", diff, diff)
    nearest = np.argmin(dist, axis=1)

    counts = np.bincount(nearest, minlength=len(palette)) / len(samples)
    order = np.argsort(-counts)
    ordered = [(tuple(map(int, arr[i]))) for i in order]
    shares = [float(counts[i]) for i in order]
    return ordered, shares


def _pad_with_shares(
    palette: List[Color], shares: List[float], num_colors: int
) -> List[PalettedColor]:
    """Return exactly num_colors (color, share) pairs; padding share = 0."""
    result = list(zip(palette, shares))
    if len(result) >= num_colors:
        return result[:num_colors]
    for i in range(num_colors - len(result)):
        if palette:
            clone = palette[i % len(palette)]
        else:
            clone = (0, 0, 0)
        result.append((clone, 0.0))
    return result


def _kmeans(samples, num_colors: int) -> List[Color]:
    """Cluster pixels into num_colors groups via K-means."""
    from sklearn.cluster import KMeans

    kmeans = KMeans(
        n_clusters=num_colors,
        init="k-means++",
        n_init=10,
        max_iter=300,
        random_state=0,
    )
    kmeans.fit(samples)
    return [tuple(int(round(v)) for v in center) for center in kmeans.cluster_centers_]


def _bucket_volume(bucket) -> int:
    """Volume of the axis-aligned bounding box of the bucket's colors."""
    r = max(c[0] for c in bucket) - min(c[0] for c in bucket)
    g = max(c[1] for c in bucket) - min(c[1] for c in bucket)
    b = max(c[2] for c in bucket) - min(c[2] for c in bucket)
    return r + g + b


def _median_cut(samples, num_colors: int) -> List[Color]:
    """Recursively split pixel buckets by the channel with largest range."""
    buckets: List[List[Color]] = [
        [(int(r), int(g), int(b)) for r, g, b in samples]
    ]

    while len(buckets) < num_colors:
        bucket = max(buckets, key=_bucket_volume)
        buckets.remove(bucket)

        if len(bucket) < 2:
            # Cannot split further: duplicate so we never infinite-loop.
            buckets.append(list(bucket))
            buckets.append(list(bucket))
            continue

        channel = _widest_channel(bucket)
        bucket.sort(key=lambda c: c[channel])
        mid = len(bucket) // 2
        buckets.append(bucket[:mid])
        buckets.append(bucket[mid:])

    return [_average(b) for b in buckets]


def _widest_channel(bucket) -> int:
    r = max(c[0] for c in bucket) - min(c[0] for c in bucket)
    g = max(c[1] for c in bucket) - min(c[1] for c in bucket)
    b = max(c[2] for c in bucket) - min(c[2] for c in bucket)
    ranges = (r, g, b)
    return max(range(3), key=ranges.__getitem__)


def _average(bucket) -> Color:
    n = len(bucket)
    return (
        sum(c[0] for c in bucket) // n,
        sum(c[1] for c in bucket) // n,
        sum(c[2] for c in bucket) // n,
    )