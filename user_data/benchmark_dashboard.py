#!/usr/bin/env python3
"""Interactive benchmarking dashboard for freqtrade backtest summaries."""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZipFile

HEADLESS = os.getenv("BENCHMARK_DASHBOARD_HEADLESS") == "1"

if not HEADLESS:
    import pandas as pd  # type: ignore
    import streamlit as st  # type: ignore
else:  # pragma: no cover - lightweight fallback for CLI usage
    pd = None  # type: ignore

    class _StubSidebar:
        def header(self, *_args: Any, **_kwargs: Any) -> None:  # noqa: D401 - noop stub
            return

        def multiselect(self, *_args: Any, **_kwargs: Any) -> list[Any]:
            return []

        def number_input(self, *_args: Any, **_kwargs: Any) -> int:
            return 0

        def date_input(self, *_args: Any, **_kwargs: Any) -> tuple[datetime, datetime]:
            today = datetime.utcnow().date()
            return (today, today)

        def selectbox(self, *_args: Any, **_kwargs: Any) -> Any:
            return None

        def checkbox(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

        def markdown(self, *_args: Any, **_kwargs: Any) -> None:
            return

        def write(self, *_args: Any, **_kwargs: Any) -> None:
            return

    class _StubStreamlit:
        sidebar = _StubSidebar()

        @staticmethod
        def set_page_config(*_args: Any, **_kwargs: Any) -> None:
            return

        @staticmethod
        def title(*_args: Any, **_kwargs: Any) -> None:
            return

        @staticmethod
        def warning(msg: str) -> None:
            print(f"[streamlit warning] {msg}")

        @staticmethod
        def subheader(*_args: Any, **_kwargs: Any) -> None:
            return

        @staticmethod
        def dataframe(*_args: Any, **_kwargs: Any) -> None:
            return

    st = _StubStreamlit()  # type: ignore

USER_DIR = Path(__file__).resolve().parent
RESULTS_DIR = USER_DIR / "backtest_results"
SUMMARY_GLOB = "summary_*.json"
SUMMARY_FILTER = os.getenv("BENCHMARK_DASHBOARD_FILTER")
CONTAINER_USER_PREFIXES = (
    Path("/freqtrade/user_data"),
    Path("/app/user_data"),
    Path("/workspace/user_data"),
)


@dataclass
class CycleRecord:
    strategy: str
    cycle_id: int
    cycle_name: str
    start: Any
    end: Any
    trades: int
    wins: int
    losses: int
    winrate: float | None
    profit_abs: float | None
    profit_pct: float | None
    profit_factor: float | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    sqn: float | None
    expectancy: float | None
    cagr: float | None
    max_drawdown_pct: float | None
    max_drawdown_abs: float | None
    trades_per_day: float | None
    notes: str | None
    result_path: Path | None
    source_summary: Path
    stake_currency: str | None = None
    run_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "cycle_id": self.cycle_id,
            "cycle_name": self.cycle_name,
            "start": self.start,
            "end": self.end,
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "winrate": self.winrate,
            "profit_abs": self.profit_abs,
            "profit_pct": self.profit_pct,
            "profit_factor": self.profit_factor,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "calmar": self.calmar,
            "sqn": self.sqn,
            "expectancy": self.expectancy,
            "cagr": self.cagr,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_abs": self.max_drawdown_abs,
            "trades_per_day": self.trades_per_day,
            "notes": self.notes,
            "result_path": str(self.result_path) if self.result_path else None,
            "source_summary": str(self.source_summary),
            "stake_currency": self.stake_currency,
            "run_label": self.run_label,
        }


def resolve_host_path(path_str: str) -> Path | None:
    path = Path(path_str)
    if path.is_absolute():
        for prefix in CONTAINER_USER_PREFIXES:
            if str(path).startswith(str(prefix)):
                rel = path.relative_to(prefix)
                return USER_DIR / rel
        return path
    return (USER_DIR / path).resolve()


def load_strategy_payload(zip_path: Path, strategy: str) -> dict[str, Any] | None:
    if not zip_path.exists():
        return None
    try:
        with ZipFile(zip_path) as archive:
            json_name = f"{zip_path.stem}.json"
            with archive.open(json_name) as handle:
                data = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Failed to load {zip_path.name}: {exc}")
        return None
    return data.get("strategy", {}).get(strategy)


