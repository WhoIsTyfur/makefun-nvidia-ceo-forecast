"""Forecast Polymarket "Next CEO of NVIDIA?" Yes prices, minute by minute, 4 hours ahead, as five quantiles.

For each case file in the input dir, for every market and every minute h = 1..240 after the checkpoint, write the
0.05/0.25/0.5/0.75/0.95 quantiles of that minute's price.

Model: the quantiles of a market's h-minute price change are read from its own lookback (empirical h-step changes),
blended with a pooled distribution of all markets' changes normalized by price level, then added to the last price.
"""
import json
import math
import os
import sys

TAUS = [0.05, 0.25, 0.5, 0.75, 0.95]
ANCHORS = [1, 2, 3, 5, 8, 12, 18, 25, 35, 50, 70, 95, 125, 160, 200, 240]
W_OWN = 0.5  # weight of a market's own empirical quantiles vs the pooled ones


def level_scale(x):
    x = min(max(x, 0.005), 0.995)
    return math.sqrt(x * (1.0 - x))


def quantile(sorted_vals, tau):
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    pos = tau * (n - 1)
    i = int(pos)
    f = pos - i
    if i + 1 < n:
        return sorted_vals[i] * (1 - f) + sorted_vals[i + 1] * f
    return sorted_vals[i]


def changes(prices, h):
    n = len(prices)
    if n <= h:
        return []
    return [prices[t + h] - prices[t] for t in range(n - h)]


def interp_anchor(table, h):
    """table: dict anchor -> list of 5 values; linear interpolation in log h."""
    if h in table:
        return table[h]
    lo = max(a for a in ANCHORS if a <= h)
    hi = min(a for a in ANCHORS if a >= h)
    w = (math.log(h) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return [table[lo][k] * (1 - w) + table[hi][k] * w for k in range(5)]


def forecast_case(case):
    horizon = case["horizon_minutes"]
    markets = case["markets"]
    # per-market and pooled normalized change quantiles at each anchor horizon
    own = []
    pooled_raw = {a: [] for a in ANCHORS}
    for m in markets:
        p = [float(v) for v in m["prices"]]
        sc = level_scale(sum(p[-240:]) / len(p[-240:]))
        tab = {}
        for a in ANCHORS:
            d = changes(p, a)
            d.sort()
            tab[a] = [quantile(d, t) for t in TAUS] if d else None
            pooled_raw[a].extend(v / sc for v in d)
        own.append((p, sc, tab, len(p)))
    pooled = {}
    for a in ANCHORS:
        v = pooled_raw[a]
        v.sort()
        pooled[a] = [quantile(v, t) for t in TAUS] if v else [0.0] * 5

    out = []
    for m, (p, sc, tab, n) in zip(markets, own):
        x = p[-1]
        # fill anchors without own data using pooled
        w_own = W_OWN * min(1.0, n / 1440.0)
        mixed = {}
        for a in ANCHORS:
            pq = [v * sc for v in pooled[a]]
            oq = tab[a]
            if oq is None:
                mixed[a] = pq
            else:
                mixed[a] = [w_own * oq[k] + (1 - w_own) * pq[k] for k in range(5)]
        rows = []
        for h in range(1, horizon + 1):
            dq = interp_anchor(mixed, min(h, ANCHORS[-1]))
            row = []
            prev = 0.0
            for k in range(5):
                q = x + dq[k]
                q = min(1.0, max(0.0, q))
                if k and q < prev:
                    q = prev
                q = round(q, 6)
                row.append(q)
                prev = q
            rows.append(row)
        out.append({"id": m["id"], "q": rows})
    return {"forecasts": out}


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    names = sorted(f for f in os.listdir(in_dir) if f.endswith(".in"))
    for name in names:
        with open(os.path.join(in_dir, name), encoding="utf-8") as fh:
            case = json.load(fh)
        res = forecast_case(case)
        with open(os.path.join(out_dir, name[:-3] + ".out"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, separators=(",", ":"))


if __name__ == "__main__":
    main()
