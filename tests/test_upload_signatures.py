from doc_audit.api import SUPPORTED_SIGNATURES, _safe_original_name


def test_detects_magic_bytes_for_supported_types() -> None:
    assert SUPPORTED_SIGNATURES["image/jpeg"](b"\xff\xd8\xff\xdb")
    assert SUPPORTED_SIGNATURES["image/png"](b"\x89PNG\r\n\x1a\ncontent")
    assert SUPPORTED_SIGNATURES["application/pdf"](b"%PDF-1.7\ncontent")
    assert not any(check(b"MZ executable") for check in SUPPORTED_SIGNATURES.values())


def test_sanitizes_original_filename() -> None:
    assert _safe_original_name("../../nota fiscal;$(whoami).jpg") == "nota_fiscal_whoami_.jpg"
