"""
Experimento D — Microteste TCP × UDP com sockets puros (fora da aplicação).

O mesmo programa é servidor de eco (TCP e UDP na mesma porta) e cliente.
O cliente envia N pacotes numerados, de mesmo tamanho e no mesmo ritmo, pelos dois
protocolos, e mede: RTT de cada pacote, perdas, chegadas fora de ordem e duplicatas.

Formato do pacote: seq (uint32) + instante de envio (double) + enchimento até --size bytes.
No TCP, cada pacote vai precedido de 4 bytes de tamanho (TCP é um fluxo de bytes e não
preserva fronteiras de mensagem; o UDP preserva). TCP_NODELAY desliga o algoritmo de Nagle
para que pacotes pequenos não sejam agrupados, deixando a comparação justa.

Uso:
  Máquina servidora:  python experiments/exp_d_tcp_udp.py server --port 9001
  Máquina cliente:    python experiments/exp_d_tcp_udp.py client --host 192.168.0.10 --label lan
                      python experiments/exp_d_tcp_udp.py client --host 192.168.0.10 --label lan_perda5 -n 2000

Saídas:
  results/tcp_udp_summary.csv                    uma linha por protocolo e execução
  results/tcp_udp_raw_<label>_<proto>.csv        RTT de cada pacote recebido
"""
import argparse
import socket
import struct
import threading
import time

from common import RESULTS, append_csv, environment, fmt_summary, print_environment, r3, summarize, write_csv

HDR = struct.Struct("!Id")   # seq, instante de envio (perf_counter do cliente)
LEN = struct.Struct("!I")    # prefixo de tamanho (só TCP)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("conexão fechada")
        buf += chunk
    return bytes(buf)


# ------------------------------------------------------------------ servidor de eco
def tcp_session(conn, addr):
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    count = 0
    try:
        while True:
            (n,) = LEN.unpack(recv_exact(conn, LEN.size))
            data = recv_exact(conn, n)
            conn.sendall(LEN.pack(n) + data)
            count += 1
    except (ConnectionError, OSError):
        pass
    finally:
        conn.close()
        print(f"[TCP] {addr[0]}:{addr[1]} encerrou após {count} pacotes")


