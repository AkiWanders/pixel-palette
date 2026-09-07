# Pixel Palette

A focused, single-page **pixel-art palette extractor** web app. Upload an image,
pick an extraction method and color count, then edit and export the resulting
palette.

Built with a Flask + Pillow + NumPy + scikit-learn backend and a hand-written
vanilla JS/CSS frontend (no bundler or framework).

## Features

- **Drag-and-drop / browse** image upload with a zoomable, pixelated preview.
- **Three methods**:
  - **K-means** clustering (scikit-learn)
  - **Median cut** (pure Python)
  - **Manual** — click pixels to build a palette by hand
- **Palette editing**: select a color, then click-and-drag on the image to
  retarget it; copy, type, or color-pick a swatch; add and remove colors.
- **Exports**: PNG swatch strip, GPL (GIMP), and ASE (Adobe Swatch Exchange).
- Dark/light theme, responsive layout, and a "Close app" button that shuts the
  server down.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Flask 3, Pillow, NumPy, scikit-learn |
| Frontend | Vanilla JS (ES6) + hand-written CSS |
| Runtime | Python 3.14 (see `requirements.txt`) |

## Setup

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run

```bash
./launch.sh
```

or

```bash
./venv/bin/python run_app.py
```

The server runs on `127.0.0.1:5000` and auto-opens your browser. If an instance
is already running, the launcher just opens the browser to it.

## Usage

1. Drop or browse an image.
2. Choose **K-means**, **Median cut**, or **Manual**.
3. Set the desired color count (`2–48`).
4. Click **Extract palette**.
5. Edit colors (select → drag on image, click hex to copy, double-click to
   type, use the color picker, add/remove).
6. Export as **PNG**, **GPL**, or **ASE**.

## Tests

```bash
./venv/bin/python -m pytest -q
```

Covers the extraction algorithms in `extractor.py` and the HTTP routes and
export writers in `app.py`.

## Project layout

```
app.py          Flask routes + export writers
extractor.py    Palette extraction algorithms (kmeans / median cut)
run_app.py      Standalone launcher (Werkzeug server + auto-open browser)
launch.sh       Double-click launch script
templates/      index.html (single-page UI)
static/         app.js + style.css
tests/          pytest suite
```
