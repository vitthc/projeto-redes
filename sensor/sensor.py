import asyncio, json, random, sys, time
import websockets

DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "sensor-01"
URL = "ws://localhost:8000/ws/sensor"

async def main():
    async with websockets.connect(URL) as ws:
        seq = 0
        while True:
            seq += 1
            msg = {"type": "DATA", "device_id": DEVICE_ID, "seq": seq,
                   "ts": time.time(), "payload": {"temp": round(random.uniform(20, 32), 1)}}
            await ws.send(json.dumps(msg))
            await asyncio.sleep(1)

asyncio.run(main())