"""
Gera gráficos e tabelas a partir dos CSVs em experiments/results/.

  python experiments/plot_results.py

Saídas:
  experiments/figures/rtt_boxplot.png         Experimento A
  experiments/figures/throughput.png          Experimento B
  experiments/figures/concurrency.png         Experimento C
  experiments/figures/tcp_udp.png             Experimentos D e E
  experiments/results/resumo.md               tabelas em Markdown para o relatório
"""
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BASE = Path(__file__).parent
RES = BASE / "results"
FIG = BASE / "figures"
FIG.mkdir(exist_ok=True)
COLORS = ["#2563eb", "#d97706", "#16a34a", "#9333ea", "#dc2626", "#0891b2"]

plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.3, "font.size": 10})


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def f(x):
    return float(x) if x not in (None, "") else float("nan")


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def fmt(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


md = ["# Resumo dos experimentos\n"]

# ------------------------------------------------------------------ A — RTT
raws = sorted(RES.glob("rtt_raw_*.csv"))
if raws:
    labels, data, rows = [], [], []
    for p in raws:
        vals = [f(r["rtt_ms"]) for r in read(p)]
        if not vals:
            continue
        label = p.stem.removeprefix("rtt_raw_")
        labels.append(label.replace("_", "\n"))
        data.append(vals)
        n = len(vals)
        rows.append([label, n, fmt(statistics.fmean(vals), 3), fmt(statistics.median(vals), 3),
                     fmt(statistics.stdev(vals) if n > 1 else 0, 3), fmt(min(vals), 3), fmt(max(vals), 3)])
    fig, ax = plt.subplots(figsize=(max(5, 1.6 * len(data)), 4))
    try:
        bp = ax.boxplot(data, tick_labels=labels, showmeans=True, patch_artist=True)
    except TypeError:  # matplotlib < 3.9
        bp = ax.boxplot(data, labels=labels, showmeans=True, patch_artist=True)
    for i, box in enumerate(bp["boxes"]):
        box.set(facecolor=COLORS[i % len(COLORS)] + "33", edgecolor=COLORS[i % len(COLORS)])
    ax.set_ylabel("RTT (ms)")
    ax.set_title("Experimento A — RTT por condição (triângulo = média)")
    fig.tight_layout()
    fig.savefig(FIG / "rtt_boxplot.png")
    plt.close(fig)
    md += ["## Experimento A — RTT\n",
           md_table(["Condição_modo", "n", "Média (ms)", "Mediana (ms)", "Desvio padrão (ms)", "Mín. (ms)", "Máx. (ms)"], rows),
           "\nFigura: `figures/rtt_boxplot.png`\n"]

# ------------------------------------------------------------------ B — Throughput
tps = sorted(RES.glob("throughput_*.csv"))
if tps:
    fig, ax = plt.subplots(figsize=(7, 4))
    rows = []
    for i, p in enumerate(tps):
        data = read(p)
        if not data:
            continue
        label = data[0]["condicao"]
        by = defaultdict(list)
        rate = defaultdict(list)
        for r in data:
            by[int(r["tamanho_carga_bytes"])].append(f(r["throughput_Mbps"]))
            rate[int(r["tamanho_carga_bytes"])].append(f(r["msgs_por_s"]))
        sizes = sorted(by)
        means = [statistics.fmean(by[s]) for s in sizes]
        sds = [statistics.stdev(by[s]) if len(by[s]) > 1 else 0 for s in sizes]
        ax.errorbar(sizes, means, yerr=sds, marker="o", capsize=4, color=COLORS[i % len(COLORS)], label=label)
        for s, m, d in zip(sizes, means, sds):
            rows.append([label, s, len(by[s]), fmt(m, 3), fmt(d, 3), fmt(statistics.fmean(rate[s]), 1)])
    ax.set_xscale("log")
    ax.set_xlabel("Tamanho da carga útil por mensagem (bytes, escala log)")
    ax.set_ylabel("Throughput útil (Mbit/s)")
    ax.set_title("Experimento B — Throughput por tamanho de mensagem")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "throughput.png")
    plt.close(fig)
    md += ["## Experimento B — Throughput\n",
           md_table(["Condição", "Carga (bytes)", "Repetições", "Média (Mbit/s)", "Desvio padrão (Mbit/s)", "Mensagens/s"], rows),
           "\nFigura: `figures/throughput.png`\n"]

