# Monitoramento de Laboratório em Tempo Real

Projeto 1 — CIC0124 Redes de Computadores (UnB, 2026).

Aplicação distribuída em que sensores simulados enviam temperatura e umidade a um servidor central.
O servidor valida, grava no SQLite, verifica limiares e repassa tudo em tempo real para um painel Web.

| Componente | Tecnologia | Comunicação |
|---|---|---|
| Servidor | Python 3.11+, FastAPI, Uvicorn | HTTP + WebSocket na porta 8000 |
| Sensores simulados | Python, biblioteca `websockets` | WebSocket `/ws/sensor` |
| Painel Web | HTML + JavaScript (sem frameworks) | HTTP (consultas e configuração) + WebSocket `/ws/dashboard` |
| Armazenamento | SQLite (`server/data.db`) | — |

## Estrutura

```
server/main.py                   servidor (HTTP, WebSocket, validação, alertas, logs, SQLite)
sensor/sensor.py                 sensor simulado (autenticação, reconexão automática)
dashboard/index.html             painel Web, servido pelo próprio servidor em http://<ip>:8000/
experiments/exp_a_rtt.py         Experimento A — RTT e tempo de resposta HTTP
experiments/exp_b_throughput.py  Experimento B — throughput por tamanho de mensagem
experiments/exp_c_concurrency.py Experimento C — 1, 2 e 5 clientes simultâneos
experiments/exp_d_tcp_udp.py     Experimento D — microteste TCP × UDP com sockets puros
experiments/netem.sh             Experimento E — atraso/perda simulados (Linux/WSL2)
experiments/plot_results.py      gera gráficos e tabelas a partir dos CSVs
experiments/results/             CSVs gerados pelos experimentos
experiments/figures/             gráficos gerados
captures/                        capturas do Wireshark (.pcapng)
```

## Instalação

Requisitos: Python 3.11 ou mais novo.

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt
```

## Execução

**1. Servidor** (na raiz do projeto):

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` deixa o servidor acessível por outras máquinas da rede. Se outra máquina não conseguir
conectar, libere a porta 8000 no firewall.

**2. Painel:** abra `http://localhost:8000/` (ou `http://<ip-do-servidor>:8000/` em outra máquina).
A documentação interativa das rotas HTTP fica em `http://localhost:8000/docs`.

**3. Cadastrar sensores:** no painel, em "Cadastrar sensor", informe um `device_id` (ex.: `sensor-01`).
O painel mostra o token e o comando pronto para iniciar o sensor. Também dá para usar `POST /devices` em `/docs`.

**4. Sensores** (um terminal para cada):

```bash
python sensor/sensor.py --id sensor-01 --token <token> --server <ip-do-servidor>:8000
python sensor/sensor.py --id sensor-02 --token <token> --server <ip-do-servidor>:8000 --hot
```

`--hot` gera temperaturas acima de 30 °C para demonstrar o alerta. `--interval` muda o intervalo entre leituras (padrão 1 s).

Para recomeçar do zero, pare o servidor e apague `server/data.db`.

## Interfaces HTTP

| Método e rota | Função |
|---|---|
| `GET /` | painel Web |
| `GET /health` | estado do servidor e hora atual |
| `POST /devices` | cadastra um sensor `{"device_id": "..."}` e devolve o token |
| `GET /devices` | lista sensores e se estão online (dado recebido nos últimos 5 s) |
| `GET /history?device_id=&limit=` | leituras gravadas, mais recentes primeiro |
| `GET /alerts?limit=` | alertas disparados |
| `GET /thresholds` / `PUT /thresholds` | consulta ou altera limiares `{"temp_max": 30, "hum_max": 80}` |

Erros de validação HTTP devolvem 422 (campo inválido) ou 409 (`device_id` já cadastrado).

## Protocolo de aplicação (WebSocket, mensagens JSON)

| Tipo | Direção | Campos | Quando |
|---|---|---|---|
| `AUTH` | sensor → servidor | `device_id`, `token` | primeira mensagem, em até 5 s após conectar |
| `AUTH_OK` | servidor → sensor | — | autenticação aceita |
| `DATA` | sensor → servidor | `device_id`, `seq`, `ts`, `payload{temp, hum}` | a cada leitura |
| `UPDATE` | servidor → painel | campos de `DATA` + `server_ts` | repasse em tempo real |
| `ALERT` | servidor → painel | `device_id`, `rule`, `value`, `ts` | valor cruza o limiar (de baixo para cima) |
| `STATUS` | servidor → painel | `device_id`, `online` | sensor conecta ou desconecta |
| `PING` / `PONG` | cliente ↔ servidor | `seq`, `ts` | medição de RTT (o PONG ecoa `seq` e `ts`) |
| `ERROR` | servidor → cliente | `code`, `msg` | mensagem rejeitada |

Códigos de erro: `AUTH_FAILED` (token inválido; a conexão é fechada com código 1008), `INVALID_MSG`
(JSON malformado ou campo ausente), `OUT_OF_RANGE` (temp fora de −40 a 85 °C ou umidade fora de 0 a 100 %),
`UNKNOWN_TYPE` (tipo desconhecido). Exceto `AUTH_FAILED`, os erros não derrubam a conexão.

Sequência: conectar → `AUTH` → `AUTH_OK` → `DATA` repetido (e `PING` quando medir) → desconexão.

Exemplos:

