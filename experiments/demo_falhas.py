"""
Demonstração do tratamento de falhas do protocolo (para o vídeo).

Envia ao servidor, passo a passo, mensagens inválidas e mostra a resposta de cada uma:
  1. token errado              -> ERROR AUTH_FAILED e a conexão é fechada
  2. JSON malformado           -> ERROR INVALID_MSG, a conexão continua
  3. campo obrigatório ausente -> ERROR INVALID_MSG
  4. temperatura fora da faixa -> ERROR OUT_OF_RANGE
  5. tipo desconhecido         -> ERROR UNKNOWN_TYPE
  6. DATA válido               -> aceito (aparece no painel), provando que a conexão sobreviveu

Uso:  python experiments/demo_falhas.py --server localhost:8000
      (Enter avança cada passo; --auto roda tudo sem pausas)
"""
import argparse
import asyncio
import json
import time

import websockets

from common import register_device


def show(direction, text):
    print(f"  {direction} {text}")


async def step(ws, title, raw, auto):
    print(f"\n[{title}]")
    if not auto:
        input("  (Enter para enviar) ")
    show("->", raw)
    await ws.send(raw)
    try:
        resp = await asyncio.wait_for(ws.recv(), timeout=1.5)
        show("<-", resp)
    except asyncio.TimeoutError:
        show("<-", "(sem resposta: mensagem aceita)")


async def main(args):
    url = f"ws://{args.server}/ws/sensor"
    device_id, token = register_device(args.server, "demo-falhas")
    print(f"Sensor de demonstração cadastrado: {device_id}")

    print("\n[1. Autenticação com token errado]")
    if not args.auto:
        input("  (Enter para enviar) ")
    async with websockets.connect(url) as ws:
        raw = json.dumps({"type": "AUTH", "device_id": device_id, "token": "token-errado"})
        show("->", raw)
        await ws.send(raw)
        show("<-", await ws.recv())
        try:
            await ws.recv()
        except websockets.exceptions.ConnectionClosed as e:
            show("xx", f"conexão fechada pelo servidor (código {e.rcvd.code if e.rcvd else '?'})")

    async with websockets.connect(url) as ws:
        print("\n[Autenticação com o token correto]")
        raw = json.dumps({"type": "AUTH", "device_id": device_id, "token": token})
        show("->", raw[:60] + "...")
        await ws.send(raw)
        show("<-", await ws.recv())

        await step(ws, "2. JSON malformado", '{"type": "DATA", "device_id": ', args.auto)
        await step(ws, "3. Campo obrigatório ausente (sem seq)",
                   json.dumps({"type": "DATA", "device_id": device_id, "ts": time.time(),
                               "payload": {"temp": 25.0}}), args.auto)
        await step(ws, "4. Temperatura fora da faixa (-40 a 85 °C)",
                   json.dumps({"type": "DATA", "device_id": device_id, "seq": 1, "ts": time.time(),
                               "payload": {"temp": 500.0, "hum": 50.0}}), args.auto)
        await step(ws, "5. Tipo de mensagem desconhecido",
                   json.dumps({"type": "HELLO", "device_id": device_id}), args.auto)
        await step(ws, "6. DATA válido na mesma conexão",
                   json.dumps({"type": "DATA", "device_id": device_id, "seq": 2, "ts": time.time(),
                               "payload": {"temp": 24.5, "hum": 55.0}}), args.auto)
    print("\nFim: os erros foram rejeitados sem derrubar a conexão nem o servidor.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Demonstração de falhas")
    ap.add_argument("--server", default="localhost:8000")
    ap.add_argument("--auto", action="store_true", help="sem pausas entre os passos")
    asyncio.run(main(ap.parse_args()))
