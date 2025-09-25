#!/usr/bin/env python3
"""Merge per-cycle freqtrade backtest results and emit a concise summary."""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile


@dataclass
class CycleResult:
    cycle_id: int
    name: str
    start: str
    end: str
    timerange: str
    trades: int
    wins: int
    losses: int
    draws: int
    win_rate: float | None
    profit_ratio: float
    profit_abs: float
    profit_factor: float | None
    cagr: float | None
    max_drawdown: float | None
    max_drawdown_abs: float | None
    trades_per_day: float | None
    starting_balance: float
    final_balance: float
    result_file: Path
    notes: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "timerange": self.timerange,
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "win_rate": self.win_rate,
            "profit_ratio": self.profit_ratio,
            "profit_abs": self.profit_abs,
            "profit_factor": self.profit_factor,
            "cagr": self.cagr,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_abs": self.max_drawdown_abs,
            "trades_per_day": self.trades_per_day,
            "starting_balance": self.starting_balance,
            "final_balance": self.final_balance,
            "result_file": str(self.result_file),
            "notes": self.notes,
        }


def load_cycles(cycles_path: Path) -> list[dict[str, Any]]:
    with cycles_path.open() as handle:
        cycles = json.load(handle)
    if not isinstance(cycles, list):
        raise ValueError("cycles.json must contain a top-level list")
    return cycles


