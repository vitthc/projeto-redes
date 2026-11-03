"""
Servidor do sistema de monitoramento de laboratório.
HTTP (consulta, cadastro, configuração) + WebSocket (tempo real) na mesma porta.
Rodar a partir da raiz do projeto:  uvicorn server.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import json
import logging
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

BASE = Path(__file__).parent
DB_PATH = BASE / "data.db"
LOG_PATH = BASE / "server.log"

# ---------------------------------------------------------------- logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("server")

app = FastAPI(title="Monitoramento de Laboratório")


# ---------------------------------------------------------------- banco
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY, token TEXT NOT NULL, created_at REAL);
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, seq INTEGER,
                ts REAL, server_ts REAL, temp REAL, hum REAL);
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, rule TEXT,
                value REAL, ts REAL);
            """
        )


init_db()

# ---------------------------------------------------------------- estado em memória
thresholds = {"temp_max": 30.0, "hum_max": 80.0}
dashboards: set[WebSocket] = set()      # painéis conectados
last_seen: dict[str, float] = {}         # último DATA de cada sensor
alert_active: dict[tuple, bool] = {}     # (device_id, campo) -> já em alerta?


# ---------------------------------------------------------------- validação
def validate_data(msg: dict) -> str | None:
    """Devolve uma descrição do erro, ou None se a mensagem DATA é válida."""
    required = {"device_id": str, "seq": int, "ts": (int, float), "payload": dict}
    for field, typ in required.items():
        if field not in msg:
            return f"campo '{field}' ausente"
        if isinstance(msg[field], bool) or not isinstance(msg[field], typ):
            return f"campo '{field}' com tipo inválido"
    p = msg["payload"]
    temp, hum = p.get("temp"), p.get("hum")
    if not isinstance(temp, (int, float)) or not -40 <= temp <= 85:
        return "temp ausente ou fora da faixa (-40 a 85)"
    if hum is not None and (not isinstance(hum, (int, float)) or not 0 <= hum <= 100):
        return "hum fora da faixa (0 a 100)"
    return None


# ---------------------------------------------------------------- envio
async def broadcast(msg: dict):
    """Envia a mensagem para todos os painéis; remove os que caíram."""
    text = json.dumps(msg)
    for ws in list(dashboards):
        try:
            await ws.send_text(text)
        except Exception:
            dashboards.discard(ws)
            log.warning("painel removido (falha no envio): %s", ws.client)


async def send_error(ws: WebSocket, code: str, msg: str):
    log.warning("ERROR %s para %s: %s", code, ws.client, msg)
    await ws.send_text(json.dumps({"type": "ERROR", "code": code, "msg": msg}))


# ---------------------------------------------------------------- HTTP
class DeviceIn(BaseModel):
    device_id: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


class ThresholdsIn(BaseModel):
    temp_max: float = Field(ge=-40, le=85)
    hum_max: float = Field(ge=0, le=100)


@app.get("/health")
def health():
    return {"status": "ok", "time": time.time()}


