import json

import cv2

from scripts.generate_synthetic_dataset import generate_sample


def test_synthetic_receipt_is_labeled_and_decodable(tmp_path) -> None:
    image_path = generate_sample(tmp_path, seed=3)
    label = json.loads(image_path.with_suffix(".json").read_text(encoding="utf-8"))
    image = cv2.imread(str(image_path))

    assert image is not None
    assert image.shape[:2] == (1400, 1400)
    assert label["image"] == image_path.name
    assert label["expected"]["cnpj"]
    assert label["expected"]["raw_text"].startswith("MERCADO SINTETICO")
    assert label["expected"]["items"]
