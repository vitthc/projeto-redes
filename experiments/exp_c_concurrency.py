"""
Experimento C — Concorrência (1, 2 e 5 clientes simultâneos).

Para cada cenário:
  * N sensores de teste enviam DATA a uma taxa fixa durante D segundos;
  * cada sensor manda um PING por segundo (RTT sob carga);
  * um painel de teste recebe os UPDATE e mede o atraso fim a fim
        atraso = instante de recebimento no painel − ts gravado pelo sensor
    Sensores e painel rodam neste mesmo processo (mesmo relógio), então o atraso
    é válido mesmo com o servidor em outra máquina.

Exemplos:
  python experiments/exp_c_concurrency.py --server 192.168.0.10:8000 --label lan
  python experiments/exp_c_concurrency.py --server 192.168.0.10:8000 --label lan --clients 1 2 5 10 --rate 20

Saídas:
  results/concurrency_summary.csv                 uma linha por cenário (acumula)
  results/concurrency_delays_<label>_N<n>.csv     atraso de cada mensagem
"""
import argparse
import asyncio
import json
import time

import websockets

from common import (RESULTS, append_csv, environment, fmt_summary, open_sensor, print_environment,
                    r3, register_device, summarize, write_csv)


async def observer(server, ids, delays, ready, stop):
    async with websockets.connect(f"ws://{server}/ws/dashboard", max_size=None) as ws:
        ready.set()
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            m = json.loads(raw)
            if m.get("type") == "UPDATE" and m.get("device_id") in ids:
                delays.append((m["device_id"], m["seq"], (time.time() - m["ts"]) * 1000))


async def client(server, device_id, token, duration, rate, counters):
    ws = await open_sensor(server, device_id, token)
    pending, rtts = {}, []

    async def reader():
        try:
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "PONG":
                    t0 = pending.pop(m.get("seq"), None)
                    if t0 is not None:
                        rtts.append((time.perf_counter() - t0) * 1000)
                elif m.get("type") == "ERROR":
                    counters["erros"] += 1
        except websockets.exceptions.ConnectionClosed:
            pass

    rt = asyncio.create_task(reader())
    start = time.perf_counter()
    next_send, next_ping = start, start
    seq = pseq = 0
    while time.perf_counter() - start < duration:
        now = time.perf_counter()
        if now >= next_ping:
            pseq += 1
            pending[pseq] = time.perf_counter()
            await ws.send(json.dumps({"type": "PING", "seq": pseq, "ts": time.time()}))
            next_ping += 1.0
        seq += 1
        await ws.send(json.dumps({"type": "DATA", "device_id": device_id, "seq": seq, "ts": time.time(),
                                  "payload": {"temp": 25.0, "hum": 50.0}}))
        next_send += 1 / rate
        await asyncio.sleep(max(0.0, next_send - time.perf_counter()))
    await asyncio.sleep(1.0)  # aguarda PONGs atrasados
    await ws.close()
    await rt
    return seq, rtts


async def scenario(args, n):
    devs = [register_device(args.server, "exp-c") for _ in range(n)]
    ids = {d for d, _ in devs}
    delays, counters = [], {"erros": 0}
    ready, stop = asyncio.Event(), asyncio.Event()
    obs = asyncio.create_task(observer(args.server, ids, delays, ready, stop))
    await asyncio.wait_for(ready.wait(), timeout=5)

    results = await asyncio.gather(*(client(args.server, d, t, args.duration, args.rate, counters)
                                     for d, t in devs))
    await asyncio.sleep(1.0)
    stop.set()
    await obs

    sent = sum(r[0] for r in results)
    rtts = [x for r in results for x in r[1]]
    return sent, delays, rtts, counters["erros"]


def main():
    ap = argparse.ArgumentParser(description="Experimento C — Concorrência")
    ap.add_argument("--server", default="localhost:8000")
    ap.add_argument("--label", required=True)
    ap.add_argument("--clients", type=int, nargs="+", default=[1, 2, 5])
    ap.add_argument("--duration", type=float, default=30, help="duração de cada cenário (s)")
    ap.add_argument("--rate", type=float, default=10, help="mensagens DATA por segundo, por cliente")
    args = ap.parse_args()

    print_environment(args.server)
    env = environment(args.server)
    for n in args.clients:
        print(f"\nCenário: {n} cliente(s), {args.rate} msgs/s cada, {args.duration} s…")
        sent, delays, rtts, errors = asyncio.run(scenario(args, n))
        recv = len(delays)
        ds = summarize([d[2] for d in delays])
        rs = summarize(rtts)
        print(f"  enviadas={sent}  recebidas no painel={recv}  perdidas={sent - recv}  erros={errors}")
        print(f"  taxa recebida: {recv / args.duration:.1f} msgs/s")
        print(f"  atraso sensor→painel: {fmt_summary(ds)}")
        print(f"  RTT PING/PONG:        {fmt_summary(rs)}")

        write_csv(RESULTS / f"concurrency_delays_{args.label}_N{n}.csv",
                  ["device_id", "seq", "atraso_ms"], [[d, s, r3(x)] for d, s, x in delays])
        append_csv(RESULTS / "concurrency_summary.csv",
                   ["condicao", "clientes", "duracao_s", "taxa_por_cliente", "enviadas", "recebidas_painel",
                    "perdidas", "erros", "taxa_envio_msgs_s", "taxa_recebida_msgs_s",
                    "atraso_media_ms", "atraso_mediana_ms", "atraso_dp_ms", "atraso_p95_ms", "atraso_max_ms",
                    "rtt_media_ms", "rtt_mediana_ms", "rtt_p95_ms", *env.keys()],
                   [args.label, n, args.duration, args.rate, sent, recv, sent - recv, errors,
                    round(sent / args.duration, 2), round(recv / args.duration, 2),
                    r3(ds["media"]), r3(ds["mediana"]), r3(ds["desvio_padrao"]), r3(ds["p95"]), r3(ds["max"]),
                    r3(rs["media"]), r3(rs["mediana"]), r3(rs["p95"]), *env.values()])
    print("\nGravado em results/concurrency_summary.csv")


if __name__ == "__main__":
    main()
