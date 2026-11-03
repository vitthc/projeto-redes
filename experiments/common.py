"""Funções compartilhadas pelos scripts de experimento."""
import csv
import json
import platform
import socket
import statistics
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
RESULTS.mkdir(exist_ok=True)

# Conexões HTTP diretas, ignorando proxies configurados no sistema
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def environment(server: str) -> dict:
    """Condições de execução, para registrar junto com os resultados."""
    return {
        "data_hora": now_str(),
        "maquina_cliente": socket.gethostname(),
        "so_cliente": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "servidor": server,
    }


def print_environment(server: str):
    print("Condições de execução:")
    for k, v in environment(server).items():
        print(f"  {k}: {v}")


def summarize(values) -> dict:
    """Estatísticas descritivas (n, média, mediana, desvio padrão amostral, mín., máx., p95)."""
    v = sorted(values)
    n = len(v)
    if n == 0:
        return {"n": 0, "media": None, "mediana": None, "desvio_padrao": None,
                "min": None, "max": None, "p95": None}
    return {
        "n": n,
        "media": statistics.fmean(v),
        "mediana": statistics.median(v),
        "desvio_padrao": statistics.stdev(v) if n > 1 else 0.0,
        "min": v[0],
        "max": v[-1],
        "p95": v[min(n - 1, round(0.95 * (n - 1)))],
    }


def fmt_summary(s: dict, unit: str = "ms") -> str:
    if not s["n"]:
        return "n=0 (sem dados)"
    return (f"n={s['n']}  média={s['media']:.3f} {unit}  mediana={s['mediana']:.3f} {unit}  "
            f"dp={s['desvio_padrao']:.3f} {unit}  mín={s['min']:.3f}  máx={s['max']:.3f}  p95={s['p95']:.3f}")


def r3(x):
    return None if x is None else round(x, 3)


def write_csv(path: Path, header: list, rows: list):
    """Grava (sobrescreve) um CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def append_csv(path: Path, header: list, row: list):
    """Acrescenta uma linha a um CSV de resumo, criando o cabeçalho se o arquivo é novo."""
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


def register_device(server: str, prefix: str):
    """Cadastra um sensor novo via HTTP POST /devices e devolve (device_id, token)."""
    device_id = f"{prefix}-{uuid.uuid4().hex[:6]}"
    req = urllib.request.Request(
        f"http://{server}/devices",
        data=json.dumps({"device_id": device_id}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with HTTP.open(req, timeout=5) as r:
        data = json.load(r)
    return data["device_id"], data["token"]


async def open_sensor(server: str, device_id: str, token: str):
    """Abre o WebSocket de sensor e autentica (AUTH → AUTH_OK)."""
    import websockets
    ws = await websockets.connect(f"ws://{server}/ws/sensor", max_size=None)
    await ws.send(json.dumps({"type": "AUTH", "device_id": device_id, "token": token}))
    resp = json.loads(await ws.recv())
    if resp.get("type") != "AUTH_OK":
        await ws.close()
        raise RuntimeError(f"autenticação recusada: {resp}")
    return ws
