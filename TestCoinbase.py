#!/usr/bin/env python3
"""Simple Coinbase websocket connectivity test for ticker streams.

This mirrors CoinbaseSocket.py's upstream subscription style:
- Coinbase Exchange websocket feed
- ticker channel for one or more product IDs

Examples:
  python3 TestCoinbase.py --product BTC-USD --count 5
  python3 TestCoinbase.py --product ETH-USD --count 5
  python3 TestCoinbase.py --products BTC-USD,ETH-USD --count 10
"""

import argparse
import asyncio
import json
import sys
import time

try:
    import websockets
except Exception:
    print("ERROR: Missing dependency 'websockets'. Install with: pip3 install websockets", file=sys.stderr)
    raise


WS_ENDPOINTS = {
    "exchange": "wss://ws-feed.exchange.coinbase.com",
    "pro": "wss://ws-feed.pro.coinbase.com",
    "direct": "wss://ws-direct.exchange.coinbase.com",
}


def build_subscribe_message(products: list[str]) -> str:
    return json.dumps({
        "type": "subscribe",
        "channels": [{"name": "ticker", "product_ids": products}],
    })


async def run_test(endpoint: str, products: list[str], count: int, timeout: int) -> int:
    url = WS_ENDPOINTS[endpoint]
    product_text = ",".join(products)
    print(f"[INFO] endpoint={endpoint} products={product_text} channel=ticker")
    print(f"[INFO] connecting: {url}")

    received = 0
    started = time.time()

    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=5) as ws:
            print("[OK] websocket connected")

            subscribe_message = build_subscribe_message(products)
            await ws.send(subscribe_message)
            print(f"[INFO] subscribed: {subscribe_message}")

            while received < count:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(raw)

                event_type = data.get("type")
                if event_type != "ticker":
                    print(f"[INFO] system: type={event_type} payload={data}")
                    continue

                received += 1
                product = data.get("product_id")
                price = data.get("price")
                best_bid = data.get("best_bid")
                best_ask = data.get("best_ask")
                last_size = data.get("last_size")
                trade_time = data.get("time")

                print(
                    f"[{received}/{count}] {product} price={price} "
                    f"bid={best_bid} ask={best_ask} size={last_size} time={trade_time}"
                )

    except asyncio.TimeoutError:
        print(f"[FAIL] timeout: no ticker message within {timeout}s")
        return 2
    except Exception as exc:
        print(f"[FAIL] websocket error: {exc}")
        return 1

    elapsed = time.time() - started
    print(f"[PASS] received {received} ticker messages in {elapsed:.2f}s")
    return 0


def parse_products(product: str | None, products: str | None) -> list[str]:
    raw_products = products if products else product
    parsed = [p.strip().upper() for p in raw_products.split(",") if p.strip()]
    return parsed


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Test Coinbase websocket ticker stream")
    p.add_argument("--endpoint", choices=sorted(WS_ENDPOINTS), default="exchange", help="Coinbase websocket endpoint")
    p.add_argument("--product", default="BTC-USD", help="Product ID, e.g. BTC-USD")
    p.add_argument("--products", help="Comma-separated product IDs, e.g. BTC-USD,ETH-USD")
    p.add_argument("--count", type=int, default=5, help="How many ticker messages to collect")
    p.add_argument("--timeout", type=int, default=15, help="Seconds to wait per ticker message")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    products = parse_products(args.product, args.products)

    if not products:
        print("[FAIL] at least one product is required, e.g. BTC-USD")
        return 2
    if any("-" not in product or not product.replace("-", "").isalnum() for product in products):
        print("[FAIL] product IDs must look like BTC-USD")
        return 2
    if args.count <= 0:
        print("[FAIL] --count must be > 0")
        return 2

    return asyncio.run(run_test(args.endpoint, products, args.count, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