@app.post("/devices", status_code=201)
def create_device(d: DeviceIn):
    token = secrets.token_hex(8)
    try:
        with db() as c:
            c.execute("INSERT INTO devices VALUES (?, ?, ?)", (d.device_id, token, time.time()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "device_id já cadastrado")
    log.info("dispositivo cadastrado: %s", d.device_id)
    return {"device_id": d.device_id, "token": token}


@app.get("/devices")
def list_devices():
    with db() as c:
        rows = c.execute("SELECT device_id FROM devices ORDER BY device_id").fetchall()
    now = time.time()
    return [
        {"device_id": r["device_id"],
         "online": now - last_seen.get(r["device_id"], 0) < 5,
         "last_seen": last_seen.get(r["device_id"])}
        for r in rows
    ]


@app.get("/history")
def history(device_id: str | None = None, limit: int = 100):
    limit = max(1, min(limit, 1000))
    q = "SELECT device_id, seq, ts, server_ts, temp, hum FROM readings"
    args: list = []
    if device_id:
        q += " WHERE device_id = ?"
        args.append(device_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with db() as c:
        return [dict(r) for r in c.execute(q, args)]


@app.get("/alerts")
def alerts(limit: int = 50):
    limit = max(1, min(limit, 500))
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT device_id, rule, value, ts FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]


@app.get("/thresholds")
def get_thresholds():
    return thresholds


@app.put("/thresholds")
def set_thresholds(t: ThresholdsIn):
    thresholds.update(t.model_dump())
    log.info("limiares alterados: %s", thresholds)
    return thresholds


# ---------------------------------------------------------------- lógica de DATA
async def handle_data(msg: dict):
    server_ts = time.time()
    dev, p = msg["device_id"], msg["payload"]
    last_seen[dev] = server_ts
    with db() as c:
        c.execute(
            "INSERT INTO readings (device_id, seq, ts, server_ts, temp, hum) VALUES (?, ?, ?, ?, ?, ?)",
            (dev, msg["seq"], msg["ts"], server_ts, p.get("temp"), p.get("hum")),
        )
    await broadcast({**msg, "type": "UPDATE", "server_ts": server_ts})

    # alertas: dispara só quando o valor CRUZA o limiar (evita um alerta por segundo)
    for key, field in (("temp_max", "temp"), ("hum_max", "hum")):
        value = p.get(field)
        if value is None:
            continue
        above = value > thresholds[key]
        if above and not alert_active.get((dev, field)):
            rule = f"{field} > {thresholds[key]}"
            with db() as c:
                c.execute("INSERT INTO alerts (device_id, rule, value, ts) VALUES (?, ?, ?, ?)",
                          (dev, rule, value, server_ts))
            log.warning("ALERTA %s: %s (valor %s)", dev, rule, value)
            await broadcast({"type": "ALERT", "device_id": dev, "rule": rule,
                             "value": value, "ts": server_ts})
        alert_active[(dev, field)] = above


# ---------------------------------------------------------------- WebSocket dos sensores
@app.websocket("/ws/sensor")
async def ws_sensor(ws: WebSocket):
    await ws.accept()
    device_id = None
    log.info("conexão de sensor aberta: %s", ws.client)
    try:
        # 1) a primeira mensagem tem de ser AUTH, em até 5 s
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
        except (asyncio.TimeoutError, json.JSONDecodeError):
            first = None
        if not isinstance(first, dict) or first.get("type") != "AUTH":
            await send_error(ws, "AUTH_FAILED", "esperado AUTH em JSON nos primeiros 5 s")
            await ws.close(code=1008)
            return
        with db() as c:
            row = c.execute("SELECT token FROM devices WHERE device_id = ?",
                            (first.get("device_id"),)).fetchone()
        if row is None or row["token"] != first.get("token"):
            await send_error(ws, "AUTH_FAILED", "device_id ou token inválido")
            await ws.close(code=1008)
            return
        device_id = first["device_id"]
        await ws.send_text(json.dumps({"type": "AUTH_OK"}))
        log.info("sensor autenticado: %s %s", device_id, ws.client)
        await broadcast({"type": "STATUS", "device_id": device_id, "online": True})

        # 2) laço principal
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send_error(ws, "INVALID_MSG", "JSON malformado")
                continue
            if not isinstance(msg, dict):
                await send_error(ws, "INVALID_MSG", "a mensagem deve ser um objeto JSON")
                continue
            kind = msg.get("type")
            if kind == "PING":
                await ws.send_text(json.dumps({"type": "PONG", "seq": msg.get("seq"), "ts": msg.get("ts")}))
                continue
            if kind != "DATA":
                await send_error(ws, "UNKNOWN_TYPE", f"tipo desconhecido: {kind}")
                continue
            err = validate_data(msg)
            if err:
                code = "OUT_OF_RANGE" if "faixa" in err else "INVALID_MSG"
                await send_error(ws, code, err)
                continue
            if msg["device_id"] != device_id:
                await send_error(ws, "AUTH_FAILED", "device_id diferente do autenticado")
                continue
            await handle_data(msg)
    except WebSocketDisconnect:
        pass
    finally:
        log.info("sensor desconectado: %s %s", device_id, ws.client)
        if device_id:
            await broadcast({"type": "STATUS", "device_id": device_id, "online": False})


# ---------------------------------------------------------------- WebSocket dos painéis
@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    await ws.accept()
    dashboards.add(ws)
    log.info("painel conectado: %s (total %d)", ws.client, len(dashboards))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send_error(ws, "INVALID_MSG", "JSON malformado")
                continue
            if isinstance(msg, dict) and msg.get("type") == "PING":
                await ws.send_text(json.dumps({"type": "PONG", "seq": msg.get("seq"), "ts": msg.get("ts")}))
    except WebSocketDisconnect:
        pass
    finally:
        dashboards.discard(ws)
        log.info("painel desconectado: %s (total %d)", ws.client, len(dashboards))