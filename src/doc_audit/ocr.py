from dataclasses import dataclass

import cv2
import pytesseract
from pytesseract import Output
from pytesseract.pytesseract import TesseractNotFoundError


@dataclass
class OCRResult:
    text: str
    confidence: float
    engine_version: str
    line_confidences: dict[str, float]


def run_ocr(image) -> OCRResult:
    try:
        data = pytesseract.image_to_data(
            image,
            lang="por",
            config="--oem 1 --psm 6",
            output_type=Output.DICT,
        )
        version = str(pytesseract.get_tesseract_version())
    except TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract não está instalado ou não está no PATH") from exc
    lines: dict[tuple[int, int, int], list[tuple[str, float]]] = {}
    for block, paragraph, line, word, confidence in zip(
        data["block_num"],
        data["par_num"],
        data["line_num"],
        data["text"],
        data["conf"],
        strict=True,
    ):
        word = word.strip()
        score = float(confidence)
        if word and score >= 0:
            lines.setdefault((int(block), int(paragraph), int(line)), []).append((word, score))
    line_texts = [
        (" ".join(word for word, _ in entries), sum(score for _, score in entries) / len(entries))
        for entries in lines.values()
    ]
    words = [entry for line in lines.values() for entry in line]
    text = "\n".join(line for line, _ in line_texts)
    confidence = sum(score for _, score in words) / len(words) if words else 0.0
    return OCRResult(
        text=text,
        confidence=confidence,
        engine_version=version,
        line_confidences=dict(line_texts),
    )


def read_qr_code(image) -> str | None:
    detector = cv2.QRCodeDetector()
    value, _, _ = detector.detectAndDecode(image)
    return value or None