# ------------------------------------------------------------------ C — Concorrência
cpath = RES / "concurrency_summary.csv"
if cpath.exists():
    data = read(cpath)
    latest = {}
    for r in data:  # se um cenário foi repetido, vale a última execução
        latest[(r["condicao"], int(r["clientes"]))] = r
    conds = sorted({k[0] for k in latest})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    width = 0.8 / max(1, len(conds))
    rows = []
    for i, cond in enumerate(conds):
        ns = sorted(n for c, n in latest if c == cond)
        xs = [j + i * width for j in range(len(ns))]
        med = [f(latest[(cond, n)]["atraso_mediana_ms"]) for n in ns]
        p95 = [f(latest[(cond, n)]["atraso_p95_ms"]) for n in ns]
        rec = [f(latest[(cond, n)]["taxa_recebida_msgs_s"]) for n in ns]
        c = COLORS[i % len(COLORS)]
        a1.bar(xs, med, width, color=c, alpha=0.85, label=f"{cond} — mediana")
        a1.scatter(xs, p95, color=c, marker="_", s=300, linewidths=2, label=f"{cond} — p95")
        a2.bar(xs, rec, width, color=c, alpha=0.85, label=cond)
        for n in ns:
            r = latest[(cond, n)]
            rows.append([cond, n, r["enviadas"], r["recebidas_painel"], r["perdidas"], fmt(f(r["taxa_recebida_msgs_s"]), 1),
                         fmt(f(r["atraso_media_ms"])), fmt(f(r["atraso_mediana_ms"])), fmt(f(r["atraso_p95_ms"])),
                         fmt(f(r["rtt_mediana_ms"]))])
        ticks = [j + width * (len(conds) - 1) / 2 for j in range(len(ns))]
        a1.set_xticks(ticks, [str(n) for n in ns])
        a2.set_xticks(ticks, [str(n) for n in ns])
    a1.set_xlabel("Clientes simultâneos")
    a1.set_ylabel("Atraso sensor → painel (ms)")
    a1.set_title("Atraso (barra = mediana, traço = p95)")
    a1.legend(fontsize=8)
    a2.set_xlabel("Clientes simultâneos")
    a2.set_ylabel("Mensagens recebidas por segundo")
    a2.set_title("Taxa de mensagens")
    a2.legend(fontsize=8)
    fig.suptitle("Experimento C — Concorrência")
    fig.tight_layout()
    fig.savefig(FIG / "concurrency.png")
    plt.close(fig)
    md += ["## Experimento C — Concorrência\n",
           md_table(["Condição", "Clientes", "Enviadas", "Recebidas", "Perdidas", "Taxa (msgs/s)", "Atraso médio (ms)",
                     "Atraso mediano (ms)", "Atraso p95 (ms)", "RTT mediano (ms)"], rows),
           "\nFigura: `figures/concurrency.png`\n"]

# ------------------------------------------------------------------ D/E — TCP × UDP
dpath = RES / "tcp_udp_summary.csv"
if dpath.exists():
    data = read(dpath)
    latest = {}
    for r in data:
        latest[(r["condicao"], r["protocolo"])] = r
    conds = list(dict.fromkeys(k[0] for k in latest))
    protos = ["TCP", "UDP"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    width = 0.38
    rows = []
    for i, proto in enumerate(protos):
        xs = [j + i * width for j in range(len(conds))]
        loss = [f(latest[(c, proto)]["perda_pct"]) if (c, proto) in latest else 0 for c in conds]
        rtt = [f(latest[(c, proto)]["rtt_mediana_ms"]) if (c, proto) in latest else 0 for c in conds]
        a1.bar(xs, loss, width, color=COLORS[i], label=proto)
        a2.bar(xs, rtt, width, color=COLORS[i], label=proto)
    for c in conds:
        for proto in protos:
            if (c, proto) in latest:
                r = latest[(c, proto)]
                rows.append([c, proto, r["enviados"], r["recebidos"], fmt(f(r["perda_pct"])), r["fora_de_ordem"],
                             fmt(f(r["rtt_media_ms"]), 3), fmt(f(r["rtt_mediana_ms"]), 3), fmt(f(r["rtt_p95_ms"]), 3),
                             fmt(f(r["goodput_kBps"]), 1)])
    ticks = [j + width / 2 for j in range(len(conds))]
    for ax in (a1, a2):
        ax.set_xticks(ticks, conds, rotation=15)
        ax.legend()
    a1.set_ylabel("Perda na aplicação (%)")
    a1.set_title("Pacotes não recebidos")
    a2.set_ylabel("RTT mediano (ms)")
    a2.set_title("RTT")
    fig.suptitle("Experimento D/E — TCP × UDP (mesma carga e ritmo)")
    fig.tight_layout()
    fig.savefig(FIG / "tcp_udp.png")
    plt.close(fig)
    md += ["## Experimentos D/E — TCP × UDP\n",
           md_table(["Condição", "Protocolo", "Enviados", "Recebidos", "Perda (%)", "Fora de ordem", "RTT médio (ms)",
                     "RTT mediano (ms)", "RTT p95 (ms)", "Goodput (kB/s)"], rows),
           "\nFigura: `figures/tcp_udp.png`\n"]

(RES / "resumo.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("Figuras em", FIG)
print("Tabelas em", RES / "resumo.md")
