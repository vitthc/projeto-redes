import json, logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.websocket("/ws/sensor")
async def ws_sensor(ws: WebSocket):
    await ws.accept()
    logging.info("sensor conectado: %s", ws.client)
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            logging.info("recebido: %s", msg)
    except WebSocketDisconnect:
        logging.info("sensor desconectado: %s", ws.client)