# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Freqtrade is a free and open-source cryptocurrency trading bot written in Python. It supports automated trading across major exchanges, includes backtesting and optimization capabilities, and features machine learning integration via FreqAI.

## Development Commands

### Environment Setup
```bash
# Initial setup (creates virtual environment and installs dependencies)
./setup.sh --install

# Update existing installation
./setup.sh --update

# Reset environment and reinstall
./setup.sh --reset

# Activate virtual environment
source .venv/bin/activate
```

### Core Commands
```bash
# Run the trading bot
freqtrade trade --config user_data/config.json

# Create new configuration
freqtrade new-config -c user_data/config.json

# Create new strategy
freqtrade new-strategy --strategy MyStrategy

# Download historical data
freqtrade download-data --exchange binance --pairs BTC/USDT ETH/USDT --timeframes 5m 1h

# Run backtesting
freqtrade backtesting --config user_data/config.json --strategy MyStrategy

# Run hyperparameter optimization
freqtrade hyperopt --config user_data/config.json --hyperopt-loss SharpeHyperOptLoss --strategy MyStrategy
```

### Code Quality & Testing
```bash
# Run all tests
pytest

# Run tests in parallel
pytest --dist loadscope

# Run specific test module
pytest tests/test_freqtradebot.py

# Code linting
ruff check

# Type checking
mypy freqtrade

# Format code
ruff format
```

## Architecture Overview

### Core Components

**Main Bot Logic (`freqtrade/`)**:
- `freqtradebot.py` - Core trading bot implementation
- `main.py` - CLI entry point and command handling
- `worker.py` - Background task management

**Exchange Integration (`freqtrade/exchange/`)**:
- `exchange.py` - Base exchange interface
- Exchange-specific implementations: `binance.py`, `kraken.py`, `okx.py`, etc.
- WebSocket support for real-time data

**Strategy Framework (`freqtrade/strategy/`)**:
- `interface.py` - Strategy base class and interface
- `strategy_helper.py` - Strategy utilities and helpers
- Template strategies in `templates/`

**Data Management (`freqtrade/data/`)**:
- `dataprovider.py` - Centralized data access
- `history/` - Historical data handling and storage
- `converter/` - Data format conversion utilities

**Machine Learning (`freqtrade/freqai/`)**:
- `data_kitchen.py` - Feature engineering pipeline  
- `prediction_models/` - ML model implementations (XGBoost, LightGBM, CatBoost, PyTorch)
- `RL/` - Reinforcement learning environments

**Optimization (`freqtrade/optimize/`)**:
- `backtesting.py` - Strategy backtesting engine
- `hyperopt/` - Hyperparameter optimization
- `optimize_reports/` - Result analysis and reporting

**Remote Control (`freqtrade/rpc/`)**:
- `telegram.py` - Telegram bot integration
- `api_server/` - REST API and WebSocket server
- `webhook.py` - External webhook notifications

### Configuration Structure

- `config_examples/` - Sample configurations for different exchanges
- `user_data/` - User-specific data directory:
  - `config.json` - Main configuration file
  - `strategies/` - Custom trading strategies
  - `data/` - Historical market data
  - `logs/` - Application logs
  - `models/` - FreqAI trained models

### Key Design Patterns

**Plugin Architecture**: Exchanges, strategies, pairlists, and protections are pluggable components with well-defined interfaces.

**Data Pipeline**: Centralized data flow through `DataProvider` with caching and preprocessing layers.

**Event-Driven**: Bot operates on market data events with configurable callbacks and hooks.

**Modular ML**: FreqAI provides a framework for different ML approaches while maintaining consistent interfaces.

## Development Guidelines

### Testing Strategy
- Comprehensive test suite with >90% coverage in `tests/`
- Separate online/offline exchange tests
- Mock external dependencies (exchange APIs, time)
- Use `conftest.py` for shared test fixtures

### Code Organization
- Follow existing module structure when adding features
- Use type hints throughout (checked with mypy)
- Maintain separation between exchange logic and strategy logic
- Keep configuration validation centralized

### Configuration Management
- All settings go through JSON schema validation
- Use `config_schema.py` for new configuration options
- Provide example configurations for new features
- Document configuration in `docs/configuration.md`

### FreqAI Development
- Models inherit from base classes in `base_models/`
- Feature engineering happens in `data_kitchen.py`
- Use consistent naming: `model_save_name` for model identification
- Test models with sample data in `tests/freqai/test_models/`

## Common Workflows

### Adding Exchange Support
1. Create new exchange class inheriting from `Exchange`
2. Implement exchange-specific methods (fees, timeframes, etc.)
3. Add exchange-specific tests
4. Update documentation in `docs/exchanges.md`

### Creating Strategy Templates
1. Add template in `freqtrade/templates/`
2. Update `strategy_subtemplates/` if needed
3. Test template generation with `freqtrade new-strategy`

### Adding FreqAI Models
1. Inherit from appropriate base class (`BaseRegressionModel`, `BaseClassifierModel`)
2. Implement required methods: `fit()`, `predict()`
3. Add model to `prediction_models/` directory
4. Create corresponding test file

### Debugging
- Enable debug logging: `"verbosity": 3` in config
- Use dry-run mode for safe testing: `"dry_run": true`
- Check logs in `user_data/logs/freqtrade.log`
- Use `--db-url sqlite:///tradesv3.dryrun.sqlite` for dry-run database

## Dependencies

**Core**: Python 3.10+, SQLAlchemy, pandas, TA-Lib, CCXT (exchange library)

**Optional Features**:
- **Plotting**: plotly
- **Hyperopt**: scipy, scikit-learn, optuna
- **FreqAI**: lightgbm, xgboost, catboost, tensorboard
- **FreqAI-RL**: torch, gymnasium, stable-baselines3

**Development**: pytest, mypy, ruff, pre-commit (auto-installed with dev setup)

## File Locations

- Main configuration: `user_data/config.json`
- Custom strategies: `user_data/strategies/`
- Historical data: `user_data/data/{exchange}/`
- FreqAI models: `user_data/models/`
- Logs: `user_data/logs/`
- Backtest results: `user_data/backtest_results/`