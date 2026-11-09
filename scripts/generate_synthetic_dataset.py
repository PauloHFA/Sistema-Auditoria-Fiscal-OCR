import argparse
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

import cv2
import numpy as np

from doc_audit.validation import is_valid_cnpj

WIDTH = 1400
HEIGHT = 1400
FONT = cv2.FONT_HERSHEY_SIMPLEX
PRODUCTS = ("ARROZ TIPO 1", "CAFE TORRADO", "LEITE INTEGRAL", "FEIJAO CARIOCA", "ACUCAR")


class SyntheticItem(TypedDict):
    description: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal


def _cnpj_for_seed(seed: int) -> str:
    prefix = f"{seed:08d}0001"
    for suffix in range(100):
        candidate = f"{prefix}{suffix:02d}"
        if is_valid_cnpj(candidate):
            return candidate
    raise ValueError(f"Nao foi possivel gerar CNPJ sintético para semente {seed}")


def _money(amount: Decimal) -> str:
    whole, cents = f"{amount:.2f}".split(".")
    return f"{int(whole):,}".replace(",", ".") + f",{cents}"


def generate_sample(output_dir: Path, seed: int) -> Path:
    cnpj = _cnpj_for_seed(seed + 1)
    if seed % 10 == 1:
        while is_valid_cnpj(cnpj):
            cnpj = f"{cnpj[:-1]}{(int(cnpj[-1]) + 1) % 10}"
    issue_date = date(2025, 1, 1) + timedelta(days=seed % 365)
    item_count = 1 + seed % 3
    items: list[SyntheticItem] = []
    for line_no in range(1, item_count + 1):
        quantity = Decimal(1 + seed % 2)
        unit_price = Decimal(350 + ((seed * 17 + line_no * 23) % 2200)) / 100
        total_price = quantity * unit_price
        items.append(
            {
                "description": PRODUCTS[(seed + line_no) % len(PRODUCTS)],
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
            }
        )
    items_total = sum((item["total_price"] for item in items), Decimal("0.00"))
    total = items_total + Decimal("5.00") if seed % 10 == 0 else items_total
    lines = [
        "MERCADO SINTETICO",
        f"CNPJ: {cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
        f"EMISSAO: {issue_date:%d/%m/%Y} 10:30",
        "ITENS DA VENDA",
    ]
    for line_no, item in enumerate(items, start=1):
        quantity = item["quantity"]
        lines.append(
            f"{line_no:03d} {item['description']} {quantity:.3f}".replace(".", ",")
            + f" UN {_money(item['unit_price'])} {_money(item['total_price'])}"
        )
    lines.append(f"VALOR TOTAL R$ {_money(total)}")
    lines.append("OBRIGADO VOLTE SEMPRE")

    image: np.ndarray = np.full((HEIGHT, WIDTH, 3), 255, dtype=np.uint8)
    y = 110
    scale = 1.05 + (seed % 3) * 0.1
    for line in lines:
        cv2.putText(image, line, (100, y), FONT, scale, (0, 0, 0), 2, cv2.LINE_AA)
        y += 115

    angle = (-2, -1, 0, 1, 2)[seed % 5]
    if angle:
        matrix = cv2.getRotationMatrix2D((WIDTH / 2, HEIGHT / 2), angle, 1.0)
        image = cv2.warpAffine(
            image,
            matrix,
            (WIDTH, HEIGHT),
            borderValue=(255, 255, 255),
        )

    filename = f"receipt-{seed + 1:03d}"
    image_path = output_dir / f"{filename}.png"
    if not cv2.imwrite(str(image_path), image):
        raise OSError(f"Nao foi possivel escrever {image_path}")
    expected = {
        "raw_text": "\n".join(lines),
        "cnpj": cnpj,
        "cpf": None,
        "issue_datetime": f"{issue_date.isoformat()}T10:30:00",
        "total_amount": str(total),
        "access_key": None,
        "items": [
            {
                "description": item["description"],
                "quantity": str(item["quantity"]),
                "unit_price": str(item["unit_price"]),
                "total_price": str(item["total_price"]),
            }
            for item in items
        ],
        "should_review": seed % 10 in {0, 1},
    }
    label = {"document_id": filename, "image": image_path.name, "expected": expected}
    label_path = output_dir / f"{filename}.json"
    label_path.write_text(json.dumps(label, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return image_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera recibos e ground truth totalmente sintéticos"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("samples/synthetic"))
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()
    if args.count < 1 or args.start < 0:
        parser.error("--count deve ser positivo e --start nao pode ser negativo")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for seed in range(args.start, args.start + args.count):
        generate_sample(args.output_dir, seed)
    print(f"Gerados {args.count} recibos sinteticos em {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
