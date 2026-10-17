// Pixelates rectangular regions of a photo (faces and plates from Gemini, or areas drawn by hand).
// Boxes are [ymin, xmin, ymax, xmax] scaled 0–1000, Gemini's convention.

function pixelate(ctx, x, y, w, h) {
  // Coarse cells (about five across the region's short side) so faces and plate text can't be read.
  const cell = Math.max(8, Math.round(Math.min(w, h) / 5));
  const small = document.createElement('canvas');
  small.width = Math.max(1, Math.round(w / cell)); small.height = Math.max(1, Math.round(h / cell));
  small.getContext('2d').drawImage(ctx.canvas, x, y, w, h, 0, 0, small.width, small.height);
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(small, 0, 0, small.width, small.height, x, y, w, h);
  ctx.restore();
}

/** Returns an object URL of the photo (longest side ≤ maxSide) with every box pixelated, padded slightly. */
export async function blurPhoto(file, boxes, { maxSide = 1600, pad = 0.2 } = {}) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = Object.assign(document.createElement('canvas'), { width: Math.round(bitmap.width * scale), height: Math.round(bitmap.height * scale) });
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  for (const [y0, x0, y1, x1] of boxes) {
    const bw = (x1 - x0) / 1000 * canvas.width, bh = (y1 - y0) / 1000 * canvas.height;
    const x = Math.max(0, x0 / 1000 * canvas.width - bw * pad), y = Math.max(0, y0 / 1000 * canvas.height - bh * pad);
    const w = Math.min(canvas.width - x, bw * (1 + 2 * pad)), h = Math.min(canvas.height - y, bh * (1 + 2 * pad));
    if (w > 1 && h > 1) pixelate(ctx, x, y, w, h);
  }
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
  return URL.createObjectURL(blob);
}
