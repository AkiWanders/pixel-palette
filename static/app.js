(() => {
  "use strict";

  /* ============================== elements ============================== */

  const fileInput = document.getElementById("file-input");
  const dropZone = document.getElementById("drop-zone");
  const browseBtn = document.getElementById("browse-btn");
  const previewWrap = document.getElementById("preview-wrap");
  const previewName = document.getElementById("preview-name");
  const canvas = document.getElementById("preview-canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const resetBtn = document.getElementById("reset-btn");
  const pickReadout = document.getElementById("pick-readout");
  const pickSwatch = document.getElementById("pick-swatch");
  const pickHex = document.getElementById("pick-hex");
  const pickHint = document.getElementById("pick-hint");
  const zoomControls = document.getElementById("zoom-controls");
  const zoomPct = document.getElementById("zoom-pct");
  const zoomOutBtn = document.getElementById("zoom-out");
  const zoomInBtn = document.getElementById("zoom-in");
  const zoomFitBtn = document.getElementById("zoom-fit");

  const methodBtns = document.querySelectorAll(".seg-btn");
  const numColors = document.getElementById("num-colors");
  const colorCount = document.getElementById("color-count");
  const colorsGroup = document.getElementById("colors-group");
  const extractBtn = document.getElementById("extract-btn");
  const manualHint = document.getElementById("manual-hint");
  const addBtn = document.getElementById("add-btn");

  const results = document.getElementById("results");
  const resultsTitle = document.getElementById("results-title");
  const outputSubtle = document.getElementById("output-subtle");
  const colorList = document.getElementById("color-list");
  const copiedNote = document.getElementById("copied-note");
  const errorBox = document.getElementById("error");
  const stripTemplate = document.getElementById("color-strip-template");

  /* ============================== state ============================== */

  const state = {
    file: null,
    img: null,
    imgW: 0,
    imgH: 0,
    method: "kmeans",
    palette: [], // {hex, rgb:[r,g,b], share}
    target: null, // index into palette being retargeted via image pick
    zoom: 1, // 1 = Fit; range 0.2 .. 4
    fitScale: 1,
    copiedTimer: null,
    inFlight: false,
  };

  let scrubActive = false; // pointer is down and dragging over the image

  const MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace";

  /* ============================== helpers ============================== */

  const hexOf = (rgb) =>
    "#" + rgb.map((v) => v.toString(16).padStart(2, "0")).join("");

  const rgbOf = (hex) => {
    const v = hex.replace("#", "");
    if (v.length === 3) return [0, 1, 2].map((i) => parseInt(v[i] + v[i], 16));
    return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16));
  };

  const luminance = ([r, g, b]) =>
    (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;

  const stripTextColor = (rgb) => (luminance(rgb) < 0.5 ? "#ffffff" : "#14161a");

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
  }
  function hideError() {
    errorBox.hidden = true;
  }

  function setPickHint(text) {
    pickHint.hidden = !text;
    pickHint.textContent = text || "";
  }

  /* ============================== theme ============================== */

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    root.dataset.theme = root.dataset.theme === "light" ? "" : "light";
  });

  /* ============================== close app ============================== */

  document.getElementById("close-btn").addEventListener("click", async () => {
    try {
      await fetch("/shutdown", { method: "POST" });
    } catch {
      /* server already gone; close the tab anyway */
    }
    window.close();
  });

  /* ============================== upload ============================== */

  function setFile(file) {
    if (!file || !file.type.startsWith("image/")) {
      showError("Please choose a valid image file.");
      return;
    }
    state.file = file;
    hideError();
    const reader = new FileReader();
    reader.onload = (e) => decodeImage(e.target.result, file.name);
    reader.readAsDataURL(file);
  }

  function decodeImage(dataUrl, name) {
    const img = new Image();
    img.onload = () => {
      state.img = img;
      state.imgW = img.naturalWidth;
      state.imgH = img.naturalHeight;
      canvas.width = state.imgW;
      canvas.height = state.imgH;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, 0, 0);

      previewName.textContent = `${name} · ${state.imgW}×${state.imgH}`;
      dropZone.hidden = true;
      previewWrap.hidden = false;
      zoomControls.hidden = false;
      state.zoom = 1;
      fitCanvas();

      resetPalette();
      if (state.method === "manual") {
        refreshToolbar();
      } else {
        extract();
      }
    };
    img.onerror = () => showError("Could not decode the image.");
    img.src = dataUrl;
  }

  function fitCanvas() {
    if (!state.img) return;
    const stage = document.getElementById("preview-stage");
    const availW = Math.max(stage.clientWidth - 4, 40);
    const availH = Math.max(stage.clientHeight - 4, 40);
    state.fitScale = Math.min(availW / state.imgW, availH / state.imgH);
    applySize();
  }

  function applySize() {
    if (!state.img) return;
    const w = Math.max(1, Math.round(state.imgW * state.fitScale * state.zoom));
    const h = Math.max(1, Math.round(state.imgH * state.fitScale * state.zoom));
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    zoomPct.textContent = `${Math.round(state.zoom * 100)}%`;
  }

  function setZoom(z, clientX, clientY) {
    const stage = document.getElementById("preview-stage");
    if (clientX === undefined || clientY === undefined) {
      const rect = stage.getBoundingClientRect();
      clientX = rect.left + stage.clientWidth / 2;
      clientY = rect.top + stage.clientHeight / 2;
    }
    const zoom = Math.min(4, Math.max(0.2, z));
    if (zoom === state.zoom) return;

    const sRect = stage.getBoundingClientRect();
    const cRect = canvas.getBoundingClientRect();
    const viewX = clientX - sRect.left;
    const viewY = clientY - sRect.top;
    const ux = Math.min(1, Math.max(0, (viewX - (cRect.left - sRect.left)) / cRect.width));
    const uy = Math.min(1, Math.max(0, (viewY - (cRect.top - sRect.top)) / cRect.height));

    state.zoom = zoom;
    applySize();

    const nLeft = canvas.offsetLeft;
    const nTop = canvas.offsetTop;
    stage.scrollLeft = nLeft + ux * canvas.clientWidth - viewX;
    stage.scrollTop = nTop + uy * canvas.clientHeight - viewY;
  }

  zoomInBtn.addEventListener("click", () => setZoom(state.zoom * 1.25));
  zoomOutBtn.addEventListener("click", () => setZoom(state.zoom / 1.25));
  zoomFitBtn.addEventListener("click", () => setZoom(1));

  canvas.addEventListener(
    "wheel",
    (e) => {
      if (!state.img) return;
      e.preventDefault();
      setZoom(e.deltaY < 0 ? state.zoom * 1.25 : state.zoom / 1.25, e.clientX, e.clientY);
    },
    { passive: false }
  );

  new ResizeObserver(fitCanvas).observe(previewWrap);
  window.addEventListener("resize", fitCanvas);

  function reset() {
    state.file = null;
    state.img = null;
    state.target = null;
    state.palette = [];
    state.zoom = 1;
    previewImgReset();
    dropZone.hidden = false;
    previewWrap.hidden = true;
    zoomControls.hidden = true;
    results.hidden = true;
    canvas.style.width = "";
    canvas.style.height = "";
    setPickHint("");
    pickReadout.hidden = true;
    scrubActive = false;
    fileInput.value = "";
    hideError();
  }

  function previewImgReset() {
    canvas.width = 0;
    canvas.height = 0;
  }

  browseBtn.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) setFile(e.target.files[0]);
  });
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });
  resetBtn.addEventListener("click", reset);

  /* ============================== eyedropper ============================== */

  function pixelAt(e) {
    const rect = canvas.getBoundingClientRect();
    const px = Math.min(
      state.imgW - 1,
      Math.max(0, Math.floor(((e.clientX - rect.left) / rect.width) * state.imgW))
    );
    const py = Math.min(
      state.imgH - 1,
      Math.max(0, Math.floor(((e.clientY - rect.top) / rect.height) * state.imgH))
    );
    const d = ctx.getImageData(px, py, 1, 1).data;
    return [d[0], d[1], d[2]];
  }

  function showReadout(e, rgb) {
    pickSwatch.style.background = hexOf(rgb);
    pickHex.textContent = hexOf(rgb);
    pickReadout.style.left = `${Math.min(e.clientX + 16, window.innerWidth - 150)}px`;
    pickReadout.style.top = `${e.clientY}px`;
    pickReadout.hidden = false;
  }

  canvas.addEventListener("pointermove", (e) => {
    if (!state.img) return;
    const rgb = pixelAt(e);
    if (scrubActive && state.target !== null) {
      state.palette[state.target].rgb = rgb.slice();
      state.palette[state.target].hex = hexOf(rgb);
      renderStrip(state.target);
    }
    showReadout(e, rgb);
  });

  canvas.addEventListener("pointerleave", () => {
    if (!scrubActive) pickReadout.hidden = true;
  });

  canvas.addEventListener("pointerdown", (e) => {
    if (!state.img) return;
    scrubActive = true;
    try {
      canvas.setPointerCapture(e.pointerId);
    } catch {}
    showReadout(e, pixelAt(e));
  });

  canvas.addEventListener("pointerup", (e) => {
    if (!scrubActive) return;
    scrubActive = false;
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch {}
    applyPick(pixelAt(e));
  });

  canvas.addEventListener("pointercancel", (e) => {
    if (!scrubActive) return;
    scrubActive = false;
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch {}
    pickReadout.hidden = true;
  });

  function applyPick(rgb) {
    if (state.target !== null) {
      const idx = state.target;
      state.palette[idx].rgb = rgb.slice();
      state.palette[idx].hex = hexOf(rgb);
      renderPalette();
      refreshTargetHint();
    } else {
      state.palette.push({ hex: hexOf(rgb), rgb, share: 0 });
      renderPalette();
    }
  }

  /* ============================== palette model ============================== */

  function updateColor(index, rgb) {
    state.palette[index].rgb = rgb.slice();
    state.palette[index].hex = hexOf(rgb);
    renderPalette();
  }

  function renderStrip(i) {
    const color = state.palette[i];
    if (!color) return;
    const swatch = colorList.querySelector(`.swatch[data-index="${i}"]`);
    if (!swatch) return;
    swatch.style.background = color.hex;
    const hexLabel = swatch.querySelector(".hex-label");
    hexLabel.textContent = color.hex;
    hexLabel.style.color = stripTextColor(color.rgb);
    swatch.querySelector(".native-color").value = color.hex;
  }

  function removeColor(index) {
    state.palette.splice(index, 1);
    if (state.target === index) state.target = null;
    else if (state.target !== null && state.target > index) state.target -= 1;
    renderPalette();
  }

  function clearTarget() {
    state.target = null;
    renderTargetOnly();
  }

  function resetPalette() {
    state.palette = [];
    state.target = null;
    results.hidden = true;
    colorList.innerHTML = "";
  }

  /* ============================== controls ============================== */

  methodBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      methodBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const next = btn.dataset.method;
      if (next === state.method) return;
      state.method = next;
      if (next === "manual") {
        enterManual();
      } else {
        leaveManual();
        if (state.img) extract();
      }
    });
  });

  function enterManual() {
    togglesForMethod("manual");
    resetPalette();
    clearTarget();
    refreshTargetHint();
    extractBtn.disabled = true;
    extractBtn.textContent = "Manual picking";
  }

  function leaveManual() {
    togglesForMethod(state.method);
    refreshTargetHint();
  }

  function togglesForMethod(method) {
    const manual = method === "manual";
    colorsGroup.hidden = manual;
    extractBtn.hidden = manual;
    manualHint.hidden = !manual;
  }

  numColors.addEventListener("input", () => {
    colorCount.textContent = numColors.value;
    const pct = ((numColors.value - numColors.min) /
      (numColors.max - numColors.min)) * 100;
    numColors.style.setProperty("--fill", `${pct}%`);
  });

  async function extract() {
    if (!state.file || state.method === "manual" || state.inFlight) return;

    hideError();
    state.inFlight = true;
    extractBtn.disabled = true;
    extractBtn.textContent = "Extracting…";

    const form = new FormData();
    form.append("image", state.file);
    form.append("method", state.method);
    form.append("num_colors", numColors.value);

    try {
      const resp = await fetch("/extract", { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Extraction failed.");

      state.palette = data.colors.map((c) => ({
        hex: c.hex,
        rgb: c.rgb,
        share: c.share || 0,
      }));
      state.target = null;
      renderPalette();
    } catch (err) {
      if (state.img) {
        // Keep manual palette if user hand-edited something; report softly.
        showError(err.message);
      }
    } finally {
      state.inFlight = false;
      extractBtn.disabled = false;
      extractBtn.textContent = "Extract palette";
    }
  }

  extractBtn.addEventListener("click", extract);

  addBtn.addEventListener("click", () => {
    if (state.target !== null) clearTarget();
    state.palette.push({ hex: "#8895a3", rgb: [136, 149, 163], share: 0 });
    state.target = state.palette.length - 1;
    renderPalette();
    refreshTargetHint();
  });

  /* ============================== render ============================== */

  function renderPalette() {
    colorList.innerHTML = "";
    state.palette.forEach((color, i) => {
      const node = stripTemplate.content.cloneNode(true);
      const swatch = node.querySelector(".swatch");
      const hexLabel = node.querySelector(".hex-label");
      const nativeInput = node.querySelector(".native-color");
      const removeBtn = node.querySelector(".remove-btn");

      swatch.dataset.index = i;
      swatch.style.background = color.hex;
      hexLabel.textContent = color.hex;
      hexLabel.style.color = stripTextColor(color.rgb);

      nativeInput.value = color.hex;

      if (state.target === i) swatch.classList.add("selected");

      /* click the circle -> select target for drag-adjust */
      swatch.addEventListener("click", (e) => {
        if (e.target.closest(".swatch-tools")) return;
        if (state.target === i) clearTarget();
        else {
          state.target = i;
          renderTargetOnly();
        }
      });

      /* click the hex label -> copy */
      hexLabel.addEventListener("click", (e) => {
        e.stopPropagation();
        flashCopy(color.hex, hexLabel);
      });

      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeColor(i);
      });

      nativeInput.addEventListener("input", (e) => {
        updateColor(i, rgbOf(e.target.value));
      });

      nativeInput.addEventListener("click", (e) => e.stopPropagation());

      /* double-click hex to type a value */
      hexLabel.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        const input = document.createElement("input");
        input.type = "text";
        input.value = color.hex;
        input.spellcheck = false;
        input.className = "hex-edit";
        input.style.fontFamily = MONO;
        hexLabel.replaceWith(input);
        input.focus();
        input.select();

        const commit = () => {
          const parsed = parseHex(input.value);
          if (parsed) updateColor(i, parsed);
          else renderPalette();
        };
        input.addEventListener("blur", commit);
        input.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") commit();
          if (ev.key === "Escape") renderPalette();
        });
      });

      colorList.appendChild(node);
    });

    results.hidden = state.palette.length === 0;
    if (state.palette.length === 0) return;

    const methodLabel =
      state.method === "manual"
        ? "Manual"
        : state.method === "median"
        ? "Median cut"
        : "K-means";
    const fileName = state.file ? state.file.name : "untitled";
    resultsTitle.textContent =
      `Palette — ${fileName} (${state.palette.length} colors, ${methodLabel})`;
    const total = state.palette.reduce((s, c) => s + c.share, 0);
    const auto = state.method !== "manual" && total > 0;
    outputSubtle.textContent = auto
      ? `${total.toFixed(1)}% coverage`
      : `${state.palette.length} colors`;

    refreshTargetHint();
  }

  function renderTargetOnly() {
    colorList
      .querySelectorAll(".swatch")
      .forEach((s) => s.classList.toggle("selected", +s.dataset.index === state.target));
    refreshTargetHint();
  }

  function refreshTargetHint() {
    if (state.target !== null && state.palette[state.target]) {
      setPickHint(
        `Drag on the image to adjust ${state.palette[state.target].hex}`
      );
      return;
    }
    if (state.method === "manual") {
      setPickHint("Click a pixel to add it to the palette.");
      return;
    }
    if (state.palette.length) {
      setPickHint("Select a color to adjust it, or click a pixel to add.");
    } else {
      setPickHint("");
    }
  }

  function flashCopy(hex, el) {
    if (hex && navigator.clipboard) {
      navigator.clipboard.writeText(hex).catch(() => {});
    }
    clearTimeout(state.copiedTimer);
    copiedNote.hidden = false;
    state.copiedTimer = setTimeout(() => {
      copiedNote.hidden = true;
      if (el) el.style.transform = "";
    }, 1000);
  }

  function parseHex(v) {
    let s = String(v).trim().replace(/^#/, "");
    if (/^[0-9a-f]{3}$/i.test(s)) {
      return [0, 1, 2].map((i) => parseInt(s[i] + s[i], 16));
    }
    if (/^[0-9a-f]{6}$/i.test(s)) {
      return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16));
    }
    return null;
  }

  /* ============================== export ============================== */

  document.querySelectorAll(".export-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!state.palette.length) return;
      const fmt = btn.dataset.fmt;
      try {
        const resp = await fetch(`/export/${fmt}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            colors: state.palette.map((c) => ({ rgb: c.rgb })),
          }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data.error || "Export failed.");
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `palette.${fmt}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (err) {
        showError(err.message);
      }
    });
  });

  /* init slider fill */
  numColors.dispatchEvent(new Event("input"));
})();