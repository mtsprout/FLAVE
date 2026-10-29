# cpu_compositor.py
# CPU stand-in for the CUDA headless composer (sequence_preview_gpu), used
# when there is no NVIDIA stack (macOS, or FLAVE_BACKEND=cpu). Same layer
# list as the GPU path (sequence_player._layer_items, borrowed below), so
# every keyframe effect resolves exactly as there; the per-layer blend is
# numpy and follows the PTX blend_layer kernel: nearest-neighbour inverse
# mapping, rotate about the layer center, crop test on source pixel centers,
# chroma stack, contrast / brightness / gamma, opacity * alpha blend.
# Decode is cpu_decoder.CpuDecoder (ffmpeg pipe), no device memory.
# Not implemented yet: the border outline band (layer item [15]).
# The render calls frames_rgb(frames, snapshot) -> RGB24 bytes per frame
# and close(), the same two calls as render_manager._RenderGpu. ASCII only.

import math
import os
import sys
import threading

import numpy as np

_CPU = [None]
_DEC_MAX = 6            # decoders kept open (least recently used closed)
_SEEK_SKIP_MAX = 8      # decode through a short forward gap instead of a seek


def use_cpu_backend():
    # True when the CUDA stack is absent or FLAVE_BACKEND=cpu. Cached.
    if _CPU[0] is None:
        want = os.environ.get("FLAVE_BACKEND", "").lower()
        if want == "cpu" or sys.platform == "darwin":
            _CPU[0] = True
        elif want == "cuda":
            _CPU[0] = False
        else:
            try:
                from sequence_player_gpu import _libs
                _libs()
                _CPU[0] = False
            except Exception:
                _CPU[0] = True
    return _CPU[0]


FAST = True     # fast paths of blend_layer (tests turn it off to compare)


def _contiguous(idx):
    # True when idx is a run of consecutive integers (a 1:1 sampling)
    return len(idx) == 1 or bool(np.all(np.diff(idx) == 1))


def _num(v, default, lo, hi):
    try:
        v = float(v) if v is not None else default
    except (TypeError, ValueError):
        v = default
    if v != v:
        v = default
    return max(lo, min(hi, v))


