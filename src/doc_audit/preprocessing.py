import cv2
import numpy as np


def decode_image(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError("Não foi possível decodificar a imagem")
    return image


def deskew(binary_image: np.ndarray) -> np.ndarray:
    text_pixels = cv2.bitwise_not(binary_image)
    coordinates = np.column_stack(np.where(text_pixels > 0))
    if len(coordinates) < 10:
        return binary_image
    points = coordinates[:, ::-1].astype(np.float32)
    box = cv2.boxPoints(cv2.minAreaRect(points))
    edges = np.roll(box, -1, axis=0) - box
    angles = []
    for edge in edges:
        angle = float(np.degrees(np.arctan2(edge[1], edge[0])))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        angles.append(angle)
    correction = min(angles, key=abs)
    if abs(correction) < 0.1 or abs(correction) > 15:
        return binary_image
    height, width = binary_image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), correction, 1.0)
    return cv2.warpAffine(
        binary_image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_image(image: np.ndarray, threshold_method: str = "adaptive") -> np.ndarray:
    if threshold_method not in {"adaptive", "otsu"}:
        raise ValueError(f"Método de binarização não suportado: {threshold_method}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if gray.shape[0] < 1500:
        scale = 1500 / gray.shape[0]
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10)
    if threshold_method == "adaptive":
        binary = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
    elif threshold_method == "otsu":
        _, binary = cv2.threshold(
            denoised,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )
    return deskew(binary)
