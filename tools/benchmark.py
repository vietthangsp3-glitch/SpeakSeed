"""Small reproducible HTTP load probe. Run only against an authorized beta/staging URL."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import secrets
import time

import httpx


def percentile(values: list[float], quantile: float) -> float:
    if not values: return 0.0
    ordered = sorted(values); index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


async def run(base_url: str, requests: int, concurrency: int, scenario: str) -> dict:
    timeout = httpx.Timeout(30); semaphore = asyncio.Semaphore(concurrency)
    clients: list[httpx.AsyncClient] = []
    marker = secrets.token_hex(5)
    if scenario == "account":
        for index in range(concurrency):
            client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
            response = await client.post("/api/register", json={"name": f"Load {index}", "email": f"load-{marker}-{index}@example.invalid", "password": "benchmark-password"})
            response.raise_for_status(); clients.append(client)
    else:
        clients = [httpx.AsyncClient(base_url=base_url, timeout=timeout) for _ in range(concurrency)]
    latencies: list[float] = []; errors = 0; statuses: dict[str, int] = {}

    async def one(index: int) -> None:
        nonlocal errors
        async with semaphore:
            client = clients[index % len(clients)]
            started = time.perf_counter()
            try:
                if scenario == "account":
                    if index % 2:
                        csrf = client.cookies.get("ss_csrf")
                        response = await client.post("/api/profile", headers={"X-CSRF-Token": csrf},
                                                     json={"daily_goal_minutes": 10 + (index % 5) * 5})
                    else:
                        response = await client.get("/api/dashboard")
                else:
                    paths = ("/api/health/live", "/api/library/stats", "/api/grammar/curriculum", "/api/skills/catalog")
                    response = await client.get(paths[index % len(paths)])
                status = str(response.status_code); statuses[status] = statuses.get(status, 0) + 1
                if response.status_code >= 400: errors += 1
            except Exception:
                errors += 1; statuses["exception"] = statuses.get("exception", 0) + 1
            finally:
                latencies.append((time.perf_counter() - started) * 1000)

    wall = time.perf_counter(); await asyncio.gather(*(one(index) for index in range(requests)))
    duration = time.perf_counter() - wall
    for client in clients: await client.aclose()
    return {"scenario": scenario, "requests": requests, "concurrency": concurrency,
            "duration_seconds": round(duration, 3), "requests_per_second": round(requests / duration, 2),
            "p50_ms": round(percentile(latencies, .50), 2), "p95_ms": round(percentile(latencies, .95), 2),
            "max_ms": round(max(latencies, default=0), 2), "errors": errors,
            "error_rate": round(errors / requests, 4) if requests else 0, "statuses": statuses}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--scenario", choices=("public", "account"), default="public")
    args = parser.parse_args()
    if args.requests < 1 or not 1 <= args.concurrency <= 100: raise SystemExit("requests >= 1, concurrency 1..100")
    print(json.dumps(asyncio.run(run(args.url.rstrip('/'), args.requests, args.concurrency, args.scenario)), ensure_ascii=False))


if __name__ == "__main__": main()

