from doc_audit.ocr import run_ocr


def test_ocr_preserves_lines_and_line_confidence(monkeypatch) -> None:
    import doc_audit.ocr as ocr_module

    monkeypatch.setattr(
        ocr_module.pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 2],
            "text": ["VALOR", "TOTAL", "87,90"],
            "conf": ["90", "80", "70"],
        },
    )
    monkeypatch.setattr(ocr_module.pytesseract, "get_tesseract_version", lambda: "5.4.0")

    result = run_ocr(object())

    assert result.text == "VALOR TOTAL\n87,90"
    assert result.line_confidences["VALOR TOTAL"] == 85
    assert result.confidence == 80
