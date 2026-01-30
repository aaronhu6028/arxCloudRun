import asyncio
import json
import websockets
import logging
import os
from logging.handlers import TimedRotatingFileHandler

# 自定義 Handler：確保每次 emit 後都立即 flush
class FlushedTimedRotatingFileHandler(TimedRotatingFileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()  # 強制寫入硬碟

# 確保 Log 資料夾存在
log_dir = './Log'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logfile = os.path.join(log_dir, 'coinbaseSocket.log')

# 使用我們自定義的 Flush Handler
file_handler = FlushedTimedRotatingFileHandler(
    logfile,
    when="midnight",
    interval=1,
    backupCount=7,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

# 設定 StreamHandler (螢幕輸出)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

# 全域 Logging 設定
log = logging.getLogger('')
log.setLevel(logging.INFO)
log.addHandler(file_handler)
log.addHandler(stream_handler)

def logit(*args, **kwargs):
    log.info(*args, **kwargs)

# Coinbase WebSocket URL
COINBASE_WS_URLS = [
    "wss://ws-feed.pro.coinbase.com", 
    "wss://ws-feed.exchange.coinbase.com", 
    "wss://ws-direct.exchange.coinbase.com"
]

connected_clients = set()

async def coinbase_ws_handler():
    reconnect_delay = 1
    max_delay = 120
    ws_select = 0
    
    while True:
        try:
            ws_url = COINBASE_WS_URLS[ws_select]
            ws_select = (ws_select + 1) % len(COINBASE_WS_URLS)
            
            logit(f"Connecting to {ws_url}...")
            async with websockets.connect(ws_url) as websocket:
                reconnect_delay = 1

                subscribe_message = json.dumps({
                    "type": "subscribe",
                    "channels": [{"name": "ticker", "product_ids": ["BTC-USD", "ETH-USD"]}]
                })
                await websocket.send(subscribe_message)

                last_ts = {}
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    if data.get('type') == 'ticker':
                        await broadcast(data)
                        
                        t = data.get('time', '')
                        product = data.get('product_id')
                        ts = t[:16] # 擷取到分鐘
                        
                        if ts != last_ts.get(product):
                            last_ts[product] = ts
                            logit(f"ticker: n={len(connected_clients)} product={product} price={data.get('price')}")
                    else:
                        logit(f"System: {data.get('type')}")

        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosed):
            logit(f"Connection closed, retrying in {reconnect_delay}s...")
        except Exception as e:
            logit(f"Unexpected error: {e}, retrying in {reconnect_delay}s...")

        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, max_delay)

async def broadcast(data):
    if connected_clients:
        message = json.dumps(data)
        tasks = [asyncio.create_task(client.send(message)) for client in connected_clients]
        if tasks:
            await asyncio.wait(tasks)

async def client_handler(websocket, path=None):
    addr = websocket.remote_address
    connected_clients.add(websocket)
    logit(f"Client connected from {addr}")
    try:
        await websocket.wait_closed()
    except Exception:
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logit(f"Client {addr} disconnected")

async def main():
    coinbase_task = asyncio.create_task(coinbase_ws_handler())

    async with websockets.serve(client_handler, "localhost", 6789, 
                               ping_interval=None, ping_timeout=None):
        logit("Local Server started at ws://localhost:6789")
        await coinbase_task

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logit("Server stopped by user.")