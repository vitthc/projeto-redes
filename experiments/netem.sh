#!/usr/bin/env bash
# Experimento E — aplica ou remove atraso/perda com tc netem (Linux ou WSL2).
#
# Uso:
#   sudo ./experiments/netem.sh <interface> apply <atraso_ms> <perda_pct> [variacao_ms]
#   sudo ./experiments/netem.sh <interface> clear
#   ./experiments/netem.sh <interface> show
#
# Exemplos:
#   sudo ./experiments/netem.sh lo   apply 100 0        # 100 ms de atraso no loopback
#   sudo ./experiments/netem.sh wlan0 apply 100 5 10    # 100 ± 10 ms e 5 % de perda no Wi-Fi
#   sudo ./experiments/netem.sh wlan0 clear
#
# Observações para o relatório:
#   * netem age na SAÍDA da interface. No loopback (lo) isso afeta ida e volta,
#     então o RTT sobe cerca de 2 × atraso. Numa interface real, afeta só os pacotes
#     que saem desta máquina: aplicado no servidor, o RTT sobe cerca de 1 × atraso.
#   * Descubra o nome da interface com:  ip -br addr
#   * Sempre remova a regra no fim (clear), ou a rede continua degradada.
set -euo pipefail

IFACE="${1:-}"; ACTION="${2:-}"
if [[ -z "$IFACE" || -z "$ACTION" ]]; then
  sed -n '2,20p' "$0"; exit 1
fi

case "$ACTION" in
  apply)
    DELAY="${3:?informe o atraso em ms}"; LOSS="${4:?informe a perda em %}"; JITTER="${5:-0}"
    tc qdisc del dev "$IFACE" root 2>/dev/null || true
    if [[ "$JITTER" != "0" ]]; then
      tc qdisc add dev "$IFACE" root netem delay "${DELAY}ms" "${JITTER}ms" loss "${LOSS}%"
    else
      tc qdisc add dev "$IFACE" root netem delay "${DELAY}ms" loss "${LOSS}%"
    fi
    echo "$(date '+%F %T') aplicado em $IFACE: atraso ${DELAY} ms, variação ${JITTER} ms, perda ${LOSS} %"
    tc qdisc show dev "$IFACE"
    ;;
  clear)
    tc qdisc del dev "$IFACE" root 2>/dev/null && echo "regras removidas de $IFACE" || echo "nenhuma regra em $IFACE"
    ;;
  show)
    tc qdisc show dev "$IFACE"
    ;;
  *)
    echo "ação desconhecida: $ACTION (use apply, clear ou show)"; exit 1
    ;;
esac
