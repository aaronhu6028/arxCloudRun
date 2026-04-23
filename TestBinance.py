#!/usr/bin/env python3
"""Simple Binance websocket connectivity test for arxPacker quote streams.

This mirrors arxPacker's quote subscription style:
- Spot aggTrade stream
- USD-M Futures aggTrade stream

Examples:
  python3 TestBinance.py --market futures --symbol BTCUSDT --count 5
  python3 TestBinance.py --market spot --symbol ETHUSDT --count 5
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone

try:
    import websockets
except Exception:
    print("ERROR: Missing dependency 'websockets'. Install with: pip3 install websockets", file=sys.stderr)
    raise


WS_ENDPOINTS = {
    "futures": "wss://fstream.binance.com/ws/{stream}",
    "spot": "wss://stream.binance.com:9443/ws/{stream}",
}


def build_url(market: str, symbol: str) -> str:
    stream = f"{symbol.lower()}@aggTrade"
    return WS_ENDPOINTS[market].format(stream=stream)


def format_ts(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.isoformat()


async def run_test(market: str, symbol: str, count: int, timeout: int) -> int:
    url = build_url(market, symbol)
    print(f"[INFO] market={market} symbol={symbol} stream=aggTrade")
    print(f"[INFO] connecting: {url}")

    received = 0
    started = time.time()

    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=5) as ws:
            print("[OK] websocket connected")

            while received < count:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(raw)

                # aggTrade core fields
                event = data.get("e")
                trade_time = data.get("T")
                price = data.get("p")
                qty = data.get("q")
                symbol_recv = data.get("s")

                received += 1
                if event != "aggTrade":
                    print(f"[WARN] unexpected event={event} payload={data}")
                    continue

                tstr = format_ts(trade_time) if isinstance(trade_time, int) else str(trade_time)
                print(
                    f"[{received}/{count}] {symbol_recv} price={price} qty={qty} trade_time={tstr}"
                )

    except asyncio.TimeoutError:
        print(f"[FAIL] timeout: no message within {timeout}s")
        return 2
    except Exception as exc:
        print(f"[FAIL] websocket error: {exc}")
        return 1

    elapsed = time.time() - started
    print(f"[PASS] received {received} aggTrade messages in {elapsed:.2f}s")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Test Binance websocket quote stream (aggTrade)")
    p.add_argument("--market", choices=["futures", "spot"], default="futures", help="Binance market type")
    p.add_argument("--symbol", default="BTCUSDT", help="Trading symbol, e.g. BTCUSDT")
    p.add_argument("--count", type=int, default=5, help="How many aggTrade messages to collect")
    p.add_argument("--timeout", type=int, default=15, help="Seconds to wait per message")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.symbol.strip().upper()

    if not symbol.isalnum():
        print("[FAIL] symbol must be alphanumeric, e.g. BTCUSDT")
        return 2
    if args.count <= 0:
        print("[FAIL] --count must be > 0")
        return 2

    return asyncio.run(run_test(args.market, symbol, args.count, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())