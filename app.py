"""Flask app: focused pixel-art palette extractor web app."""

from __future__ import annotations

import io
import os
import threading

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image

from extractor import extract_palette

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB upload limit
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-me")

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"}


def _is_allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "No image uploaded."}), 400

    if not _is_allowed(file.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    method = request.form.get("method", "kmeans").lower()
    if method not in ("kmeans", "median", "manual"):
        return jsonify({"error": "Invalid method."}), 400

    try:
        num_colors = int(request.form.get("num_colors", "16"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid color count."}), 400

    if method == "manual":
        # Manual picking is a purely client-side workflow (image sampling via
        # canvas); the server has no palette to return when asked directly.
        return jsonify(
            {
                "colors": [],
                "method": method,
                "count": 0,
                "filename": file.filename,
            }
        )

    try:
        image = Image.open(file.stream)
        image.load()
    except Exception:
        return jsonify({"error": "Could not read image."}), 400

    palette = extract_palette(image, method, num_colors)

    colors = [
        {
            "hex": "#{:02x}{:02x}{:02x}".format(*c),
            "rgb": list(c),
            "share": round(share * 100, 1),
        }
        for c, share in palette
    ]

    return jsonify(
        {
            "colors": colors,
            "method": method,
            "count": len(colors),
            "filename": file.filename,
        }
    )


@app.route("/export/<fmt>", methods=["POST"])
def export(fmt):
    data = request.get_json(silent=True)
    if not data or "colors" not in data:
        return jsonify({"error": "No palette provided."}), 400

    colors = []
    for c in data["colors"]:
        try:
            colors.append(tuple(int(x) for x in c["rgb"]))
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "Malformed color data."}), 400

    if fmt == "png":
        return _export_png(colors)
    if fmt == "gpl":
        return _export_gpl(colors)
    if fmt == "ase":
        return _export_ase(colors)

    return jsonify({"error": "Unsupported format."}), 400


def _export_png(colors) -> "response":
    n = len(colors)
    swatch_h = 48
    cell_w = 64
    img = Image.new("RGB", (cell_w * n, swatch_h), (255, 255, 255))
    px = img.load()
    for i, (r, g, b) in enumerate(colors):
        for x in range(i * cell_w, (i + 1) * cell_w):
            for y in range(swatch_h):
                px[x, y] = (r, g, b)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name="palette.png",
    )


def _export_gpl(colors) -> "response":
    lines = ["GIMP Palette", "Name: pixel-palette", "Columns: 8", "#"]
    for c in colors:
        lines.append(f"{c[0]:3d} {c[1]:3d} {c[2]:3d}\t#{c[0]:02x}{c[1]:02x}{c[2]:02x}")
    buf = io.BytesIO(("\n".join(lines) + "\n").encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        mimetype="text/plain",
        as_attachment=True,
        download_name="palette.gpl",
    )


def _export_ase(colors) -> "response":
    """Write an Adobe Swatch Exchange (.ase) file.

    Layout per Adobe's format / Cyotek reference:
      header: "ASEF" + u16 major(1) + u16 minor(0) + u32 block count
      per block: u16 type(0x0001 color), u32 length,
                 cstring name (UTF-16BE, null-terminated),
                 4 ascii bytes colorspace "RGB ",
                 3 x f32 components (0..1),
                 u16 color type (2 = normal).
    The block length covers everything after the u32 length field.
    """
    import struct

    out = io.BytesIO()

    def w16(v: int) -> None:
        out.write(v.to_bytes(2, "big"))

    def w32(v: int) -> None:
        out.write(v.to_bytes(4, "big"))

    def wf(v: float) -> None:
        out.write(struct.pack(">f", v))

    def write_name(name: str) -> None:
        w16(len(name) + 1)
        out.write(name.encode("utf-16-be"))
        out.write(b"\x00\x00")

    out.write(b"ASEF")
    w16(1)  # major
    w16(0)  # minor
    w32(len(colors))

    for r, g, b in colors:
        name = "#%02x%02x%02x" % (r, g, b)
        block_len = 2 + (len(name) + 1) * 2 + 4 + 12 + 2
        w16(0x0001)  # color entry
        w32(block_len)
        write_name(name)
        out.write(b"RGB ")
        wf(r / 255.0)
        wf(g / 255.0)
        wf(b / 255.0)
        w16(2)  # normal

    buf = io.BytesIO(out.getvalue())
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name="palette.ase",
    )


@app.route("/shutdown", methods=["POST"])
def shutdown():
    if not app.config.get("ENABLE_SHUTDOWN"):
        return jsonify({"error": "Shutdown not enabled."}), 403
    server = app.config.get("_server")
    if server is None:
        return jsonify({"error": "Server cannot shut itself down."}), 500
    threading.Timer(0.1, server.shutdown).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