def find_latest_backtest_file(result_dir: Path) -> Path | None:
    candidates = sorted(result_dir.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        candidates = sorted(result_dir.glob("backtest-result-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def read_backtest_payload(backtest_file: Path) -> dict[str, Any]:
    if backtest_file.suffix == ".zip":
        json_name = f"{backtest_file.stem}.json"
        with ZipFile(backtest_file) as archive:
            with archive.open(json_name) as handle:
                return json.load(handle)
    return json.loads(backtest_file.read_text())


def read_metadata(backtest_file: Path) -> dict[str, Any]:
    meta_path = backtest_file.parent / f"{backtest_file.stem}.meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}


def safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_markdown(strategy: str, rows: list[CycleResult], aggregate: dict[str, Any]) -> str:
    headers = [
        "Cycle",
        "Timerange",
        "Trades",
        "Win%",
        "Profit %",
        "Profit (abs)",
        "PF",
        "Max DD",
        "CAGR",
    ]
    table_lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]

    for row in rows:
        timerange = f"{row.start} → {row.end}"
        win_pct = f"{row.win_rate * 100:.2f}%" if row.win_rate is not None else "n/a"
        pf = f"{row.profit_factor:.2f}" if row.profit_factor not in (None, 0) else "n/a"
        max_dd = f"{row.max_drawdown * 100:.2f}%" if row.max_drawdown is not None else "n/a"
        cagr = f"{row.cagr * 100:.2f}%" if row.cagr is not None else "n/a"
        md_line = "| " + " | ".join(
            [
                f"#{row.cycle_id} {row.name}",
                timerange,
                str(row.trades),
                win_pct,
                f"{row.profit_ratio * 100:.2f}%",
                f"{row.profit_abs:.2f}",
                pf,
                max_dd,
                cagr,
            ]
        ) + " |"
        table_lines.append(md_line)

    summary_lines = [
        f"### Aggregated ({strategy})",
        f"- Total trades: {aggregate['total_trades']}",
        f"- Win rate: {aggregate['win_rate']:.2f}%",
        f"- Combined ROI: {aggregate['roi_pct']:.2f}%",
        f"- Absolute profit: {aggregate['profit_abs']:.2f} {aggregate['stake_currency']}",
        f"- Worst drawdown: {aggregate['worst_drawdown_pct']:.2f}%",
    ]

    return "\n".join([f"## Cycle Breakdown ({strategy})"] + table_lines + ["", *summary_lines])


def collect_cycle_result(
    cycle: dict[str, Any],
    strategy: str,
    result_root: Path,
) -> CycleResult | None:
    cid = cycle.get("id")
    if cid is None:
        raise ValueError("Each cycle entry must include an 'id'.")
    result_dir = result_root / f"cycle_{cid}"
    if not result_dir.exists():
        print(f"Warning: result directory missing for cycle {cid}: {result_dir}", file=sys.stderr)
        return None

    backtest_file = find_latest_backtest_file(result_dir)
    if not backtest_file:
        print(f"Warning: no backtest results found in {result_dir}", file=sys.stderr)
        return None

    payload = read_backtest_payload(backtest_file)
    strategy_data = payload.get("strategy", {}).get(strategy)
    if not strategy_data:
        print(f"Warning: strategy '{strategy}' not found in {backtest_file}", file=sys.stderr)
        return None

    metadata = read_metadata(backtest_file).get(strategy, {})

    start_iso = cycle["date_range"]["start"]
    end_iso = cycle["date_range"]["end"]
    timerange = f"{start_iso.replace('-', '')}-{end_iso.replace('-', '')}"

    wins = int(strategy_data.get("wins", 0))
    losses = int(strategy_data.get("losses", 0))
    total = wins + losses
    win_rate = (wins / total) if total else None

    profit_factor = safe_float(strategy_data.get("profit_factor"))
    cagr = safe_float(strategy_data.get("cagr"))
    max_dd = safe_float(strategy_data.get("max_drawdown_account"))
    if max_dd is None:
        max_dd = safe_float(strategy_data.get("max_drawdown"))
    trades_per_day = safe_float(strategy_data.get("trades_per_day"))
    max_dd_abs = safe_float(strategy_data.get("max_drawdown_abs"))

    return CycleResult(
        cycle_id=int(cid),
        name=cycle.get("name", f"Cycle {cid}"),
        start=start_iso,
        end=end_iso,
        timerange=timerange,
        trades=int(strategy_data.get("total_trades", 0)),
        wins=wins,
        losses=losses,
        draws=int(strategy_data.get("draws", 0)),
        win_rate=win_rate,
        profit_ratio=float(strategy_data.get("profit_total", 0.0)),
        profit_abs=float(strategy_data.get("profit_total_abs", 0.0)),
        profit_factor=profit_factor,
        cagr=cagr,
        max_drawdown=max_dd,
        max_drawdown_abs=max_dd_abs,
        trades_per_day=trades_per_day,
        starting_balance=float(strategy_data.get("starting_balance", 0.0)),
        final_balance=float(strategy_data.get("final_balance", 0.0)),
        result_file=backtest_file,
        notes=metadata.get("notes"),
    )


def detect_stake_currency(result_root: Path) -> str:
    candidate = result_root.parent / "config.json"
    if candidate.exists():
        try:
            with candidate.open() as handle:
                data = json.load(handle)
            return data.get("stake_currency", "USDT")
        except (json.JSONDecodeError, OSError):
            pass
    return "USDT"


def compute_aggregate(rows: list[CycleResult], stake_currency: str) -> dict[str, Any]:
    profit_abs = sum(r.profit_abs for r in rows)
    starting_capital = sum(r.starting_balance for r in rows)
    roi_pct = (profit_abs / starting_capital * 100.0) if starting_capital else 0.0
    total_trades = sum(r.trades for r in rows)
    total_wins = sum(r.wins for r in rows)
    total_losses = sum(r.losses for r in rows)
    worst_drawdown = max((r.max_drawdown for r in rows if r.max_drawdown is not None), default=0.0)
    win_rate = (total_wins / (total_wins + total_losses) * 100.0) if (total_wins + total_losses) else 0.0
    return {
        "profit_abs": profit_abs,
        "roi_pct": roi_pct,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "worst_drawdown_pct": worst_drawdown * 100 if worst_drawdown is not None else 0.0,
        "stake_currency": stake_currency,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parent
    parser.add_argument("--strategy", default="ElliotV5_SMA", help="Strategy name to summarise")
    parser.add_argument("--cycles", default=str(default_root / "cycles.json"), help="Path to cycles.json")
    parser.add_argument("--results-root", default=str(default_root / "backtest_results"), help="Directory containing per-cycle backtest outputs")
    parser.add_argument("--output-markdown", default=None, help="Optional markdown output path")
    parser.add_argument("--output-json", default=None, help="Optional JSON summary output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cycles_path = Path(args.cycles).expanduser().resolve()
    result_root = Path(args.results_root).expanduser().resolve()

    cycles = load_cycles(cycles_path)
    rows: list[CycleResult] = []
    for cycle in cycles:
        row = collect_cycle_result(cycle, args.strategy, result_root)
        if row:
            rows.append(row)

    if not rows:
        raise SystemExit("No backtest results available to summarise.")

    rows.sort(key=lambda r: r.cycle_id)
    stake_currency = detect_stake_currency(result_root)
    aggregate = compute_aggregate(rows, stake_currency)
    markdown_out = render_markdown(args.strategy, rows, aggregate)

    print(markdown_out)

    md_path = Path(args.output_markdown) if args.output_markdown else result_root / f"summary_{args.strategy}.md"
    json_path = Path(args.output_json) if args.output_json else result_root / f"summary_{args.strategy}.json"

    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    md_path.write_text(markdown_out)
    payload = {
        "strategy": args.strategy,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "cycles": [row.as_dict() for row in rows],
        "aggregate": aggregate,
    }
    json_path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
