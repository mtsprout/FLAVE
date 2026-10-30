# cpu_effects.py
# Blur and drop shadow for a layer on the CPU backend. The layer is drawn
# twice with the ordinary blend_layer, onto black and onto white canvases;
# from the pair the layer's colour (premultiplied) and alpha come out exactly
# as it would show, with every transform, crop, rotation, key and opacity
# applied. The effects then work on that picture:
#   blur    both blurred (a Gaussian-like triple box blur, radius in sequence
#           px, large radii on a reduced copy), then composited over dst
#   shadow  the layer's alpha, blurred and shifted down-right, darkens dst
#           under the layer (strength percent); the geometry is a fixed soft
#           shadow in proportion to the frame height
# No effect (radius / strength 0 or None) never reaches this module. The
# Windows GPU kernel has no counterpart. ASCII only.

import numpy as np

SHADOW_DISTANCE = 0.014      # of the frame height
SHADOW_BLUR = 0.020          # of the frame height


def _box(a, k, axis):
    # Running mean of width 2k + 1 along axis (zeros beyond the edges)
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim
    pad[axis] = (k + 1, k)
    c = np.cumsum(np.pad(a, pad), axis=axis, dtype=np.float32)
    hi = np.take(c, np.arange(2 * k + 1, 2 * k + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) * (1.0 / (2 * k + 1))


def blur(a, radius):
    # a float32 (H, W) or (H, W, C); radius in pixels of a (reach about
    # radius, like a Gaussian of sigma radius / 2.4)
    if radius < 0.5:
        return a
    ds = 1 if radius < 12 else 2 if radius < 30 else 4 if radius < 90 else 8
    h, w = a.shape[:2]
    if ds > 1:
        ph, pw = (-h) % ds, (-w) % ds
        pad = [(0, ph), (0, pw)] + [(0, 0)] * (a.ndim - 2)
        small = np.pad(a, pad, mode="edge")
        small = small.reshape((h + ph) // ds, ds, (w + pw) // ds, ds,
                              *a.shape[2:]).mean(axis=(1, 3)).astype(np.float32)
    else:
        small = a
    k = max(1, int(round(radius / ds / 3.0)))
    for _ in range(3):
        small = _box(small, k, 0)
        small = _box(small, k, 1)
    if ds > 1:
        small = np.repeat(np.repeat(small, ds, axis=0), ds, axis=1)[:h, :w]
    return small


def layer_picture(draw, shape):
    # (premultiplied colour float32 (H, W, 3) 0..255, alpha float32 (H, W)
    # 0..1) of what draw(canvas) paints; None when it paints nothing.
    # draw(canvas) blends one layer into a uint8 (H, W, 3) canvas.
    h, w = shape
    black = np.zeros((h, w, 3), np.uint8)
    white = np.full((h, w, 3), 255, np.uint8)
    draw(black)
    draw(white)
    # alpha from the green channel pair (white - black = 255 * (1 - alpha))
    diff = np.subtract(white[..., 1], black[..., 1], dtype=np.int16)
    alpha = np.clip(1.0 - diff * np.float32(1.0 / 255.0), 0.0, 1.0).astype(np.float32)
    if not alpha.any():
        return None
    return black.astype(np.float32), alpha


def apply(dst, draw, blur_px, shadow_pct):
    # Composite the layer drawn by draw onto dst (uint8 (H, W, 3), in place)
    # with blur_px (output pixels) and shadow_pct (0..100) applied. Only the
    # box the layer covers, plus the reach of the effects, is processed.
    h, w = dst.shape[:2]
    pic = layer_picture(draw, (h, w))
    if pic is None:
        return
    color, alpha = pic
    shadow_on = bool(shadow_pct and shadow_pct > 0)
    margin = int((blur_px or 0.0) * 1.6) + 2
    if shadow_on:
        margin += int(h * (SHADOW_DISTANCE + SHADOW_BLUR * 1.6)) + 2
    ys = np.nonzero(alpha.any(axis=1))[0]
    xs = np.nonzero(alpha.any(axis=0))[0]
    y0, y1 = max(0, int(ys[0]) - margin), min(h, int(ys[-1]) + 1 + margin)
    x0, x1 = max(0, int(xs[0]) - margin), min(w, int(xs[-1]) + 1 + margin)
    color, alpha = color[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    ch, cw = alpha.shape
    if blur_px and blur_px > 0:
        alpha = np.clip(blur(alpha, blur_px), 0.0, 1.0)
        color = blur(color, blur_px)
    out = dst[y0:y1, x0:x1].astype(np.float32)
    if shadow_on:
        d = int(round(h * SHADOW_DISTANCE * 0.7071))
        sa = blur(alpha, max(1.0, h * SHADOW_BLUR)) * min(1.0, shadow_pct / 100.0)
        if d:
            moved = np.zeros_like(sa)
            moved[d:, d:] = sa[:ch - d, :cw - d]
            sa = moved
        out *= (1.0 - sa)[..., None]
    out = out * (1.0 - alpha)[..., None] + color
    dst[y0:y1, x0:x1] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
