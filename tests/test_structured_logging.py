import json
import logging

from doc_audit.structured_logging import JsonLogFormatter


def test_json_formatter_includes_processing_context() -> None:
    record = logging.LogRecord(
        name="doc_audit.tasks",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="processing stage completed",
        args=(),
        exc_info=None,
    )
    record.document_id = "document-123"
    record.stage = "ocr"
    record.duration_ms = 42.5
    record.page = 2

    formatted = json.loads(JsonLogFormatter().format(record))

    assert formatted["message"] == "processing stage completed"
    assert formatted["document_id"] == "document-123"
    assert formatted["stage"] == "ocr"
    assert formatted["duration_ms"] == 42.5
    assert formatted["page"] == 2