```json
{"type": "AUTH", "device_id": "sensor-01", "token": "3f9a1c7e2b4d6a80"}
{"type": "DATA", "device_id": "sensor-01", "seq": 42, "ts": 1793728310.87, "payload": {"temp": 27.5, "hum": 55.0}}
{"type": "ALERT", "device_id": "sensor-02", "rule": "temp > 30.0", "value": 34.2, "ts": 1793728310.88}
{"type": "ERROR", "code": "OUT_OF_RANGE", "msg": "temp ausente ou fora da faixa (-40 a 85)"}
```

## Tratamento de falhas e logs

- Todo evento (conexão, autenticação, erro, alerta, desconexão, mudança de limiar) é gravado com timestamp em `server/server.log`.
- O sensor reconecta sozinho a cada 2 s se o servidor cair; o painel reconecta com espera crescente (1, 2, 4… até 10 s).
- O painel marca um sensor como offline após 5 s sem dados, mesmo sem aviso de desconexão.
- Mensagens inválidas recebem `ERROR` e não derrubam o servidor nem a conexão.

## Experimentos

Execute com o servidor rodando. Use `--server <ip>:8000` quando o servidor estiver em outra máquina.
Cada script imprime as condições de execução (data, máquina, SO) e grava CSVs em `experiments/results/`.
Os scripts cadastram sensores próprios com prefixo `exp-`; o painel os esconde por padrão.

### A — RTT (≥ 30 medições por condição)

```bash
python experiments/exp_a_rtt.py --server localhost:8000 --label localhost
python experiments/exp_a_rtt.py --server 192.168.0.10:8000 --label lan
python experiments/exp_a_rtt.py --server 192.168.0.10:8000 --label lan --mode http
```

`--mode ws` mede o RTT de aplicação por PING/PONG numa conexão já aberta.
`--mode http` mede o tempo de resposta de `GET /health`, incluindo o handshake TCP de cada requisição.
As 3 primeiras medições são descartadas (aquecimento).

### B — Throughput

```bash
python experiments/exp_b_throughput.py --server 192.168.0.10:8000 --label lan
```

Envia 200 mensagens por tamanho de carga (100 B, 1 kB, 10 kB, 100 kB), 3 repetições cada.
Throughput útil = bytes de carga ÷ tempo entre o primeiro envio e o PONG final
(o PONG só volta depois que todas as mensagens foram processadas, porque o TCP entrega em ordem).

### C — Concorrência

```bash
python experiments/exp_c_concurrency.py --server 192.168.0.10:8000 --label lan
```

Cenários de 1, 2 e 5 sensores a 10 mensagens/s cada, 30 s por cenário. Mede o atraso fim a fim
sensor → servidor → painel (mesmo relógio, pois os clientes rodam no mesmo processo) e a taxa de mensagens.

### D — TCP × UDP

```bash
# máquina servidora
python experiments/exp_d_tcp_udp.py server --port 9001
# máquina cliente
python experiments/exp_d_tcp_udp.py client --host 192.168.0.10 --label lan
```

Mesma carga nos dois protocolos: 1000 pacotes de 512 B a cada 2 ms. Mede perdas, chegadas fora de
ordem, duplicatas e RTT. O TCP retransmite e entrega em ordem; o UDP não, então perdas aparecem como
pacotes não recebidos. A comparação é de transporte, não de funcionalidade equivalente.

### E — Rede degradada

Linux ou WSL2 (`ip -br addr` mostra o nome da interface):

```bash
sudo ./experiments/netem.sh lo apply 100 5        # 100 ms de atraso e 5 % de perda
python experiments/exp_a_rtt.py --label netem_100ms_5pct
python experiments/exp_d_tcp_udp.py client --label netem_100ms_5pct
sudo ./experiments/netem.sh lo clear              # sempre remover no fim
```

No loopback o atraso vale para ida e volta (RTT ≈ 2 × atraso). Numa interface real, só para os pacotes que saem da máquina.
No Windows, use o [clumsy](https://jagt.github.io/clumsy/) com filtro `tcp.DstPort == 8000 or tcp.SrcPort == 8000` (ou `udp`)
e as opções Lag e Drop; anote os parâmetros usados.

### Gráficos e tabelas

```bash
python experiments/plot_results.py
```

Gera `experiments/figures/*.png` e `experiments/results/resumo.md` (tabelas prontas para o relatório).

## Wireshark

Capture na interface de rede real (Wi-Fi ou cabo) enquanto roda os experimentos e salve em `captures/`.

| Captura | Filtro |
|---|---|
| Handshake TCP e HTTP | `tcp.port == 8000 && (tcp.flags.syn == 1 \|\| http)` |
| Upgrade para WebSocket e frames | `tcp.port == 8000 && (http \|\| websocket)` |
| Retransmissões (com netem/clumsy) | `tcp.analysis.retransmission \|\| tcp.analysis.duplicate_ack` |
| Microteste UDP | `udp.port == 9001` |
| Várias conexões simultâneas | `tcp.port == 8000`, depois Statistics → Conversations |

O RTT do TCP aparece em Statistics → TCP Stream Graphs → Round Trip Time; compare com o RTT de aplicação do Experimento A.
No Windows, para capturar `localhost` é preciso o Npcap com suporte a loopback.

## Bibliotecas, ferramentas e uso de IA

- FastAPI, Uvicorn, Pydantic, websockets, matplotlib; SQLite (biblioteca padrão do Python).
- Wireshark, tc/netem (Linux) ou clumsy (Windows).
- O código-base foi gerado com auxílio do Claude (Anthropic) e revisado, testado e adaptado pelo grupo.
  <!-- Ajustem esta declaração para refletir exatamente como a IA foi usada. -->
