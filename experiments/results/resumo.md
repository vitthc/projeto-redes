# Resumo dos experimentos

## Experimento A — RTT

| Condição_modo | n | Média (ms) | Mediana (ms) | Desvio padrão (ms) | Mín. (ms) | Máx. (ms) |
|---|---|---|---|---|---|---|
| localhost_ws | 30 | 0,858 | 0,800 | 0,239 | 0,593 | 1,920 |
| localhost_http | 30 | 9,814 | 4,312 | 8,605 | 3,241 | 28,110 |
| lan_ws | 30 | 21,973 | 13,444 | 17,280 | 9,813 | 74,407 |
| lan_http | 30 | 63,445 | 50,791 | 54,432 | 22,039 | 305,603 |
| lan_atraso100_perda5_ws | 30 | 528,952 | 505,491 | 273,209 | 302,583 | 1436,228 |

Figura: `figures/rtt_boxplot.png`

## Experimento B — Throughput

| Condição | Carga (bytes) | Repetições | Média (Mbit/s) | Desvio padrão (Mbit/s) | Mensagens/s |
|---|---|---|---|---|---|
| lan | 100 | 3 | 0,045 | 0,004 | 55,6 |
| lan | 1000 | 3 | 0,423 | 0,036 | 52,9 |
| lan | 10000 | 3 | 4,216 | 0,121 | 52,7 |
| lan | 100000 | 3 | 35,439 | 0,726 | 44,3 |
| localhost | 100 | 3 | 0,136 | 0,003 | 169,6 |
| localhost | 1000 | 3 | 1,273 | 0,113 | 159,1 |
| localhost | 10000 | 3 | 12,315 | 0,588 | 153,9 |
| localhost | 100000 | 3 | 102,907 | 6,633 | 128,7 |

Figura: `figures/throughput.png`

## Experimento C — Concorrência

| Condição | Clientes | Enviadas | Recebidas | Perdidas | Taxa (msgs/s) | Atraso médio (ms) | Atraso mediano (ms) | Atraso p95 (ms) | RTT mediano (ms) |
|---|---|---|---|---|---|---|---|---|---|
| lan | 1 | 300 | 300 | 0 | 10,0 | 43,42 | 37,03 | 89,73 | 16,12 |
| lan | 2 | 600 | 600 | 0 | 20,0 | 66,78 | 52,09 | 161,49 | 27,54 |
| lan | 5 | 1500 | 1500 | 0 | 50,0 | 111,23 | 88,13 | 276,95 | 54,92 |
| localhost | 1 | 300 | 300 | 0 | 10,0 | 11,67 | 11,60 | 17,89 | 1,17 |
| localhost | 2 | 600 | 600 | 0 | 20,0 | 13,70 | 12,06 | 28,22 | 1,05 |
| localhost | 5 | 1500 | 1500 | 0 | 50,0 | 31,38 | 14,14 | 130,19 | 2,64 |

Figura: `figures/concurrency.png`

## Experimentos D/E — TCP × UDP

| Condição | Protocolo | Enviados | Recebidos | Perda (%) | Fora de ordem | RTT médio (ms) | RTT mediano (ms) | RTT p95 (ms) | Goodput (kB/s) |
|---|---|---|---|---|---|---|---|---|---|
| localhost | TCP | 1000 | 1000 | 0,00 | 0 | 0,374 | 0,311 | 0,672 | 256,2 |
| localhost | UDP | 1000 | 1000 | 0,00 | 0 | 0,329 | 0,302 | 0,542 | 256,1 |
| lan | TCP | 1000 | 1000 | 0,00 | 0 | 31,570 | 23,527 | 90,003 | 254,1 |
| lan | UDP | 1000 | 1000 | 0,00 | 0 | 30,366 | 22,621 | 95,067 | 254,0 |
| lan_atraso100_perda5 | TCP | 1000 | 1000 | 0,00 | 0 | 11376,370 | 14041,395 | 19397,262 | 23,4 |
| lan_atraso100_perda5 | UDP | 1000 | 884 | 11,60 | 0 | 275,060 | 273,268 | 332,155 | 195,9 |

Figura: `figures/tcp_udp.png`

