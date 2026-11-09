import argparse
import asyncio
import time
import uuid

import cv2
import httpx
import numpy as np


def _synthetic_receipt() -> bytes:
    image = np.full((1400, 1400, 3), 255, dtype=np.uint8)
    lines = (
        "MERCADO SINTETICO",
        "CNPJ: 11.222.333/0001-81",
        "EMISSAO: 14/03/2026 10:30",
        "001 ARROZ TIPO 1 1,000 UN 10,00 10,00",
        "VALOR TOTAL R$ 10,00",
    )
    for index, line in enumerate(lines):
        cv2.putText(
            image, line, (100, 160 + index * 190), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3
        )
    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        raise RuntimeError("Nao foi possivel gerar imagem de smoke test")
    return encoded.tobytes()


async def run_smoke_test(api_url: str, api_key: str, timeout: float) -> None:
    headers = {"X-API-Key": api_key}
    async with httpx.AsyncClient(timeout=10) as client:
        deadline = time.monotonic() + 60
        while True:
            response = await client.get(f"{api_url}/health")
            if response.status_code == 200:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("API nao ficou saudavel no prazo")
            await asyncio.sleep(1)

        payload = _synthetic_receipt()
        response = await client.post(
            f"{api_url}/api/v1/documents",
            headers=headers,
            files={"file": (f"smoke-{uuid.uuid4()}.jpg", payload, "image/jpeg")},
        )
        response.raise_for_status()
        document_id = response.json()["document_id"]
        if response.json()["status"] != "PENDING":
            raise AssertionError(f"Estado inicial inesperado: {response.json()}")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await client.get(f"{api_url}/api/v1/documents/{document_id}", headers=headers)
            result.raise_for_status()
            document = result.json()
            if document["status"] in {"DONE", "NEEDS_REVIEW", "FAILED"}:
                break
            await asyncio.sleep(1)
        else:
            raise TimeoutError(f"Documento {document_id} nao terminou em {timeout}s")

        if document["status"] == "FAILED":
            raise AssertionError(f"Worker falhou: {document.get('error')}")
        if not document.get("extraction", {}).get("raw_text"):
            raise AssertionError("OCR nao produziu texto")
        if not document.get("audit"):
            raise AssertionError("Auditoria nao foi persistida")
        print(
            f"Smoke test aprovado: document_id={document_id}, status={document['status']}, "
            f"campos={sorted(document['extraction'])}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa um upload e OCR real contra a API Compose"
    )
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    asyncio.run(run_smoke_test(args.api_url.rstrip("/"), args.api_key, args.timeout))


if __name__ == "__main__":
    main()