def load_cycle_records(summary_path: Path) -> list[CycleRecord]:
    summary = json.loads(summary_path.read_text())
    strategy = summary.get("strategy", summary_path.stem.replace("summary_", ""))
    records: list[CycleRecord] = []
    for cycle in summary.get("cycles", []):
        host_result = resolve_host_path(cycle.get("result_file", ""))
        payload = load_strategy_payload(host_result, strategy) if host_result else None
        stats = payload or {}
        if pd is not None:
            start = pd.to_datetime(cycle.get("start"))
            end = pd.to_datetime(cycle.get("end"))
        else:
            start = datetime.fromisoformat(cycle.get("start")) if cycle.get("start") else None
            end = datetime.fromisoformat(cycle.get("end")) if cycle.get("end") else None
        run_label = summary.get("run_label") or cycle.get("run_label")
        record = CycleRecord(
            strategy=strategy,
            cycle_id=int(cycle.get("cycle_id", 0)),
            cycle_name=str(cycle.get("name", f"Cycle {cycle.get('cycle_id')}")),
            start=start,
            end=end,
            trades=int(stats.get("total_trades", cycle.get("trades", 0)) or 0),
            wins=int(stats.get("wins", cycle.get("wins", 0)) or 0),
            losses=int(stats.get("losses", cycle.get("losses", 0)) or 0),
            winrate=float(stats.get("winrate", cycle.get("win_rate"))) if stats.get("winrate") is not None or cycle.get("win_rate") is not None else None,
            profit_abs=float(stats.get("profit_total_abs", cycle.get("profit_abs"))) if stats.get("profit_total_abs") is not None or cycle.get("profit_abs") is not None else None,
            profit_pct=float(stats.get("profit_total", cycle.get("profit_ratio"))) if stats.get("profit_total") is not None or cycle.get("profit_ratio") is not None else None,
            profit_factor=float(stats.get("profit_factor", cycle.get("profit_factor"))) if stats.get("profit_factor") is not None or cycle.get("profit_factor") is not None else None,
            sharpe=float(stats.get("sharpe")) if stats.get("sharpe") is not None else None,
            sortino=float(stats.get("sortino")) if stats.get("sortino") is not None else None,
            calmar=float(stats.get("calmar")) if stats.get("calmar") is not None else None,
            sqn=float(stats.get("sqn")) if stats.get("sqn") is not None else None,
            expectancy=float(stats.get("expectancy")) if stats.get("expectancy") is not None else None,
            cagr=float(stats.get("cagr", cycle.get("cagr"))) if stats.get("cagr") is not None or cycle.get("cagr") is not None else None,
            max_drawdown_pct=float(stats.get("max_drawdown_account")) if stats.get("max_drawdown_account") is not None else (float(cycle.get("max_drawdown")) if cycle.get("max_drawdown") is not None else None),
            max_drawdown_abs=float(stats.get("max_drawdown_abs")) if stats.get("max_drawdown_abs") is not None else None,
            trades_per_day=float(stats.get("trades_per_day", cycle.get("trades_per_day"))) if stats.get("trades_per_day") is not None or cycle.get("trades_per_day") is not None else None,
            notes=str(cycle.get("notes")) if cycle.get("notes") else None,
            result_path=host_result,
            source_summary=summary_path,
            stake_currency=str(summary.get("aggregate", {}).get("stake_currency")),
            run_label=str(run_label) if run_label is not None else None,
        )
        records.append(record)
    return records


def load_all_records(results_dir: Path):  # type: ignore[override]
    summaries = sorted(results_dir.rglob(SUMMARY_GLOB))
    if SUMMARY_FILTER:
        summaries = [path for path in summaries if SUMMARY_FILTER in str(path)]
    rows: list[dict[str, Any]] = []
    for summary_path in summaries:
        rows.extend(rec.to_dict() for rec in load_cycle_records(summary_path))
    if pd is None:
        return rows
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["duration_days"] = (df["end"] - df["start"]).dt.days
    df["winrate_pct"] = df["winrate"] * 100
    df["max_drawdown_pct"] = df["max_drawdown_pct"].apply(lambda v: v * 100 if isinstance(v, (int, float)) else v)
    df["profit_pct"] = df["profit_pct"].apply(lambda v: v * 100 if isinstance(v, (int, float)) else v)
    return df


