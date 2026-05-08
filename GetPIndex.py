#!/usr/bin/env python3
"""Get latest 1m spot bars from Binance and Coinbase, then print PIndex.

PIndex is calculated as:
  Binance close price - Coinbase close price

Examples:
  python3 GetPIndex.py
  python3 GetPIndex.py --symbols BTC,ETH
  python3 GetPIndex.py --timeout 20
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import requests


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/{product}/candles"
COINBASE_ADVANCED_CANDLES_URL = "https://api.coinbase.com/api/v3/brokerage/market/products/{product}/candles"

DEFAULT_SYMBOLS = ["BTC", "ETH"]
QUOTE = "USD"


@dataclass(frozen=True)
class Bar:
    exchange: str
    symbol: str
    timetag: str
    price: Decimal


def utc_iso_from_seconds(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def utc_iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def parse_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc


def binance_symbol(symbol: str) -> str:
    return f"{symbol}USDT"


def coinbase_product(symbol: str) -> str:
    return f"{symbol}-{QUOTE}"


def get_binance_latest_1m(symbol: str, timeout: int) -> Bar:
    api_symbol = binance_symbol(symbol)
    params = {
        "symbol": api_symbol,
        "interval": "1m",
        "limit": 1,
    }

    payload = http_get_json(BINANCE_KLINES_URL, params=params, timeout=timeout)

    if not payload:
        raise RuntimeError(f"Binance returned no 1m bar for {api_symbol}")

    latest = payload[-1]
    open_time_ms = int(latest[0])
    close_price = parse_decimal(latest[4])

    return Bar(
        exchange="Binance",
        symbol=api_symbol,
        timetag=utc_iso_from_ms(open_time_ms),
        price=close_price,
    )


def get_coinbase_latest_1m(symbol: str, timeout: int) -> Bar:
    product = coinbase_product(symbol)
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=10)
    headers = {
        "User-Agent": "arxCloud-GetPIndex/1.0",
        "Accept": "application/json",
    }
    advanced_params = {
        "granularity": "ONE_MINUTE",
        "start": str(int(start.timestamp())),
        "end": str(int(now.timestamp())),
    }
    exchange_params = {
        "granularity": 60,
    }

    try:
        payload = http_get_json(
            COINBASE_ADVANCED_CANDLES_URL.format(product=product),
            params=advanced_params,
            headers=headers,
            timeout=timeout,
        )
        candles = payload.get("candles", []) if isinstance(payload, dict) else []
        if candles:
            latest = max(candles, key=lambda candle: int(candle["start"]))
            return Bar(
                exchange="Coinbase",
                symbol=product,
                timetag=utc_iso_from_seconds(int(latest["start"])),
                price=parse_decimal(latest["close"]),
            )
    except Exception:
        pass

    payload = http_get_json(
        COINBASE_CANDLES_URL.format(product=product),
        params=exchange_params,
        headers=headers,
        timeout=timeout,
    )

    if not payload:
        raise RuntimeError(f"Coinbase returned no 1m bar for {product}")

    # Coinbase candles are [start, low, high, open, close, volume] and may not
    # be sorted consistently, so choose the newest start timestamp explicitly.
    latest = max(payload, key=lambda candle: int(candle[0]))
    start_seconds = int(latest[0])
    close_price = parse_decimal(latest[4])

    return Bar(
        exchange="Coinbase",
        symbol=product,
        timetag=utc_iso_from_seconds(start_seconds),
        price=close_price,
    )


def print_bar(bar: Bar) -> None:
    print(f"{bar.exchange:<8} {bar.symbol:<8} timetag={bar.timetag} price={bar.price}")


def http_get_json(url: str, params: dict[str, object] | None = None, headers: dict[str, str] | None = None,
                  timeout: int = 15) -> object:
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def parse_symbols(raw: str) -> list[str]:
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    if not symbols:
        raise ValueError("at least one symbol is required")
    if any(not symbol.isalnum() for symbol in symbols):
        raise ValueError("symbols must be alphanumeric, e.g. BTC,ETH")
    return symbols


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Get latest 1m BTC/ETH spot bars from Binance and Coinbase, then print PIndex"
    )
    p.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated base symbols, e.g. BTC,ETH",
    )
    p.add_argument("--timeout", type=int, default=15, help="REST request timeout in seconds")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.timeout <= 0:
        print("[FAIL] --timeout must be > 0")
        return 2

    try:
        symbols = parse_symbols(args.symbols)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 2

    print("[INFO] latest 1m spot bars")

    exit_code = 0
    for symbol in symbols:
        try:
            binance_bar = get_binance_latest_1m(symbol, args.timeout)
            coinbase_bar = get_coinbase_latest_1m(symbol, args.timeout)
            pindex = binance_bar.price - coinbase_bar.price

            print()
            print_bar(binance_bar)
            print_bar(coinbase_bar)
            print(f"PIndex   {symbol:<8} Binance-Coinbase={pindex}")

        except requests.HTTPError as exc:
            print(f"\n[FAIL] {symbol}: HTTP error: {exc}", file=sys.stderr)
            exit_code = 1
        except requests.RequestException as exc:
            print(f"\n[FAIL] {symbol}: request error: {exc}", file=sys.stderr)
            exit_code = 1
        except Exception as exc:
            print(f"\n[FAIL] {symbol}: {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
