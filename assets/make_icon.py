# assets/make_icon.py
# Draws the FLAVE for Mac application icon and writes assets/FLAVE.png
# (1024 px) and, on macOS, assets/FLAVE.icns (via iconutil).
# Run:  python assets/make_icon.py     ASCII only.

import os
import shutil
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QRadialGradient)

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 1024
BODY = 824                   # the macOS icon grid: the body leaves a margin
RADIUS = 0.225 * BODY


def draw():
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = (SIZE - BODY) / 2.0
    body = QRectF(m, m, BODY, BODY)
    clip = QPainterPath()
    clip.addRoundedRect(body, RADIUS, RADIUS)

    # soft shadow under the body
    for i, a in enumerate((5, 8, 11, 14)):
        sh = QPainterPath()
        sh.addRoundedRect(body.adjusted(-6 + i * 3, 12 + i * 3, 6 - i * 3, 24 - i * 3),
                          RADIUS, RADIUS)
        p.fillPath(sh, QColor(0, 0, 0, a))

    # background: deep indigo to violet-blue
    g = QLinearGradient(body.topLeft(), body.bottomRight())
    g.setColorAt(0.0, QColor("#5b46f2"))
    g.setColorAt(0.55, QColor("#2a2f8f"))
    g.setColorAt(1.0, QColor("#101a4a"))
    p.fillPath(clip, QBrush(g))
    # warm glow low in the corner (stage-light magenta)
    glow = QRadialGradient(QPointF(body.left() + BODY * 0.2, body.bottom() - BODY * 0.05),
                           BODY * 0.7)
    glow.setColorAt(0.0, QColor(255, 70, 160, 120))
    glow.setColorAt(1.0, QColor(255, 70, 160, 0))
    p.save()
    p.setClipPath(clip)
    p.fillRect(body, QBrush(glow))

    # film strip: two columns of sprocket holes
    hole_w, hole_h, gap = 46.0, 64.0, 46.0
    n = 7
    total = n * hole_h + (n - 1) * gap
    top = body.top() + (BODY - total) / 2.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 150))
    for col_x in (body.left() + 64.0, body.right() - 64.0 - hole_w):
        for i in range(n):
            p.drawRoundedRect(QRectF(col_x, top + i * (hole_h + gap), hole_w, hole_h), 12, 12)
    # frame lines between the sprocket columns
    pen = QPen(QColor(255, 255, 255, 60), 6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(body.left() + 150, body.top() + 150, BODY - 300, BODY - 300),
                      44, 44)

    # the play triangle, rounded, with a thin highlight
    cx, cy = SIZE / 2.0 + 18.0, SIZE / 2.0
    s = 190.0
    tri = QPainterPath()
    tri.moveTo(cx - s * 0.75, cy - s)
    tri.lineTo(cx + s * 1.05, cy)
    tri.lineTo(cx - s * 0.75, cy + s)
    tri.closeSubpath()
    p.setPen(QPen(QColor("white"), 46, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    tg = QLinearGradient(QPointF(cx, cy - s), QPointF(cx, cy + s))
    tg.setColorAt(0.0, QColor("#ffffff"))
    tg.setColorAt(1.0, QColor("#d9dcff"))
    p.setBrush(QBrush(tg))
    p.drawPath(tri)

    # top sheen
    sheen = QLinearGradient(body.topLeft(), QPointF(body.left(), body.top() + BODY * 0.45))
    sheen.setColorAt(0.0, QColor(255, 255, 255, 46))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(body, QBrush(sheen))
    p.restore()
    # hairline edge
    p.setPen(QPen(QColor(255, 255, 255, 40), 3))
    p.setBrush(Qt.NoBrush)
    p.drawPath(clip)
    p.end()
    return img


def write_icns(img):
    if sys.platform != "darwin" or not shutil.which("iconutil"):
        return None
    iconset = os.path.join(HERE, "FLAVE.iconset")
    os.makedirs(iconset, exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = base * scale
            out = img.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            name = "icon_%dx%d%s.png" % (base, base, "@2x" if scale == 2 else "")
            out.save(os.path.join(iconset, name))
    icns = os.path.join(HERE, "FLAVE.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    shutil.rmtree(iconset)
    return icns


if __name__ == "__main__":
    app = QGuiApplication([])
    image = draw()
    png = os.path.join(HERE, "FLAVE.png")
    image.save(png)
    print("wrote", png)
    print("wrote", write_icns(image))
