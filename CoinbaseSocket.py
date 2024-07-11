import asyncio
import json
import websockets

import logging
logfile = './Log/coinbaseSocket.log'
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(logfile),
        logging.StreamHandler()
    ])

log = logging.getLogger('')

def logit(*args, **kwargs):
    log.info(*args, **kwargs)
  
# Coinbase WebSocket URL
COINBASE_WS_URL = "wss://ws-feed.pro.coinbase.com"

# Clients connected to the broadcast server
connected_clients = set()

async def coinbase_ws_handler():
    reconnect_delay = 10  # Initial reconnect delay (in seconds)
    max_delay = 120  # Maximum delay (in seconds)
    while True:
        try:
            async with websockets.connect(COINBASE_WS_URL) as websocket:
                # Reset the reconnect delay upon a successful connection
                reconnect_delay = 1

                # Subscribe to the BTC-USD ticker channel
                subscribe_message = json.dumps({
                    "type": "subscribe",
                    "channels": [{"name": "ticker", "product_ids": ["BTC-USD"]}]
                })
                await websocket.send(subscribe_message)

                last_ts = ''
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    if data.get('type') == 'ticker':
                        await broadcast(data)
                        t = data.get('time')
                        ts = t[:16]
                        if ts != last_ts:
                            last_ts = ts
                            logit(f"ticker: product_id={data.get('product_id')} time={data.get('time')} price={data.get('price')}")
                    else:
                        logit(f"{data.get('type')}: {data}")

        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosed):
            logit(f"Connection to Coinbase closed, retrying in {reconnect_delay} seconds...")
        except Exception as e:
            logit(f"Unexpected error: {e}, retrying in {reconnect_delay} seconds...")

        # Wait for the reconnect delay before attempting to reconnect
        await asyncio.sleep(reconnect_delay)
        # Increment the reconnect delay (with a maximum limit)
        reconnect_delay = min(reconnect_delay * 2, max_delay)

async def broadcast(data):
    if connected_clients:
        message = json.dumps(data)
        tasks = [client.send(message) for client in connected_clients]
        await asyncio.gather(*tasks)

async def client_handler(websocket, path):
    addr = websocket.remote_address
    connected_clients.add(websocket)
    logit(f"Client connected from {addr}")
    try:
        await websocket.wait_closed()
        logit(f"after {addr} wait_closed, disconnected")
    except websockets.exceptions.ConnectionClosedError:
        logit(f"ConnectionClosedError: Client {addr} disconnected.")
    finally:
        connected_clients.remove(websocket)

async def main():
    # Start the Coinbase WebSocket handler
    coinbase_task = asyncio.create_task(coinbase_ws_handler())

    # Start the WebSocket server for broadcasting data to clients
    server = await websockets.serve(client_handler, "localhost", 6789, 
                ping_interval=None, ping_timeout=None)
    logit("Server start at ws://localhost:6789")

    # Run both tasks concurrently
    await asyncio.gather(coinbase_task, server.wait_closed())

if __name__ == "__main__":
    asyncio.run(main())
