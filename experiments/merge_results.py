"""
Junta os resultados vindos de outra máquina (ex.: o celular) aos resultados desta.

  python experiments/merge_results.py <pasta-com-os-arquivos-do-celular>

  * Arquivos de resumo (*summary*.csv): as linhas novas são ACRESCENTADAS ao arquivo
    desta máquina, sem repetir o cabeçalho e sem duplicar linhas já presentes.
  * Demais arquivos (rtt_raw_*, throughput_*, concurrency_delays_*, tcp_udp_raw_*):
    são copiados para experiments/results/ (se já existir um com o mesmo nome, avisa e não sobrescreve).
"""
import csv
import shutil
import sys
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def merge_summary(src: Path, dst: Path):
    new = read_rows(src)
    if not new:
        return
    if not dst.exists():
        shutil.copy2(src, dst)
        print(f"  {dst.name}: criado com {len(new) - 1} linha(s)")
        return
    old = read_rows(dst)
    if old and old[0] != new[0]:
        print(f"  {dst.name}: CABEÇALHOS DIFERENTES — não juntei. Confira se as duas máquinas usam a mesma versão dos scripts.")
        return
    existing = {tuple(r) for r in old[1:]}
    added = [r for r in new[1:] if tuple(r) not in existing]
    with open(dst, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(added)
    print(f"  {dst.name}: {len(added)} linha(s) acrescentada(s), {len(new) - 1 - len(added)} já existiam")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    src_dir = Path(sys.argv[1])
    files = sorted(src_dir.glob("*.csv"))
    if not files:
        print(f"Nenhum .csv em {src_dir}")
        sys.exit(1)
    RESULTS.mkdir(exist_ok=True)
    print(f"Juntando {len(files)} arquivo(s) de {src_dir} em {RESULTS}:")
    for src in files:
        dst = RESULTS / src.name
        if "summary" in src.name:
            merge_summary(src, dst)
        elif dst.exists():
            print(f"  {src.name}: já existe aqui — mantido o daqui (renomeie um deles se forem medições diferentes)")
        else:
            shutil.copy2(src, dst)
            print(f"  {src.name}: copiado")
    print("Pronto. Agora rode: python experiments/plot_results.py")


if __name__ == "__main__":
    main()
