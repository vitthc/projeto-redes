"""
Sensor simulado: autentica e envia temperatura/umidade a cada intervalo.
Exemplo:  python sensor/sensor.py --id sensor-01 --token <token>
          python sensor/sensor.py --id sensor-02 --token <token> --hot   (força alerta)
"""
import argparse
import asyncio
import json
import random
import time

import websockets


def parse_args():
    ap = argparse.ArgumentParser(description="Sensor simulado")
    ap.add_argument("--id", required=True, help="device_id cadastrado no servidor")
    ap.add_argument("--token", required=True, help="token recebido no cadastro")
    ap.add_argument("--server", default="localhost:8000", help="host:porta do servidor")
    ap.add_argument("--interval", type=float, default=1.0, help="segundos entre leituras")
    ap.add_argument("--hot", action="store_true", help="gera temperatura alta para disparar alerta")
    return ap.parse_args()


async def run(args):
    url = f"ws://{args.server}/ws/sensor"
    seq = 0
    while True:  # reconexão automática
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"type": "AUTH", "device_id": args.id, "token": args.token}))
                resp = json.loads(await ws.recv())
                if resp.get("type") != "AUTH_OK":
                    print(f"[{args.id}] autenticação recusada: {resp}")
                    return
                print(f"[{args.id}] conectado a {url}")
                while True:
                    seq += 1
                    temp = random.uniform(31, 35) if args.hot else random.uniform(20, 28)
                    msg = {
                        "type": "DATA",
                        "device_id": args.id,
                        "seq": seq,
                        "ts": time.time(),
                        "payload": {"temp": round(temp, 1), "hum": round(random.uniform(40, 70), 1)},
                    }
                    await ws.send(json.dumps(msg))
                    await asyncio.sleep(args.interval)
        except (OSError, websockets.exceptions.ConnectionClosed) as e:
            print(f"[{args.id}] conexão perdida ({e}); nova tentativa em 2 s")
            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("encerrado")