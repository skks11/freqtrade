#!/usr/bin/env bash
# Orchestrate freqtrade data downloads and backtests for ElliotV5_SMA using Docker.
set -euo pipefail

abs_path() {
  python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-"$SCRIPT_DIR/.."}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"
USER_DIR_ABS=${USER_DIR:-"$SCRIPT_DIR"}
USER_DIR="$(abs_path "$USER_DIR_ABS")"
CONFIG_PATH_INPUT=${CONFIG_PATH:-"$USER_DIR/config.json"}
CYCLES_PATH_INPUT=${CYCLES_PATH:-"$USER_DIR/cycles.json"}
STRATEGY=${STRATEGY:-"ElliotV5_SMA"}
TIMEFRAMES=${TIMEFRAMES:-"5m 1h"}
RESULT_ROOT_INPUT=${RESULT_ROOT:-"$USER_DIR/backtest_results"}
ANALYSIS_SCRIPT_INPUT=${ANALYSIS_SCRIPT:-"$USER_DIR/analyze_backtests.py"}
RUN_ANALYSIS=${RUN_ANALYSIS:-"1"}
COMPOSE_FILE=${COMPOSE_FILE:-"$PROJECT_ROOT/docker-compose.yml"}
CONTAINER_USER_DIR=${CONTAINER_USER_DIR:-"/freqtrade/user_data"}
EXTRA_ARGS=()

usage() {
  cat <<USAGE
Usage: ${0##*/} [options] [-- <additional-freqtrade-args>]

Options:
  -s, --strategy NAME       Strategy class to run (default: ElliotV5_SMA)
  -c, --config PATH         Config file on host (default: user_data/config.json)
  -y, --cycles PATH         cycles.json file (default: user_data/cycles.json)
  -o, --output DIR          Root directory for per-cycle results (default: user_data/backtest_results)
  -t, --timeframes "TFs"    Space separated list of timeframes to download (default: "5m 1h")
  -n, --no-analysis         Skip post-processing summary step
  -h, --help                Show this help text

Environment variables:
  PROJECT_ROOT, USER_DIR, CONFIG_PATH, CYCLES_PATH, STRATEGY, TIMEFRAMES,
  RESULT_ROOT, ANALYSIS_SCRIPT, RUN_ANALYSIS, COMPOSE_FILE, CONTAINER_USER_DIR,
  DOCKER_COMPOSE (override docker compose executable)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--strategy)
      STRATEGY="$2"; shift 2 ;;
    -c|--config)
      CONFIG_PATH_INPUT="$2"; shift 2 ;;
    -y|--cycles)
      CYCLES_PATH_INPUT="$2"; shift 2 ;;
    -o|--output)
      RESULT_ROOT_INPUT="$2"; shift 2 ;;
    -t|--timeframes)
      TIMEFRAMES="$2"; shift 2 ;;
    -n|--no-analysis)
      RUN_ANALYSIS="0"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    --)
      shift; EXTRA_ARGS=("$@"); break ;;
    *)
      echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

CONFIG_PATH="$(abs_path "$CONFIG_PATH_INPUT")"
CYCLES_PATH="$(abs_path "$CYCLES_PATH_INPUT")"
RESULT_ROOT="$(abs_path "$RESULT_ROOT_INPUT")"
ANALYSIS_SCRIPT="$(abs_path "$ANALYSIS_SCRIPT_INPUT")"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Error: docker compose file not found at $COMPOSE_FILE" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Error: config file '$CONFIG_PATH' not found" >&2
  exit 1
fi

if [[ ! -f "$CYCLES_PATH" ]]; then
  echo "Error: cycles file '$CYCLES_PATH' not found" >&2
  exit 1
fi

mkdir -p "$RESULT_ROOT"