def blend_layer(dst, src, scale=None, pos_dx=None, pos_dy=None,
                orig_size=None, opacity=None, crop_x=None, crop_y=None,
                gamma=None, brightness=None, contrast=None, rotate=None,
                outline=None, crop_edges=None, chroma=None,
                k_pos=1.0, k_scale=1.0):
    # dst: uint8 (H, W, 3), blended in place. src: uint8 (h, w, 3 or 4).
    # Arguments are those of SequencePlayer._blend. k_pos / k_scale: dst is
    # k times the sequence size (render Output Size): positions grow by
    # k_pos, a source in its own pixels is scaled by k_scale (1 for a source
    # already made at the output size, such as a text image).
    H, W = dst.shape[:2]
    sh, sw = src.shape[:2]
    factor = 1.0
    if scale is not None:
        try:
            factor = float(scale) / 100.0
        except (TypeError, ValueError):
            factor = 1.0
    factor *= k_scale
    if factor <= 0.0:
        return
    fx_, fy_ = factor, factor
    if orig_size is not None and sw > 0 and sh > 0:
        fx_ = factor * float(orig_size[0]) / float(sw)
        fy_ = factor * float(orig_size[1]) / float(sh)
    invs, invsy = 1.0 / fx_, 1.0 / fy_
    op = _num(opacity, 1.0, 0.0, 1.0)
    crops = []
    for value, size, i in ((crop_x, sw, 0), (crop_y, sh, 1)):
        c = _num(value, 0.0, -1.0e12, 1.0e12)
        if c and orig_size is not None and orig_size[i]:
            c = c * float(size) / float(orig_size[i])
        crops.append(max(0.0, c))
    # Centering, as _blend
    dx = (W - sw) // 2 if W > sw else 0
    dy = (H - sh) // 2 if H > sh else 0
    cx = (sw - W) // 2 if sw > W else 0
    cy = (sh - H) // 2 if sh > H else 0
    ox, oy = cx - dx, cy - dy
    if crop_edges is not None:
        from sequence_player import crop_edge_rect
        ce = crop_edge_rect(crop_x, crop_y, crop_edges, sw, sh, orig_size)
        if ce[0] == "sym":
            crops = [ce[1], ce[2]]
        else:
            lo_x, hi_x, lo_y, hi_y = ce[1:]
            if lo_x > hi_x or lo_y > hi_y:
                return
            src = src[lo_y:hi_y + 1, lo_x:hi_x + 1]
            sh, sw = src.shape[:2]
            ox, oy = ox - lo_x, oy - lo_y
            crops = [0.0, 0.0]
    g_ = _num(gamma, 1.0, 0.1, 5.0)
    b_ = _num(brightness, 0.0, -100.0, 100.0) / 100.0
    k_ = _num(contrast, 1.0, 0.0, 5.0)
    rot = _num(rotate, 0.0, -1.0e9, 1.0e9) % 360.0
    if rot % 90.0 == 0.0:
        rc, rs = ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0),
                  (0.0, -1.0))[int(rot // 90.0) % 4]
    else:
        rad = math.radians(rot)
        rc, rs = math.cos(rad), math.sin(rad)
    try:
        pdx = int(round(float(pos_dx) * k_pos)) if pos_dx is not None else 0
    except (TypeError, ValueError):
        pdx = 0
    try:
        pdy = int(round(float(pos_dy) * k_pos)) if pos_dy is not None else 0
    except (TypeError, ValueError):
        pdy = 0
    keys = []
    if chroma:
        from sequence_player import _chroma_key_rows
        keys = _chroma_key_rows(chroma)

    xs = np.arange(W, dtype=np.float32) + (0.5 - W * 0.5 - pdx)
    ys = np.arange(H, dtype=np.float32) + (0.5 - H * 0.5 - pdy)
    if rs == 0.0 and rc == 1.0:
        # Separable: source column per dst column, source row per dst row
        sx = np.rint(xs * invs + (W * 0.5 + ox - 0.5)).astype(np.int64)
        sy = np.rint(ys * invsy + (H * 0.5 + oy - 0.5)).astype(np.int64)
        vx = ((sx >= 0) & (sx < sw) & (sx + 0.5 >= crops[0])
              & (sx + 0.5 <= sw - crops[0]))
        vy = ((sy >= 0) & (sy < sh) & (sy + 0.5 >= crops[1])
              & (sy + 0.5 <= sh - crops[1]))
        xi, yi = np.nonzero(vx)[0], np.nonzero(vy)[0]
        if not len(xi) or not len(yi):
            return
        plain = (not keys and k_ == 1.0 and b_ == 0.0 and g_ == 1.0
                 and op >= 1.0 and src.shape[-1] == 3)
        if FAST and _contiguous(sx[xi]) and _contiguous(sy[yi]):
            # 1:1 mapping: source and destination are plain rectangles
            # (views, no gather)
            patch = src[sy[yi[0]]:sy[yi[-1]] + 1, sx[xi[0]]:sx[xi[-1]] + 1]
            view = dst[yi[0]:yi[-1] + 1, xi[0]:xi[-1] + 1]
            if plain:
                view[...] = patch
            else:
                view[...] = _mix(view, patch, keys, k_, b_, g_, op)
            return
        patch = src.take(sy[yi], axis=0).take(sx[xi], axis=1)
        if FAST and plain and len(xi) == W and len(yi) == H:
            dst[...] = patch
            return
        sel = np.ix_(yi, xi)
        dst[sel] = _mix(dst[sel], patch, keys, k_, b_, g_, op)
        return
    # Rotated: per-pixel inverse mapping
    X = np.broadcast_to(xs[None, :], (H, W))
    Y = np.broadcast_to(ys[:, None], (H, W))
    u = X * rc + Y * rs
    v = Y * rc - X * rs
    sx = np.rint(u * invs + (W * 0.5 + ox - 0.5)).astype(np.int64)
    sy = np.rint(v * invsy + (H * 0.5 + oy - 0.5)).astype(np.int64)
    m = ((sx >= 0) & (sx < sw) & (sy >= 0) & (sy < sh)
         & (sx + 0.5 >= crops[0]) & (sx + 0.5 <= sw - crops[0])
         & (sy + 0.5 >= crops[1]) & (sy + 0.5 <= sh - crops[1]))
    if not m.any():
        return
    patch = src[sy[m], sx[m]]
    cur = dst[m]
    dst[m] = _mix(cur, patch, keys, k_, b_, g_, op)


def _mix(cur, patch, keys, k_, b_, g_, op):
    # cur: uint8 (..., 3) destination pixels; patch: uint8 (..., 3|4)
    rgb = patch[..., :3].astype(np.float32)
    if patch.shape[-1] == 4:
        a = patch[..., 3].astype(np.float32) * (1.0 / 255.0)
    else:
        a = np.ones(rgb.shape[:-1], np.float32)
    for kr, kg, kb, kt in keys:
        d2 = ((rgb[..., 0] - kr) ** 2 + (rgb[..., 1] - kg) ** 2
              + (rgb[..., 2] - kb) ** 2)
        a = np.where(d2 <= kt * kt, 0.0, a).astype(np.float32)
    if k_ != 1.0 or b_ != 0.0 or g_ != 1.0:
        c = rgb * (1.0 / 255.0)
        if k_ != 1.0:
            c = np.clip((c - 0.5) * k_ + 0.5, 0.0, 1.0)
        if b_ != 0.0:
            c = np.clip(c + b_, 0.0, 1.0)
        if g_ != 1.0:
            c = np.power(c, 1.0 / g_)
        rgb = np.minimum(np.rint(c * 255.0), 255.0)
    a = a * op
    out = cur.astype(np.float32)
    out += (rgb - out) * a[..., None]
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


class _Dec(object):
    # One open CpuDecoder and the raw frames its upload hook captured
    def __init__(self, path):
        from cpu_decoder import CpuDecoder
        self.store = {}
        self.dec = CpuDecoder(path, upload=self._upload)
        self.next = None        # source index the next get_batch_frames yields
        self.last = None        # (source index, array)

    def _upload(self, raw, slot):
        self.store[slot] = raw
        return slot

    def array(self, slot):
        d = self.dec
        return np.frombuffer(self.store[slot], np.uint8).reshape(
            d.height, d.width, 3)


class CpuComposer(object):
    cpu_backend = True
    headless = True

    def __init__(self, project, sequence_id, seq_w, seq_h, out_size=None):
        # seq_w / seq_h: the sequence (what _layer_items measures in);
        # out_size (w, h): the composited frame, a render's Output Size
        self.project = project
        self.sequence_id = int(sequence_id)
        self.seq_w, self.seq_h = int(seq_w), int(seq_h)
        self.out_w, self.out_h = ((int(out_size[0]), int(out_size[1]))
                                  if out_size else (self.seq_w, self.seq_h))
        self.k = self.out_w / float(self.seq_w)
        self.row = self.seq_w * 3
        self.ready = True
        self.closed = False
        self.paths = {}
        self.images = {}
        self.decs = {}          # decoder key -> _Dec, least recently used first
        self.key = None
        self.lock = threading.RLock()

    class _TL(object):
        def __init__(self, project):
            self._p = project

        def _project_db(self):
            return self._p

    @property
    def timeline(self):
        return CpuComposer._TL(self.project)

    # ---- sources
    def _image(self, path):
        if path in self.images:
            return self.images[path]
        from PySide6.QtGui import QImage
        arr = None
        img = QImage(path)
        if not img.isNull():
            arr = self._qimage_array(img)
        self.images[path] = arr
        return arr

    @staticmethod
    def _qimage_array(img):
        from PySide6.QtGui import QImage
        img = img.convertToFormat(QImage.Format_RGBA8888)
        w, h, bpl = img.width(), img.height(), img.bytesPerLine()
        raw = np.frombuffer(bytes(img.constBits())[:bpl * h], np.uint8)
        return raw.reshape(h, bpl)[:, :w * 4].reshape(h, w, 4).copy()

    def _text_image_scaled(self, clip_id, style):
        # The text clip drawn for the output size: font size, position and
        # shadow blur / offset grow with the frame (not a stretched image)
        from PySide6.QtGui import QImage
        from text_clip import render_text_image
        k = self.k
        style = tuple(style)
        text, family, size, color, x, y = style[:6]
        shadow = list(style[6:11]) if len(style) >= 11 else None
        if shadow:
            shadow[2] = int(round((shadow[2] or 0) * k))
            shadow[4] = int(round((shadow[4] or 0) * k))
        img = render_text_image(
            text, family, max(1, int(round((size or 1) * k))), color,
            None if x is None else int(round(x * k)),
            None if y is None else int(round(y * k)),
            self.out_w, self.out_h, clip_key=clip_id,
            shadow=tuple(shadow) if shadow else None)
        return img.convertToFormat(QImage.Format_RGBA8888)

    def _text(self, path, clip_id, style):
        if path in self.images:
            return self.images[path]
        arr = None
        if style is not None:
            from player_text import text_rgba
            if self.k == 1.0:
                img = text_rgba(clip_id, style, self.seq_w, self.seq_h)
            else:
                img = self._text_image_scaled(clip_id, style)
            arr = self._qimage_array(img)
        # One text image per clip: drop older styles of this clip
        mine = "text:%d:" % int(clip_id)
        for k in [k for k in self.images if k.startswith(mine)]:
            del self.images[k]
        self.images[path] = arr
        return arr

    def _video(self, dkey, path, src_frame):
        # RGB array of source frame src_frame, or None (transparent layer)
        from sequence_player import source_index_ok, learn_source_end
        if not source_index_ok(self, dkey, None, src_frame):
            return None
        d = self.decs.pop(dkey, None)
        if d is None:
            d = _Dec(path)
            while len(self.decs) >= _DEC_MAX:
                old = self.decs.pop(next(iter(self.decs)))
                old.dec.close()
        self.decs[dkey] = d
        if d.last is not None and d.last[0] == src_frame:
            return d.last[1]
        skip = (src_frame - d.next) if d.next is not None else -1
        count = 1
        try:
            if 0 < skip <= _SEEK_SKIP_MAX:
                count = skip + 1
            elif d.next != src_frame:
                d.dec.seek_to_index(src_frame)
            frames = d.dec.get_batch_frames(count)
        except (IndexError, ValueError):
            d.next = d.last = None
            learn_source_end(dkey, src_frame)
            return None
        if len(frames) < count:
            d.next = d.last = None
            return None
        arr = d.array(count - 1)
        d.next = src_frame + 1
        d.last = (src_frame, arr)
        return arr

    # ---- frames
    def _frame(self, frame, snapshot):
        canvas = np.zeros((self.out_h, self.out_w, 3), np.uint8)
        styles = snapshot[29] if len(snapshot) > 29 else {}
        for layer in self._layer_items(frame, snapshot):
            kind, path, src_frame = layer[0], layer[1], layer[2]
            dkey = layer[16] if len(layer) > 16 else (0, path)
            if kind == "image":
                src = self._image(path)
            elif kind == "text":
                src = self._text(path, layer[6][0], styles.get(layer[6][0]))
                # made at the output size already: positions only grow
                k_scale = 1.0
            elif os.path.isfile(path):
                src = self._video(dkey, path, src_frame)
            else:
                src = None
            if src is None:
                continue
            g = lambda i: layer[i] if len(layer) > i else None
            if kind != "text":
                k_scale = self.k
            blend_layer(canvas, src, k_pos=self.k, k_scale=k_scale,
                        scale=g(3), pos_dx=g(4), pos_dy=g(5),
                        orig_size=g(7), opacity=g(8), crop_x=g(9),
                        crop_y=g(10), gamma=g(11), brightness=g(12),
                        contrast=g(13), rotate=g(14), outline=g(15),
                        crop_edges=g(17), chroma=g(18))
        return canvas

    def frames_rgb(self, frames, snapshot):
        if self.closed:
            raise RuntimeError("The CPU compositor was released.")
        with self.lock:
            return [self._frame(f, snapshot).tobytes() for f in frames]

    # ---- preview worker (same two calls the GPU composer has)
    def frames_jpeg_batch(self, frames, quality, snapshot):
        # JPEG bytes per frame (None on a failed frame), Qt encodes
        # at the project's Preview Size
        if self.closed or snapshot is None:
            return None
        out = []
        for f in frames:
            try:
                out.append(self._jpeg(self.frames_rgb([f], snapshot)[0], quality))
            except Exception as e:
                print("CPU compositor frame %s failed: %s" % (f, e))
                out.append(None)
        return out

    def frame_jpeg(self, frame, quality=90, snapshot=None, worker=False):
        # Worker only: the GUI path returns None (the worker fills it)
        if not worker:
            return None
        res = self.frames_jpeg_batch([frame], quality, snapshot)
        return res[0] if res else None

    def _jpeg(self, rgb, quality):
        from PySide6.QtCore import QBuffer, QIODevice
        from sequence_player_preview import _qt_preview_image
        img = _qt_preview_image(self, rgb)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        if not img.save(buf, "JPG", quality):
            return None
        return bytes(buf.data())

    def close(self):
        self.closed = True
        self.ready = False
        for d in self.decs.values():
            try:
                d.dec.close()
            except Exception:
                pass
        self.decs.clear()
        self.images.clear()


def _borrow():
    from sequence_player import SequencePlayer as P
    for name in ("_layer_items", "_footage_path", "_dec_instances",
                 "_clip_path"):
        setattr(CpuComposer, name, P.__dict__[name])


_borrow_done = [False]


def new_cpu_composer(project, sequence_id, out_size=None):
    _borrow_once()
    from sequence_preview_gpu import _sequence_size
    w, h = _sequence_size(project, sequence_id)
    return CpuComposer(project, sequence_id, w, h, out_size)


# ---- the preview worker's one composer (sequence_preview_gpu.headless_for)
_GEN = [None]
_GEN_LOCK = threading.Lock()


def cpu_generator_for(project, sequence_id):
    # Kept while the sequence and its size stay the same (decoders warm)
    _borrow_once()
    from sequence_preview_gpu import _sequence_size
    w, h = _sequence_size(project, sequence_id)
    key = (os.path.abspath(project), int(sequence_id), w, h)
    with _GEN_LOCK:
        g = _GEN[0]
        if g is None or g.closed or g.key != key:
            if g is not None:
                g.close()
            g = CpuComposer(project, sequence_id, w, h)
            g.key = key
            _GEN[0] = g
        return g


def cpu_generator_active():
    return _GEN[0] is not None and not _GEN[0].closed


def cpu_generator_release():
    with _GEN_LOCK:
        if _GEN[0] is not None:
            _GEN[0].close()
            _GEN[0] = None


def _borrow_once():
    if not _borrow_done[0]:
        _borrow()
        _borrow_done[0] = True