def weighted_average(series: pd.Series, weights: pd.Series) -> float | None:
    valid = (~series.isna()) & (~weights.isna())
    if not valid.any():
        return None
    w = weights[valid]
    if (w.sum() == 0) or math.isclose(w.sum(), 0.0, abs_tol=1e-12):
        return float(series[valid].mean())
    return float((series[valid] * w).sum() / w.sum())


def render_dashboard(df: pd.DataFrame) -> None:
    st.set_page_config(page_title="Freqtrade Benchmark Dashboard", layout="wide")
    st.title("Freqtrade Strategy Benchmark Dashboard")

    if df.empty:
        st.warning("No summary files found. Run analyze_backtests.py to generate summary JSON files.")
        return

    st.sidebar.header("Filters")
    strategies = sorted(df["strategy"].unique())
    selected_strategies = st.sidebar.multiselect("Strategy", strategies, default=strategies)
    df_filtered = df[df["strategy"].isin(selected_strategies)] if selected_strategies else df

    cycles = sorted(df_filtered["cycle_name"].unique())
    selected_cycles = st.sidebar.multiselect("Cycle", cycles, default=cycles)
    if selected_cycles:
        df_filtered = df_filtered[df_filtered["cycle_name"].isin(selected_cycles)]

    min_trades = st.sidebar.number_input("Minimum trades", min_value=0, value=0, step=10)
    if min_trades:
        df_filtered = df_filtered[df_filtered["trades"] >= min_trades]

    date_min = df_filtered["start"].min()
    date_max = df_filtered["end"].max()
    if pd.notna(date_min) and pd.notna(date_max):
        date_range = st.sidebar.date_input("Date range", value=(date_min.date(), date_max.date()))
        if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
            start_filter, end_filter = map(pd.to_datetime, date_range)
            df_filtered = df_filtered[(df_filtered["end"] >= start_filter) & (df_filtered["start"] <= end_filter)]

    sort_options = {
        "Total Profit (abs)": "profit_abs",
        "Total Profit (%)": "profit_pct",
        "Profit Factor": "profit_factor",
        "Sharpe": "sharpe",
        "Win Rate": "winrate",
        "Max Drawdown (%)": "max_drawdown_pct",
        "Trades": "trades",
    }
    sort_label = st.sidebar.selectbox("Sort by", list(sort_options.keys()), index=0)
    ascending = st.sidebar.checkbox("Ascending", value=False)

    df_display = df_filtered.copy()
    df_display_sorted = df_display.sort_values(by=sort_options[sort_label], ascending=ascending, na_position="last")

    column_labels = {
        "strategy": "Strategy",
        "run_label": "Run Label",
        "cycle_name": "Cycle",
        "trades": "Trades",
        "winrate_pct": "Win Rate (%)",
        "sharpe": "Sharpe",
        "profit_factor": "Profit Factor",
        "profit_abs": "Total Profit",
        "profit_pct": "Total Profit (%)",
        "max_drawdown_pct": "Max Drawdown (%)",
        "max_drawdown_abs": "Max Drawdown (abs)",
        "cagr": "CAGR",
        "sortino": "Sortino",
        "calmar": "Calmar",
        "sqn": "SQN",
        "trades_per_day": "Trades / Day",
        "notes": "Notes",
    }
    display_cols = [
        "strategy",
        "run_label",
        "cycle_name",
        "trades",
        "winrate_pct",
        "sharpe",
        "profit_factor",
        "profit_abs",
        "profit_pct",
        "max_drawdown_pct",
        "max_drawdown_abs",
        "cagr",
        "sortino",
        "calmar",
        "sqn",
        "trades_per_day",
        "notes",
    ]
    st.subheader("Cycle Level Results")
    st.dataframe(
        df_display_sorted[display_cols].rename(columns=column_labels).style.format({
            "Win Rate (%)": "{:.2f}",
            "Sharpe": "{:.2f}",
            "Profit Factor": "{:.2f}",
            "Total Profit": "{:.2f}",
            "Total Profit (%)": "{:.2f}",
            "Max Drawdown (%)": "{:.2f}",
            "Max Drawdown (abs)": "{:.2f}",
            "CAGR": "{:.2f}",
            "Sortino": "{:.2f}",
            "Calmar": "{:.2f}",
            "SQN": "{:.2f}",
            "Trades / Day": "{:.2f}",
        }),
        width="stretch",
    )

    st.subheader("Strategy Aggregates")
    agg_rows: list[dict[str, Any]] = []
    for (strategy, run_label), group in df_filtered.groupby(["strategy", "run_label"], dropna=False):
        total_trades = int(group["trades"].sum())
        agg_rows.append({
            "Strategy": strategy,
            "Run Label": run_label,
            "Cycles": group["cycle_id"].nunique(),
            "Total Trades": total_trades,
            "Total Profit": group["profit_abs"].sum(),
            "Total Profit (%)": group["profit_pct"].sum(skipna=True),
            "Weighted Win Rate (%)": weighted_average(group["winrate_pct"], group["trades"]),
            "Weighted Sharpe": weighted_average(group["sharpe"], group["trades"]),
            "Weighted Profit Factor": weighted_average(group["profit_factor"], group["trades"]),
            "Worst Drawdown (%)": group["max_drawdown_pct"].max(),
            "Worst Drawdown (abs)": group["max_drawdown_abs"].max(),
            "CAGR Avg": weighted_average(group["cagr"], group["duration_days"].replace(0, 1)),
        })
    agg_df = pd.DataFrame(agg_rows)
    if not agg_df.empty:
        agg_sort_map = {
            "Total Profit (abs)": "Total Profit",
            "Total Profit (%)": "Total Profit (%)",
            "Profit Factor": "Weighted Profit Factor",
            "Sharpe": "Weighted Sharpe",
            "Win Rate": "Weighted Win Rate (%)",
            "Max Drawdown (%)": "Worst Drawdown (%)",
            "Trades": "Total Trades",
        }
        agg_sort_col = agg_sort_map.get(sort_label, "Total Profit")
        agg_df = agg_df.sort_values(by=[agg_sort_col, "Strategy", "Run Label"], ascending=ascending, na_position="last")
        st.dataframe(
            agg_df.style.format({
                "Total Profit": "{:.2f}",
                "Total Profit (%)": "{:.2f}",
                "Weighted Win Rate (%)": "{:.2f}",
                "Weighted Sharpe": "{:.2f}",
                "Weighted Profit Factor": "{:.2f}",
                "Worst Drawdown (%)": "{:.2f}",
                "Worst Drawdown (abs)": "{:.2f}",
                "CAGR Avg": "{:.2f}",
            }),
            width="stretch",
        )

    st.sidebar.markdown("---")
    st.sidebar.write(f"Loaded {len(df_filtered)} cycle rows from {len(df_filtered['strategy'].unique())} strategies")


