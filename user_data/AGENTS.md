# Repository Guidelines

## Project Structure & Module Organization
The repo mirrors freqtrade's `user_data` layout so strategies and resources remain portable. Use `strategies/` in your main freqtrade checkout to store Python strategy classes; generated artifacts reside here: `backtest_results/` for performance exports, `data/` for cached candles, `freqaimodels/` for serialized ML helpers, `hyperopts/` for hyper-optimization payloads, `logs/` for execution logs, and `notebooks/` for exploratory Jupyter workflows. Keep large datasets out of version control unless they are essential and compressed. Document any new subfolders in the root `README` or strategy docstring for quick discovery.

## Build, Test, and Development Commands
Install dependencies inside the main freqtrade environment (`pip install freqtrade` or `poetry install` in the upstream repo) before working here. Typical local loops:
- `freqtrade backtesting --strategy MyStrategy --config user_data/config.json --timerange 20240101-` evaluates performance using cached data.
- `freqtrade hyperopt --spaces buy sell roi stoploss --strategy MyStrategy` tunes parameters saved into `hyperopts/`.
- `freqtrade plot-dataframe --strategy MyStrategy` renders diagnostic charts into `backtest_results/plots/`.
Run commands from the root freqtrade project while pointing to this `user_data` path via `--userdir` when needed.

## Coding Style & Naming Conventions
Write Python 3 code with four-space indentation, PEP 8 spacing, and descriptive, CamelCase strategy class names (e.g., `MomentumAtrStrategy`). Keep indicator helpers in dedicated modules and import them inside strategies to avoid circular logic. Prefer type hints and dataclasses for shared utilities. Format code with `black` (line length 88) and lint using `ruff` or `flake8` to mirror upstream expectations. Name exported artifacts with ISO dates: `backtest_results/2024-06-15_mystrategy.json`.

## Testing Guidelines
Validate logic with `freqtrade test-strategy --strategy MyStrategy` before committing. For indicator utilities, add unit tests in the upstream repo's `freqtrade/tests/` and run `pytest -k mystrategy`. Capture benchmark metrics (win rate, profit ratio) in a short markdown note under `backtest_results/notes/`. Reject changes if backtests regress materially or if hyperopt loses tracked metrics; record comparison tables when deviations occur.

## Commit & Pull Request Guidelines
Craft commits in imperative mood (`Add leverage guard`). Keep scope focused and include relevant command outputs in the commit description when helpful. Pull requests should: 1) explain the trading rationale and data sources, 2) link issues or experiment tickets, 3) attach key plots or logs from the latest backtest, and 4) list manual verification steps (`freqtrade backtesting ...`). Request review before merging significant strategy changes or risk parameter tweaks.
