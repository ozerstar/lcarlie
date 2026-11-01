"""Fiş fotoğrafını PaddleOCR ile okuyup satır satır düz metin basar.

Ayrı venv'de çalışır (/opt/lcarlie/ocr-venv); Jarvis bunu alt süreç olarak
çağırır: `ocr-venv/bin/python paddle_ocr.py <görsel>` -> stdout metin.
"""
import os
import sys

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import numpy as np  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

_engine = None


def engine():
    global _engine
    if _engine is None:
        from paddleocr import PaddleOCR
        _engine = PaddleOCR(
            lang="tr",
            text_detection_model_name="PP-OCRv5_mobile_det",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_det_limit_type="max",
            text_det_limit_side_len=2400,
        )
    return _engine


def read_lines(path, side=2400):
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    image.thumbnail((side, side))
    result = engine().predict(np.array(image)[:, :, ::-1])[0]
    boxes = []
    for text, box in zip(result["rec_texts"], result["rec_boxes"], strict=True):
        x1, y1, x2, y2 = (float(value) for value in box)
        if text.strip():
            boxes.append((y1, y2, x1, text.strip()))
    boxes.sort(key=lambda item: (item[0] + item[1]) / 2)
    lines, current = [], []
    for box in boxes:
        center = (box[0] + box[1]) / 2
        if current:
            ref = current[-1]
            height = ref[1] - ref[0]
            if abs(center - (ref[0] + ref[1]) / 2) > height * 0.5:
                lines.append(current)
                current = []
        current.append(box)
    if current:
        lines.append(current)
    return "\n".join(" ".join(item[3] for item in sorted(line, key=lambda item: item[2])) for line in lines)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(read_lines(path))