def render_cli(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No cycle summaries found under", RESULTS_DIR)
        return
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["source_summary"], []).append(row)

    for summary_path, entries in grouped.items():
        summary = json.loads(Path(summary_path).read_text())
        strategy = summary.get("strategy", entries[0].get("strategy"))
        aggregate = summary.get("aggregate", {})
        currency = aggregate.get("stake_currency", entries[0].get("stake_currency", "USDT"))
        run_label = summary.get("run_label") or aggregate.get("run_label")
        total_trades = aggregate.get("total_trades") or sum(row.get("trades", 0) for row in entries)
        total_profit = aggregate.get("profit_abs")
        total_roi = aggregate.get("roi_pct")
        worst_dd = aggregate.get("worst_drawdown_pct")

        print(f"Summary: {Path(summary_path).relative_to(RESULTS_DIR)}")
        print(f"  Strategy: {strategy}")
        if run_label:
            print(f"  Run label: {run_label}")
        print(f"  Total trades: {total_trades}")
        if total_profit is not None and total_roi is not None:
            print(f"  Total profit: {total_profit:.2f} {currency} (ROI {total_roi:.2f}%)")
        if worst_dd is not None:
            print(f"  Worst drawdown: {worst_dd:.2f}%")
        for row in sorted(entries, key=lambda x: x.get("cycle_id", 0)):
            profit_pct = (row.get("profit_pct") or 0.0) * 100
            win_pct = (row.get("winrate") or 0.0) * 100
            dd_pct = (row.get("max_drawdown_pct") or 0.0) * 100
            print(
                f"    Cycle {row['cycle_id']}: {row['cycle_name']} -> profit {row.get('profit_abs'):.2f} ({profit_pct:.2f}%), "
                f"win {win_pct:.2f}%, DD {dd_pct:.2f}%"
            )
        print()


if __name__ == "__main__":
    data_frame = load_all_records(RESULTS_DIR)
    if pd is None:
        render_cli(data_frame)
    else:
        render_dashboard(data_frame)