def serve_tcp(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen()
    print(f"[TCP] eco escutando em {host}:{port}")
    while True:
        conn, addr = s.accept()
        print(f"[TCP] conexão de {addr[0]}:{addr[1]}")
        threading.Thread(target=tcp_session, args=(conn, addr), daemon=True).start()


def serve_udp(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((host, port))
    print(f"[UDP] eco escutando em {host}:{port}")
    while True:
        data, addr = s.recvfrom(65535)
        s.sendto(data, addr)


def run_server(args):
    threading.Thread(target=serve_tcp, args=(args.bind, args.port), daemon=True).start()
    threading.Thread(target=serve_udp, args=(args.bind, args.port), daemon=True).start()
    print("Ctrl+C para encerrar.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("encerrado")


# ------------------------------------------------------------------ cliente
def run_proto(proto, host, port, n, size, interval, timeout):
    size = max(size, HDR.size)
    pad = b"\0" * (size - HDR.size)
    received = {}            # seq -> rtt_ms
    arrival = []             # ordem de chegada
    st = {"dup": 0, "ooo": 0, "max_seq": -1, "last": None, "send_err": 0}
    stop = threading.Event()

    def on_packet(data, t):
        seq, t0 = HDR.unpack_from(data)
        if seq in received:
            st["dup"] += 1
            return
        if seq < st["max_seq"]:
            st["ooo"] += 1
        st["max_seq"] = max(st["max_seq"], seq)
        received[seq] = (t - t0) * 1000
        arrival.append(seq)
        st["last"] = t

    if proto == "tcp":
        sock = socket.create_connection((host, port), timeout=5)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(None)

        def receiver():
            try:
                while len(received) < n:
                    (ln,) = LEN.unpack(recv_exact(sock, LEN.size))
                    data = recv_exact(sock, ln)
                    on_packet(data, time.perf_counter())
            except (ConnectionError, OSError):
                pass

        def send(pkt):
            sock.sendall(LEN.pack(len(pkt)) + pkt)
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((host, port))
        sock.settimeout(0.2)

        def receiver():
            while not stop.is_set() and len(received) < n:
                try:
                    data = sock.recv(65535)
                except socket.timeout:
                    continue
                except ConnectionRefusedError:   # ICMP "port unreachable"
                    continue
                except OSError:
                    break
                on_packet(data, time.perf_counter())

        def send(pkt):
            sock.send(pkt)

    th = threading.Thread(target=receiver, daemon=True)
    th.start()

    t_start = time.perf_counter()
    next_t = t_start
    for seq in range(n):
        try:
            send(HDR.pack(seq, time.perf_counter()) + pad)
        except OSError:
            st["send_err"] += 1
        next_t += interval
        d = next_t - time.perf_counter()
        if d > 0:
            time.sleep(d)
    t_sent = time.perf_counter()

    deadline = t_sent + timeout
    while len(received) < n and time.perf_counter() < deadline:
        time.sleep(0.01)
    stop.set()
    try:
        sock.close()
    except OSError:
        pass
    th.join(1)

    elapsed = (st["last"] or time.perf_counter()) - t_start
    got = len(received)
    return {
        "proto": proto.upper(), "enviados": n, "recebidos": got, "perdidos": n - got,
        "perda_pct": 100 * (n - got) / n, "fora_de_ordem": st["ooo"], "duplicados": st["dup"],
        "erros_envio": st["send_err"], "tempo_s": elapsed, "tempo_envio_s": t_sent - t_start,
        "goodput_kBps": got * size / elapsed / 1000 if elapsed > 0 else 0.0,
        "rtt": summarize(received.values()), "raw": [(s, received[s]) for s in arrival], "size": size,
    }


def run_client(args):
    print_environment(f"{args.host}:{args.port}")
    env = environment(f"{args.host}:{args.port}")
    protos = ["tcp", "udp"] if args.proto == "both" else [args.proto]
    for proto in protos:
        print(f"\n{proto.upper()}: {args.n} pacotes de {args.size} B, intervalo {args.interval * 1000:.2f} ms…")
        r = run_proto(proto, args.host, args.port, args.n, args.size, args.interval, args.timeout)
        print(f"  recebidos {r['recebidos']}/{r['enviados']}  perdidos {r['perdidos']} ({r['perda_pct']:.2f} %)  "
              f"fora de ordem {r['fora_de_ordem']}  duplicados {r['duplicados']}")
        print(f"  tempo total {r['tempo_s']:.3f} s  goodput {r['goodput_kBps']:.1f} kB/s")
        print(f"  RTT: {fmt_summary(r['rtt'])}")
        write_csv(RESULTS / f"tcp_udp_raw_{args.label}_{proto}.csv", ["ordem_chegada", "seq", "rtt_ms"],
                  [[i + 1, s, r3(v)] for i, (s, v) in enumerate(r["raw"])])
        rt = r["rtt"]
        append_csv(RESULTS / "tcp_udp_summary.csv",
                   ["condicao", "protocolo", "tamanho_bytes", "intervalo_ms", "enviados", "recebidos", "perdidos",
                    "perda_pct", "fora_de_ordem", "duplicados", "erros_envio", "tempo_s", "goodput_kBps",
                    "rtt_media_ms", "rtt_mediana_ms", "rtt_dp_ms", "rtt_p95_ms", "rtt_max_ms", *env.keys()],
                   [args.label, r["proto"], r["size"], args.interval * 1000, r["enviados"], r["recebidos"],
                    r["perdidos"], round(r["perda_pct"], 3), r["fora_de_ordem"], r["duplicados"], r["erros_envio"],
                    round(r["tempo_s"], 4), round(r["goodput_kBps"], 2), r3(rt["media"]), r3(rt["mediana"]),
                    r3(rt["desvio_padrao"]), r3(rt["p95"]), r3(rt["max"]), *env.values()])
        time.sleep(0.5)
    print("\nGravado em results/tcp_udp_summary.csv")


def main():
    ap = argparse.ArgumentParser(description="Experimento D — TCP × UDP")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("server", help="inicia os servidores de eco TCP e UDP")
    s.add_argument("--bind", default="0.0.0.0")
    s.add_argument("--port", type=int, default=9001)
    c = sub.add_parser("client", help="executa a medição")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, default=9001)
    c.add_argument("--label", required=True)
    c.add_argument("--proto", choices=["tcp", "udp", "both"], default="both")
    c.add_argument("-n", type=int, default=1000, help="pacotes por protocolo")
    c.add_argument("--size", type=int, default=512, help="bytes por pacote (mín. 12)")
    c.add_argument("--interval", type=float, default=0.002, help="intervalo entre envios (s); 0 = rajada")
    c.add_argument("--timeout", type=float, default=3.0, help="espera pelos ecos após o último envio (s)")
    args = ap.parse_args()
    run_server(args) if args.cmd == "server" else run_client(args)


if __name__ == "__main__":
    main()
