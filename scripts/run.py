# scripts/run_all.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from datetime import datetime


ROOT = Path(__file__).resolve().parents[1]
OUT_RES = ROOT / "outputs" / "results"
OUT_FIG = ROOT / "outputs" / "figures"
OUT_RES.mkdir(parents=True, exist_ok=True)
OUT_FIG.mkdir(parents=True, exist_ok=True)


def run_module(module: str):
    """
    Ejecuta: python -m <module>
    """
    cmd = [sys.executable, "-m", module]
    print(f"\n▶ Running: {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0:
        raise SystemExit(f"❌ Falló el módulo: {module} (returncode={res.returncode})")
    print(f"✅ OK: {module}")


def require_files(paths: list[Path], hint: str = ""):
    missing = [p for p in paths if not p.exists()]
    if missing:
        print("\n❌ Faltan archivos esperados:")
        for p in missing:
            print(" -", p)
        if hint:
            print("\nHint:", hint)
        raise SystemExit(1)


def write_run_report():
    """
    Mini informe para el profe: qué se ha generado y dónde mirarlo.
    """
    report = OUT_RES / "RUN_REPORT.md"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append(f"# Run report\n\nGenerado: `{now}`\n")
    lines.append("## Enunciado → Outputs\n")
    lines.append("### 1) Estrategia long straddle periódico (SPY)\n")
    lines.append("- `outputs/results/daily_nohedge.csv`\n")
    lines.append("- `outputs/results/trades_nohedge.csv`\n")
    lines.append("- `outputs/figures/equity_nohedge.png`\n")

    lines.append("\n### 2) Versión delta-hedged con subyacente\n")
    lines.append("- `outputs/results/daily_deltahedged.csv`\n")
    lines.append("- `outputs/results/trades_deltahedged.csv`\n")
    lines.append("- `outputs/figures/equity_deltahedged.png`\n")

    lines.append("\n### 3) Análisis P&L histórico (métricas + gráficos)\n")
    lines.append("- `outputs/results/summary_metrics.csv`\n")
    lines.append("- `outputs/figures/equity_compare.png`\n")
    lines.append("- `outputs/figures/drawdown_compare.png`\n")
    lines.append("- `outputs/figures/rolling_vol_compare.png`\n")

    lines.append("\n### 4) Ejecución: combo vs patas + riesgo de legging\n")
    lines.append("- `outputs/results/execution_legging_summary.csv`\n")

    lines.append("\n### 5) Neutralizar delta con otra opción (impacto Gamma/Vega/Theta)\n")
    lines.append("- salida por consola (tabla) y opcional CSV si lo añades\n")

    lines.append("\n### 6) Reflexión SPX vs SPY\n")
    lines.append("- `REFLEXION.md`\n")

    report.write_text("".join(lines), encoding="utf-8")
    print("\n📝 Report generado:", report)


def main():
    print("\n==============================")
    print("   PRACTICA 4 - RUN ALL")
    print("==============================\n")
    print("IMPORTANTE: abre TWS y deja API activa antes de ejecutar.\n")

    # 0) Backtest (1 y 2)
    run_module("scripts.run_backtest")

    # Comprobamos que están los CSVs base
    require_files(
        [
            OUT_RES / "daily_nohedge.csv",
            OUT_RES / "daily_deltahedged.csv",
            OUT_RES / "trades_nohedge.csv",
            OUT_RES / "trades_deltahedged.csv",
        ],
        hint="Si faltan, revisa que scripts/run_backtest.py esté guardando con esos nombres."
    )

    # 1) Analytics (3)
    run_module("scripts.run_analytics")
    require_files(
        [
            OUT_RES / "summary_metrics.csv",
            OUT_FIG / "equity_compare.png",
            OUT_FIG / "drawdown_compare.png",
            OUT_FIG / "rolling_vol_compare.png",
        ],
        hint="Si faltan, revisa scripts/run_analytics.py y src/analytics.py."
    )

    # 2) Ejecución / Legging (4) - si tienes el script creado
    # Si aún no lo tienes, comenta esta línea.
    run_module("scripts.run_execution_sim")
    require_files(
        [OUT_RES / "execution_legging_summary.csv"],
        hint="Si faltan, revisa scripts/run_execution_sim.py (depende de trades_nohedge.csv)."
    )

    # 3) Delta-neutral con otra opción (5)
    run_module("scripts.run_delta_neutral_option")

    # 4) Report final
    write_run_report()

    print("\n✅ Todo OK. Mira outputs/figures y outputs/results para la entrega.\n")


if __name__ == "__main__":
    main()