if [[ "$CONFIG_PATH" != "$USER_DIR"/* ]]; then
  echo "Error: config file must reside inside $USER_DIR" >&2
  exit 1
fi
if [[ "$CYCLES_PATH" != "$USER_DIR"/* ]]; then
  echo "Error: cycles file must reside inside $USER_DIR" >&2
  exit 1
fi
if [[ "$ANALYSIS_SCRIPT" != "$USER_DIR"/* ]]; then
  echo "Error: analysis script must reside inside $USER_DIR" >&2
  exit 1
fi
if [[ "$RESULT_ROOT" != "$USER_DIR"/* ]]; then
  echo "Error: result directory must reside inside $USER_DIR" >&2
  exit 1
fi

# Prepare working config (ensure spot mode + accessible path).
WORKING_CONFIG="$USER_DIR/.backtest_config.json"
CONFIG_COPY_OUT=$(python3 - "$CONFIG_PATH" "$WORKING_CONFIG" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
dest = Path(sys.argv[2])
with source.open() as handle:
    data = json.load(handle)
modified = False
if data.get("trading_mode") != "spot":
    data["trading_mode"] = "spot"
    modified = True
if data.get("margin_mode"):
    data.pop("margin_mode", None)
    modified = True
if data.get("pairlists"):
    data["pairlists"] = [{"method": "StaticPairList"}]
    modified = True
with dest.open("w") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
print(dest)
print("modified" if modified else "copied")
PY
)
CONFIG_FOR_RUN=$(printf '%s
' "$CONFIG_COPY_OUT" | sed -n '1p')
CONFIG_STATUS=$(printf '%s
' "$CONFIG_COPY_OUT" | sed -n '2p')

# Determine docker compose executable
if [[ -n "${DOCKER_COMPOSE:-}" ]]; then
  IFS=' ' read -r -a DOCKER_COMPOSE_BIN <<<"$DOCKER_COMPOSE"
else
  if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_BIN=(docker compose)
  elif docker-compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_BIN=(docker-compose)
  else
    echo "Error: docker compose plugin or docker-compose binary not found" >&2
    exit 1
  fi
fi

to_container_path() {
  local host_path="$1"
  if [[ "$host_path" == "$USER_DIR" ]]; then
    printf '%s\n' "$CONTAINER_USER_DIR"
    return
  fi
  if [[ "$host_path" == "$USER_DIR"/* ]]; then
    local rel="${host_path#$USER_DIR/}"
    printf '%s/%s\n' "$CONTAINER_USER_DIR" "$rel"
    return
  fi
  echo "Error: path '$host_path' must reside inside $USER_DIR" >&2
  exit 1
}

compose_freqtrade() {
  "${DOCKER_COMPOSE_BIN[@]}" -f "$COMPOSE_FILE" run --rm --no-deps -T freqtrade "$@"
}

compose_python() {
  "${DOCKER_COMPOSE_BIN[@]}" -f "$COMPOSE_FILE" run --rm --no-deps -T --entrypoint python freqtrade "$@"
}

CONFIG_CONTAINER=$(to_container_path "$CONFIG_FOR_RUN")
CYCLES_CONTAINER=$(to_container_path "$CYCLES_PATH")
RESULT_CONTAINER=$(to_container_path "$RESULT_ROOT")
ANALYSIS_CONTAINER=$(to_container_path "$ANALYSIS_SCRIPT")

CYCLE_LINES=()
while IFS= read -r line; do
  CYCLE_LINES+=("$line")
done < <(CYCLES_PATH="$CYCLES_PATH" python3 - <<'PY'
import json
import os
import sys
from datetime import datetime
from pathlib import Path

cycles_path = Path(os.environ["CYCLES_PATH"]).expanduser().resolve()
if not cycles_path.exists():
    sys.exit("cycles.json not found")
cycles = json.loads(cycles_path.read_text())
if not cycles:
    sys.exit("cycles.json is empty")

fmt = "%Y-%m-%d"
start_dates = [datetime.strptime(c["date_range"]["start"], fmt) for c in cycles]
end_dates = [datetime.strptime(c["date_range"]["end"], fmt) for c in cycles]
min_start = min(start_dates)
max_end = max(end_dates)
print("GLOBAL|{}|{}|{}|{}".format(
    min_start.strftime("%Y%m%d"),
    max_end.strftime("%Y%m%d"),
    min_start.strftime(fmt),
    max_end.strftime(fmt)
))
for cycle in cycles:
    cid = cycle["id"]
    name = cycle.get("name", f"Cycle {cid}")
    start = cycle["date_range"]["start"]
    end = cycle["date_range"]["end"]
    print("{}|{}|{}|{}|{}|{}".format(
        cid,
        datetime.strptime(start, fmt).strftime("%Y%m%d"),
        datetime.strptime(end, fmt).strftime("%Y%m%d"),
        start,
        end,
        name.replace("|", "/")
    ))
PY
)

if [[ ${#CYCLE_LINES[@]} -eq 0 ]]; then
  echo "Error: Failed to parse cycles" >&2
  exit 1
fi

GLOBAL_LINE="${CYCLE_LINES[0]}"
IFS='|' read -r _ GLOBAL_START GLOBAL_END GLOBAL_START_ISO GLOBAL_END_ISO <<<"$GLOBAL_LINE"
DOWNLOAD_TIMERANGE="${GLOBAL_START}-${GLOBAL_END}"

echo "Using working config: $CONFIG_FOR_RUN ($CONFIG_STATUS)"
echo "Downloading data via Docker for timerange ${GLOBAL_START_ISO} -> ${GLOBAL_END_ISO} (${DOWNLOAD_TIMERANGE})"
DOWNLOAD_CMD=(download-data
  --config "$CONFIG_CONTAINER"
  --userdir "$CONTAINER_USER_DIR"
  --timerange "$DOWNLOAD_TIMERANGE"
  --timeframes $TIMEFRAMES
)
compose_freqtrade "${DOWNLOAD_CMD[@]}"

declare -a RESULT_PATHS=()

echo "\nRunning backtests for strategy '$STRATEGY' (Docker)"
for (( idx=1; idx<${#CYCLE_LINES[@]}; idx++ )); do
  IFS='|' read -r CYCLE_ID START_TS END_TS START_ISO END_ISO CYCLE_NAME <<<"${CYCLE_LINES[$idx]}"
  TIMERANGE="${START_TS}-${END_TS}"
  CYCLE_DIR="$RESULT_ROOT/cycle_${CYCLE_ID}"
  mkdir -p "$CYCLE_DIR"
  NOTE="Cycle ${CYCLE_ID}: ${CYCLE_NAME} (${START_ISO} → ${END_ISO})"
  echo "- Cycle ${CYCLE_ID}: ${CYCLE_NAME} (${TIMERANGE})"
  BACKTEST_CMD=(backtesting
    --config "$CONFIG_CONTAINER"
    --userdir "$CONTAINER_USER_DIR"
    --strategy "$STRATEGY"
    --timerange "$TIMERANGE"
    --export trades
    --backtest-directory "$RESULT_CONTAINER/cycle_${CYCLE_ID}"
    --notes "$NOTE"
  )
  if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    BACKTEST_CMD+=("${EXTRA_ARGS[@]}")
  fi
  compose_freqtrade "${BACKTEST_CMD[@]}"
  RESULT_PATHS+=("$CYCLE_DIR")
done

echo "\nBacktests complete. Results stored under:"
for path in "${RESULT_PATHS[@]}"; do
  echo "  - $path"
done

if [[ "$RUN_ANALYSIS" != "0" ]]; then
  if [[ ! -f "$ANALYSIS_SCRIPT" ]]; then
    echo "Warning: Analysis script '$ANALYSIS_SCRIPT' not found. Skipping summary." >&2
    exit 0
  fi
  echo "\nGenerating merged analysis via Docker"
  ANALYZE_CMD=("$ANALYSIS_CONTAINER"
    --strategy "$STRATEGY"
    --cycles "$CYCLES_CONTAINER"
    --results-root "$RESULT_CONTAINER"
  )
  compose_python "${ANALYZE_CMD[@]}"
fi
