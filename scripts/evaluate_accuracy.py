import argparse
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from doc_audit.accuracy import aggregate_accuracy, evaluate_document
from doc_audit.auditing import audit_extraction
from doc_audit.config import settings
from doc_audit.models import Document
from doc_audit.ocr import read_qr_code, run_ocr
from doc_audit.parsers import (
    parse_access_key,
    parse_cnpj,
    parse_cpf,
    parse_issue_datetime,
    parse_items,
    parse_total,
)
from doc_audit.preprocessing import preprocess_image
from doc_audit.tasks import _document_pages


def _extract(image_path: Path, threshold_method: str) -> dict[str, Any]:
    document = Document(
        file_hash="",
        original_name=image_path.name,
        mime_type="application/pdf" if image_path.suffix.lower() == ".pdf" else "image/jpeg",
        storage_path=str(image_path),
        status="PROCESSING",
    )
    pages = _document_pages(document)
    ocr_results = []
    qr_values = []
    for image in pages:
        ocr_results.append(run_ocr(preprocess_image(image, threshold_method)))
        qr_value = read_qr_code(image)
        if qr_value:
            qr_values.append(qr_value)
    raw_text = "\n".join(result.text for result in ocr_results)
    lines = [
        (line, confidence)
        for result in ocr_results
        for line, confidence in result.line_confidences.items()
    ]

    def confidence_for(value: object) -> float:
        normalized = re.sub(r"\D", "", str(value))
        for line, confidence in lines:
            if normalized and normalized in re.sub(r"\D", "", line):
                return confidence
        return 0.0

    access_key = parse_access_key(raw_text)
    qr_key = parse_access_key("\n".join(qr_values))
    if qr_key:
        access_key = qr_key
    issue_datetime = parse_issue_datetime(raw_text)
    cnpj = parse_cnpj(raw_text)
    cpf = parse_cpf(raw_text)
    total = parse_total(raw_text)
    items = parse_items(raw_text)
    field_confidences = {
        "cnpj": confidence_for(cnpj) if cnpj else 0,
        "cpf": confidence_for(cpf) if cpf else 0,
        "issue_datetime": confidence_for(issue_datetime.strftime("%d%m%Y"))
        if issue_datetime
        else 0,
        "total_amount": confidence_for(total) if total is not None else 0,
        "access_key": 100.0 if qr_key else confidence_for(access_key) if access_key else 0,
    }
    audit = audit_extraction(
        cnpj=cnpj,
        cpf=cpf,
        issue_datetime=issue_datetime,
        total_amount=total,
        access_key=access_key,
        item_totals=[item["total_price"] for item in items],
        field_confidences=field_confidences,
        tolerance=Decimal(settings.audit_tolerance),
        minimum_confidence=settings.min_field_confidence,
    )
    return {
        "raw_text": raw_text,
        "cnpj": cnpj,
        "cpf": cpf,
        "issue_datetime": issue_datetime.isoformat() if issue_datetime else None,
        "total_amount": total,
        "access_key": access_key,
        "items": items,
        "verdict": audit["verdict"],
    }


def run_evaluation(dataset: Path, threshold_method: str) -> dict[str, object]:
    dataset_root = dataset.resolve()
    results = []
    labels = sorted(dataset_root.glob("*.json"))
    if not labels:
        raise ValueError(f"Nenhum arquivo de ground truth encontrado em {dataset_root}")
    for label_path in labels:
        label = json.loads(label_path.read_text(encoding="utf-8"))
        image_path = (dataset_root / label["image"]).resolve()
        if not image_path.is_relative_to(dataset_root):
            raise ValueError(f"Imagem fora do diretório do conjunto: {label['image']}")
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        expected = label["expected"]
        actual = _extract(image_path, threshold_method)
        result = evaluate_document(expected, actual)
        result["document_id"] = label.get("document_id", image_path.stem)
        results.append(result)
    return {
        "threshold_method": threshold_method,
        "summary": aggregate_accuracy(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia OCR e parser contra ground truth rotulado")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--threshold", choices=("adaptive", "otsu"), default="adaptive")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_evaluation(args.dataset, args.threshold)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
