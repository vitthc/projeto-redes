"""
Experimento A — RTT e tempo de resposta.

  --mode ws    RTT de aplicação: PING/PONG pelo WebSocket (conexão TCP já aberta)
  --mode http  tempo de resposta de GET /health (cada requisição abre uma conexão TCP nova)

Exemplos:
  python experiments/exp_a_rtt.py --server localhost:8000 --label localhost
  python experiments/exp_a_rtt.py --server 192.168.0.10:8000 --label lan
  python experiments/exp_a_rtt.py --server 192.168.0.10:8000 --label lan --mode http
  python experiments/exp_a_rtt.py --server 192.168.0.10:8000 --label lan_netem100ms

Saídas:
  results/rtt_raw_<label>_<mode>.csv   uma linha por medição
  results/rtt_summary.csv              uma linha por execução (acumula)
"""
import argparse
import asyncio
import json
import time

import websockets

from common import (HTTP, RESULTS, append_csv, environment, fmt_summary, print_environment,
                    r3, summarize, write_csv)


async def rtt_ws(server: str, total: int, interval: float) -> list:
    out = []
    async with websockets.connect(f"ws://{server}/ws/dashboard", max_size=None) as ws:
        for seq in range(1, total + 1):
            t0 = time.perf_counter()
            await ws.send(json.dumps({"type": "PING", "seq": seq, "ts": time.time()}))
            while True:  # ignora UPDATE/ALERT que cheguem no meio
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if m.get("type") == "PONG" and m.get("seq") == seq:
                    break
            out.append((time.perf_counter() - t0) * 1000)
            await asyncio.sleep(interval)
    return out


def rtt_http(server: str, total: int, interval: float) -> list:
    out = []
    for _ in range(total):
        t0 = time.perf_counter()
        with HTTP.open(f"http://{server}/health", timeout=10) as r:
            r.read()
        out.append((time.perf_counter() - t0) * 1000)
        time.sleep(interval)
    return out


def main():
    ap = argparse.ArgumentParser(description="Experimento A — RTT")
    ap.add_argument("--server", default="localhost:8000")
    ap.add_argument("--label", required=True, help="nome da condição (ex.: localhost, lan, lan_netem)")
    ap.add_argument("--mode", choices=["ws", "http"], default="ws")
    ap.add_argument("-n", type=int, default=30, help="medições válidas (mínimo 30 pelo enunciado)")
    ap.add_argument("--warmup", type=int, default=3, help="medições iniciais descartadas")
    ap.add_argument("--interval", type=float, default=0.2, help="pausa entre medições (s)")
    args = ap.parse_args()

    print_environment(args.server)
    total = args.n + args.warmup
    print(f"\nModo {args.mode}: {total} medições ({args.warmup} de aquecimento descartadas)…")
    if args.mode == "ws":
        values = asyncio.run(rtt_ws(args.server, total, args.interval))
    else:
        values = rtt_http(args.server, total, args.interval)
    values = values[args.warmup:]

    s = summarize(values)
    print(f"\nResultado [{args.label} / {args.mode}]: {fmt_summary(s)}")

    raw = RESULTS / f"rtt_raw_{args.label}_{args.mode}.csv"
    write_csv(raw, ["medicao", "rtt_ms"], [[i + 1, r3(v)] for i, v in enumerate(values)])
    env = environment(args.server)
    append_csv(RESULTS / "rtt_summary.csv",
               ["condicao", "modo", "n", "media_ms", "mediana_ms", "desvio_padrao_ms", "min_ms", "max_ms",
                "p95_ms", "intervalo_s", *env.keys()],
               [args.label, args.mode, s["n"], r3(s["media"]), r3(s["mediana"]), r3(s["desvio_padrao"]),
                r3(s["min"]), r3(s["max"]), r3(s["p95"]), args.interval, *env.values()])
    print(f"Gravado em {raw} e results/rtt_summary.csv")


if __name__ == "__main__":
    main()
