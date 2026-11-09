import cv2
import numpy as np
import pytest

from doc_audit.preprocessing import decode_image, deskew, preprocess_image


@pytest.mark.parametrize("rotation", [-15, -5, 0, 5, 15])
def test_deskew_corrects_known_small_rotations(rotation: int) -> None:
    image = np.full((600, 600), 255, dtype=np.uint8)
    for y in range(100, 500, 40):
        cv2.line(image, (50, y), (550, y), 0, 3)
    matrix = cv2.getRotationMatrix2D((300, 300), rotation, 1.0)
    rotated = cv2.warpAffine(image, matrix, (600, 600), borderValue=255)

    corrected = deskew(rotated)

    assert corrected.shape == rotated.shape
    if rotation == 0:
        assert np.array_equal(corrected, rotated)
    else:
        assert np.max(np.sum(corrected == 0, axis=1)) > np.max(np.sum(rotated == 0, axis=1))


def test_decode_image_rejects_invalid_bytes() -> None:
    with pytest.raises(ValueError, match="validar"):
        decode_image(b"not an image")


def test_decode_image_checks_pixel_limit_before_decoding() -> None:
    success, encoded = cv2.imencode(".png", np.zeros((20, 20, 3), dtype=np.uint8))
    assert success

    with pytest.raises(ValueError, match="limite de 100 pixels"):
        decode_image(encoded.tobytes(), max_pixels=100)


def test_preprocess_image_upscales_and_returns_binary_image() -> None:
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    cv2.putText(image, "TEST", (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

    processed = preprocess_image(image)

    assert processed.shape[0] == 1500
    assert set(np.unique(processed)).issubset({0, 255})


def test_preprocess_image_rejects_unknown_threshold_method() -> None:
    with pytest.raises(ValueError, match="não suportado"):
        preprocess_image(np.zeros((10, 10, 3), dtype=np.uint8), "unknown")
