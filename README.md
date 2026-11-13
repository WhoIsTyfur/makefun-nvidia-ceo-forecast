# NVIDIA next-CEO price forecaster

Entry for the make.fun bounty [polymarket-nvidia-ceo-forecast-01](https://make.fun/bounty/polymarket-nvidia-ceo-forecast-01).

## What it does

`main.py` (Python 3.13, standard library only) reads each case file `<id>.in` from `$MAKEFUN_INPUT_DIR`
(default `/input`): the 1-minute Yes prices of the 24 markets of Polymarket's "Next CEO of NVIDIA?" event for the
72 hours up to a checkpoint. For every market and every minute h = 1..240 after the checkpoint it writes five
quantiles (5%, 25%, 50%, 75%, 95%) of that minute's price to `$MAKEFUN_OUTPUT_DIR/<id>.out` (default `/output`):

```
{"forecasts":[{"id":"0x...","q":[[0.163534,0.1665,0.1665,0.1665,0.16825], ... 240 rows]}, ...]}
```

The quantiles are the last price plus quantiles of the h-minute price change, learned from the lookback: each
market's own empirical changes blended with a pooled distribution across markets (normalized by price level).
Polymarket prices sit still for minutes and then tick or jump, so the inner quantiles usually stay at the current
price while the outer ones widen with how often each market really moves.

## How it is scored

Mean pinball loss (in percentage points) over every case, market, minute and quantile, lowest first. The final is
twelve 4-hour cases from 2026-11-13T21:00Z to 2026-11-15T21:00Z.

## Run it locally

```
mkdir out
MAKEFUN_INPUT_DIR=kit/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`bench/` holds the local benchmark: `fetch.py` downloads every market's 1-minute history from Polymarket's public
`prices-history` endpoint onto the rules' grid, and `bench.py` cuts hourly cases (72 h lookback, 240-minute answers)
from it and scores candidate forecasters (`cands.py`) by the same pinball loss:

```
python bench/fetch.py kit/input/p05.in out/history.json
python bench/bench.py out/history.json verify
python bench/bench.py out/history.json run baseline,entry
```
