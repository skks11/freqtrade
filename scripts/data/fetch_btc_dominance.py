from datetime import datetime, timezone
import time
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

# ---- config ----
SYMBOL = "BTC.D"
EXCHANGE = "CRYPTOCAP"
INTERVAL = Interval.in_30_minute
START_DATE_UTC = datetime(2020, 1, 1, tzinfo=timezone.utc)

# chunk size per request. Many tvdatafeed builds will cap at ~5000 bars / call
# so we force a rolling-window approach: move the "end anchor" back in time.
CHUNK_BARS = 4800          # 30m bars -> ~100 days per chunk (48 bars/day * 100)
BACKOFF_SEC = 1.2          # polite pause between requests
MAX_RETRY = 3

# ---- login ----
# Option A: guest (may be throttled)
tv = TvDatafeed()

# Option B: login for stability (uncomment and fill in)
# tv = TvDatafeed(username="YOUR_TV_USERNAME", password="YOUR_TV_PASSWORD")

def pull_latest_n_bars(n_bars: int):
    """Fetch the latest n_bars bars for BTC.D 30-min.
    Some tvdatafeed builds accept n_bars > 5000 and auto-paginate; others cap at ~5000.
    This function is kept small; we handle windowing outside."""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            df = tv.get_hist(
                symbol=SYMBOL,
                exchange=EXCHANGE,
                interval=INTERVAL,
                n_bars=n_bars
            )
            return df
        except Exception as e:
            if attempt >= MAX_RETRY:
                raise
            time.sleep(BACKOFF_SEC * attempt)


def merge_unique(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Combine 2 OHLCV frames, keeping the latest duplicate per timestamp."""
    if new is None or new.empty:
        return existing

    combined = pd.concat([existing, new])
    combined = combined.sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined

def fetch_btcd_30m_since_2020():
    """
    Strategy:
      1) Pull a chunk of most recent bars (e.g., last ~100 days).
      2) Move the anchor to the earliest timestamp we have, then request a BIGGER window
         that *ends* at that anchor (by asking for more total bars), repeating until
         the earliest date <= START_DATE_UTC.
      Why this works:
         - In most tvdatafeed builds, get_hist returns the *latest* n_bars.
         - So to "move back in time", we re-call with a *larger* n_bars so that the
           window extends further into the past (then we slice only the newly-revealed head).
    """
    # bootstrap
    df_last = pull_latest_n_bars(CHUNK_BARS)
    if df_last is None or df_last.empty:
        raise RuntimeError("No data returned in the first chunk. Try logging in with credentials.")

    df_last.index = pd.to_datetime(df_last.index, utc=True)
    df_last = df_last.sort_index()
    collected = df_last.copy()

    print(f"[init] got {len(df_last)} rows. earliest={collected.index[0]} latest={collected.index[-1]}")

    # If library caps at ~5000 bars, we expand the window progressively
    total_bars = len(df_last)

    # loop until we’ve reached 2020-01-01 (UTC)
    while collected.index[0] > START_DATE_UTC:
        total_bars += CHUNK_BARS  # ask for a bigger historical window
        df_big = pull_latest_n_bars(total_bars)

        # defensive: if provider still returns the same earliest/size, we’ll try a few more bumps
        if df_big is None or df_big.empty:
            print("[warn] empty chunk, backing off...")
            time.sleep(BACKOFF_SEC)
            continue

        df_big.index = pd.to_datetime(df_big.index, utc=True)
        df_big = df_big.sort_index()

        # merge & dedup
        before_rows = len(collected)
        collected = merge_unique(collected, df_big)
        after_rows = len(collected)

        print(f"[expand] asked={total_bars} rows -> merged {after_rows} rows "
              f"(+{after_rows - before_rows}), earliest={collected.index[0]}")

        # stop condition if no progress
        if after_rows == before_rows:
            # If we’re not extending earlier, try a few more bumps; otherwise break to avoid infinite loop.
            # You can also reduce CHUNK_BARS to smaller steps to coax more history.
            bump_attempts = 0
            while bump_attempts < 3 and collected.index[0] > START_DATE_UTC:
                total_bars += CHUNK_BARS
                bump_attempts += 1
                df_big = pull_latest_n_bars(total_bars)
                if df_big is None or df_big.empty:
                    continue
                df_big.index = pd.to_datetime(df_big.index, utc=True)
                df_big = df_big.sort_index()
                prev_earliest = collected.index[0]
                collected = merge_unique(collected, df_big)
                if collected.index[0] < prev_earliest:
                    print(f"[bump] earliest moved to {collected.index[0]} with ask={total_bars}")
                    break
            else:
                print("[stop] no further progress; you may be hitting a hard cap of your tvdatafeed build.")
                break

        time.sleep(BACKOFF_SEC)

    # tidy columns: rename 'close' to 'btcd' and keep OHLCV if you want
    out = collected.copy()
    out = out.loc[out.index >= START_DATE_UTC]
    out = out.sort_index()
    if "close" in out.columns:
        out["btcd"] = out["close"]

    columns = ["open", "high", "low", "close", "btcd", "volume"]
    if "symbol" in out.columns:
        columns.append("symbol")
    columns = [col for col in columns if col in out.columns]
    out = out[columns]

    return out

if __name__ == "__main__":
    df = fetch_btcd_30m_since_2020()
    out_csv = "btcd_30m_2020_to_now.csv"
    df.to_csv(out_csv, index_label="datetime_utc")
    print(f"Saved {len(df)} rows to {out_csv}. "
          f"range: {df.index.min()} -> {df.index.max()}")
