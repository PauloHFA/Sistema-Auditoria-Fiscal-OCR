import argparse
import asyncio
import json
import math
import statistics
import time
import uuid
from collections.abc import Sequence

import httpx


async def _submit_and_poll(
    client: httpx.AsyncClient,
    api_url: str,
    api_key: str,
    image_path,
    timeout: float,
) -> tuple[float, float, str]:
    started = time.perf_counter()
    image = image_path.read_bytes()
    response = await client.post(
        f"{api_url}/api/v1/documents",
        headers={"X-API-Key": api_key},
        files={"file": (f"{uuid.uuid4()}.png", image, "image/png")},
    )
    response.raise_for_status()
    accepted_at = time.perf_counter()
    document_id = response.json()["document_id"]
    deadline = accepted_at + timeout
    while time.perf_counter() < deadline:
        result = await client.get(
            f"{api_url}/api/v1/documents/{document_id}",
            headers={"X-API-Key": api_key},
        )
        result.raise_for_status()
        document = result.json()
        if document["status"] in {"DONE", "NEEDS_REVIEW", "FAILED"}:
            if document["status"] == "FAILED":
                raise RuntimeError(f"{document_id}: {document.get('error')}")
            return accepted_at - started, time.perf_counter() - accepted_at, document["status"]
        await asyncio.sleep(0.5)
    raise TimeoutError(f"{document_id} nao terminou em {timeout}s")


def _percentile(samples: Sequence[float], percentile: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(math.ceil(len(ordered) * percentile) - 1, len(ordered) - 1)
    return ordered[index]


async def run_load_test(
    api_url: str,
    api_key: str,
    image_paths: list,
    concurrency: int,
    timeout: float,
) -> dict:
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=30) as client:

        async def run_one(image_path):
            async with semaphore:
                return await _submit_and_poll(client, api_url, api_key, image_path, timeout)

        started = time.perf_counter()
        results = await asyncio.gather(*(run_one(path) for path in image_paths))
        wall_time = time.perf_counter() - started
    queue_seconds = [result[0] for result in results]
    processing_seconds = [result[1] for result in results]
    statuses = {
        status: sum(result[2] == status for result in results)
        for status in sorted({result[2] for result in results})
    }
    return {
        "documents": len(results),
        "concurrency": concurrency,
        "wall_time_seconds": round(wall_time, 3),
        "throughput_documents_per_second": round(len(results) / wall_time, 3) if wall_time else 0,
        "upload_latency_seconds": {
            "p50": round(statistics.median(queue_seconds), 3),
            "p95": round(_percentile(queue_seconds, 0.95), 3),
        },
        "processing_latency_seconds": {
            "p50": round(statistics.median(processing_seconds), 3),
            "p95": round(_percentile(processing_seconds, 0.95), 3),
        },
        "statuses": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga concorrente em documentos sinteticos")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--dataset", default="samples/synthetic")
    parser.add_argument("--documents", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    if args.documents < 1 or args.concurrency < 1:
        parser.error("--documents e --concurrency devem ser positivos")
    from pathlib import Path

    images = sorted(Path(args.dataset).glob("*.png"))
    if not images:
        parser.error("dataset vazio; execute scripts/generate_synthetic_dataset.py primeiro")
    if len(images) < args.documents:
        parser.error(
            f"dataset tem {len(images)} imagens; gere ao menos {args.documents} com "
            f"scripts/generate_synthetic_dataset.py --count {args.documents}"
        )
    selected = images[: args.documents]
    report = asyncio.run(
        run_load_test(
            args.api_url.rstrip("/"),
            args.api_key,
            selected,
            args.concurrency,
            args.timeout,
        )
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
