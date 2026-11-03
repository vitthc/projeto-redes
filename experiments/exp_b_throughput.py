"""
Experimento B — Throughput da aplicação.

Um sensor de teste envia N mensagens DATA com carga útil de tamanho fixo (campo "pad")
e, no fim, um PING. Como o WebSocket roda sobre TCP (entrega ordenada) e o servidor
processa as mensagens em ordem, o PONG só volta depois que todas as DATA foram
validadas, gravadas e repassadas. Assim:

    throughput útil = (N × tamanho da carga) / (tempo do 1º envio até receber o PONG)

Exemplos:
  python experiments/exp_b_throughput.py --server 192.168.0.10:8000 --label lan
  python experiments/exp_b_throughput.py --server localhost:8000 --label localhost --sizes 100 1000 10000 100000 --count 200

Saída: results/throughput_<label>.csv
"""
import argparse
import asyncio
import json
import statistics
import time

from common import RESULTS, environment, open_sensor, print_environment, register_device, write_csv


async def run(args):
    device_id, token = register_device(args.server, "exp-b")
    print(f"Sensor de teste cadastrado: {device_id}\n")
    ws = await open_sensor(args.server, device_id, token)
    seq = ping_seq = 0
    rows = []
    try:
        for size in args.sizes:
            pad = "x" * size
            for rep in range(1, args.reps + 1):
                wire = 0
                t0 = time.perf_counter()
                for _ in range(args.count):
                    seq += 1
                    text = json.dumps({"type": "DATA", "device_id": device_id, "seq": seq, "ts": time.time(),
                                       "payload": {"temp": 25.0, "hum": 50.0, "pad": pad}})
                    wire += len(text.encode())
                    await ws.send(text)
                ping_seq += 1
                await ws.send(json.dumps({"type": "PING", "seq": ping_seq, "ts": time.time()}))
                errors = 0
                while True:
                    m = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                    if m.get("type") == "PONG" and m.get("seq") == ping_seq:
                        break
                    if m.get("type") == "ERROR":
                        errors += 1
                elapsed = time.perf_counter() - t0
                useful = size * args.count
                kbps = useful / elapsed / 1000
                mbps = useful * 8 / elapsed / 1e6
                rate = args.count / elapsed
                print(f"  carga {size:>7} B  rep {rep}: {elapsed:7.3f} s  {kbps:10.1f} kB/s  "
                      f"{mbps:8.3f} Mbit/s  {rate:8.1f} msgs/s  erros={errors}")
                rows.append([args.label, size, rep, args.count, round(elapsed, 4), useful, wire,
                             round(kbps, 2), round(mbps, 4), round(rate, 1), errors])
                await asyncio.sleep(args.pause)
    finally:
        await ws.close()
    return rows


def main():
    ap = argparse.ArgumentParser(description="Experimento B — Throughput")
    ap.add_argument("--server", default="localhost:8000")
    ap.add_argument("--label", required=True)
    ap.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 10000, 100000],
                    help="tamanhos da carga útil em bytes")
    ap.add_argument("--count", type=int, default=200, help="mensagens por repetição")
    ap.add_argument("--reps", type=int, default=3, help="repetições por tamanho")
    ap.add_argument("--pause", type=float, default=0.5, help="pausa entre repetições (s)")
    args = ap.parse_args()

    print_environment(args.server)
    print()
    rows = asyncio.run(run(args))

    print("\nMédia por tamanho de carga:")
    for size in args.sizes:
        v = [r[8] for r in rows if r[1] == size]
        sd = statistics.stdev(v) if len(v) > 1 else 0.0
        print(f"  {size:>7} B: {statistics.fmean(v):.3f} Mbit/s (dp {sd:.3f})")

    env = environment(args.server)
    out = RESULTS / f"throughput_{args.label}.csv"
    write_csv(out, ["condicao", "tamanho_carga_bytes", "repeticao", "mensagens", "segundos", "bytes_uteis",
                    "bytes_mensagens_ws", "throughput_kBps", "throughput_Mbps", "msgs_por_s", "erros",
                    *env.keys()],
              [r + list(env.values()) for r in rows])
    print(f"\nGravado em {out}")


if __name__ == "__main__":
    main()
