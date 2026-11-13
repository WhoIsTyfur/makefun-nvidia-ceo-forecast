"""Local benchmark: cut cases from the fetched history and score forecasters by mean pinball loss.

python bench/bench.py out/history.json verify          # check grid vs practice inputs and baseline loss
python bench/bench.py out/history.json run name[,name]  # score candidates from bench/cands.py
"""
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TAUS = [0.05, 0.25, 0.5, 0.75, 0.95]
LOOKBACK = 4320
H = 240


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_iso(s):
    return int(datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


def load_history(path):
    return json.load(open(path))


def make_case(hist, at, cid="b"):
    """Case at checkpoint `at` (unix s) plus answers {id: [240 prices]} or None if not fully answered."""
    markets, answers = [], {}
    for m in hist["markets"]:
        st = m["start_ts"]
        if st is None or st > at:
            continue
        i_at = (at - st) // 60
        if i_at + H >= len(m["prices"]):
            return None, None
        i0 = max(0, i_at - LOOKBACK)
        markets.append({"id": m["id"], "name": m["name"], "start": iso(st + 60 * i0),
                        "prices": m["prices"][i0:i_at + 1]})
        answers[m["id"]] = m["prices"][i_at + 1:i_at + 1 + H]
    case = {"at": iso(at), "case": cid, "horizon_minutes": H, "markets": markets, "quantiles": TAUS}
    return case, answers


def pinball_case(fc, answers):
    tot = 0.0
    n = 0
    per_market = {}
    for row in fc["forecasts"]:
        ys = answers[row["id"]]
        s = 0.0
        for q5, y in zip(row["q"], ys):
            for tau, q in zip(TAUS, q5):
                d = y - q
                s += 100 * (tau * d if d >= 0 else (tau - 1) * d)
        per_market[row["id"]] = s / (5 * len(ys))
        tot += s
        n += 5 * len(ys)
    assert len(fc["forecasts"]) == len(answers)
    return tot / n, per_market


def baseline(case):
    z = [-1.644854, -0.674490, 0.0, 0.674490, 1.644854]
    out = []
    for m in case["markets"]:
        x = m["prices"][-1]
        rows = [[round(min(1, max(0, x + zz * 0.0025 * math.sqrt(h))), 6) for zz in z] for h in range(1, H + 1)]
        out.append({"id": m["id"], "q": rows})
    return {"forecasts": out}


def load_cands():
    spec = importlib.util.spec_from_file_location("cands", os.path.join(HERE, "cands.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verify(hist):
    kit = os.path.join(HERE, "..", "kit", "input")
    losses = []
    for name in sorted(os.listdir(kit)):
        if not name.endswith(".in"):
            continue
        real = json.load(open(os.path.join(kit, name), encoding="utf-8"))
        at = parse_iso(real["at"])
        case, ans = make_case(hist, at)
        mine = {m["id"]: m for m in case["markets"]}
        bad = 0
        for m in real["markets"]:
            pm = mine.get(m["id"])
            if pm is None or pm["start"] != m["start"] or len(pm["prices"]) != len(m["prices"]):
                bad += 1
                continue
            bad += sum(1 for a, b in zip(pm["prices"], m["prices"]) if abs(a - b) > 1e-12) > 0
        l, _ = pinball_case(baseline(real), {k: ans[k] for k in (m["id"] for m in real["markets"])})
        losses.append(l)
        print(name, "markets", len(real["markets"]), "mine", len(case["markets"]), "mismatched", bad, "baseline", round(l, 6))
    print("baseline practice mean", round(sum(losses) / len(losses), 6), "(target 0.363589)")


def bench_cases(hist, step_min=60, min_markets=10):
    starts = [m["start_ts"] for m in hist["markets"] if m["start_ts"]]
    first = min(starts) + 6 * 3600  # need some lookback
    first = (first // 3600 + 1) * 3600
    cases = []
    at = first
    while True:
        case, ans = make_case(hist, at, iso(at))
        if case is None:
            break
        if len(case["markets"]) >= min_markets:
            cases.append((case, ans))
        at += step_min * 60
    return cases


def movement(case, ans):
    """Mean absolute 240-minute path movement across markets (calm-ness of the answer window)."""
    tot = 0.0
    for m in case["markets"]:
        x = m["prices"][-1]
        tot += sum(abs(y - x) for y in ans[m["id"]]) / H
    return tot / len(case["markets"])


def run(hist, names, step):
    cands = load_cands()
    cases = bench_cases(hist, step)
    mv = [movement(c, a) for c, a in cases]
    order = sorted(range(len(cases)), key=lambda i: mv[i])
    calm = set(order[: len(cases) // 2])
    # weekend-like: Sat/Sun UTC or night hours. Our history has few weekend hours, so use calm half instead.
    print("cases", len(cases), "from", cases[0][0]["at"], "to", cases[-1][0]["at"])
    results = {}
    for name in names:
        fn = baseline if name == "baseline" else getattr(cands, name)
        t0 = time.time()
        ls = []
        for c, a in cases:
            ls.append(pinball_case(fn(c), a)[0])
        dt = time.time() - t0
        wts = [len(c["markets"]) for c, a in cases]
        wmean = sum(l * w for l, w in zip(ls, wts)) / sum(wts)
        srt = sorted(ls)
        k = max(1, len(ls) // 10)
        worst = sum(srt[-k:]) / k
        calm_l = sum(ls[i] for i in calm) / len(calm)
        busy_l = sum(ls[i] for i in range(len(ls)) if i not in calm) / (len(ls) - len(calm))
        last24 = ls[-24:]
        results[name] = ls
        print(f"{name:28s} mean {wmean:.5f}  worst10% {worst:.5f}  calm {calm_l:.5f}  busy {busy_l:.5f}  "
              f"last24 {sum(last24)/len(last24):.5f}  ({dt/len(cases)*1000:.0f} ms/case)")
    return results


if __name__ == "__main__":
    hist = load_history(sys.argv[1])
    if sys.argv[2] == "verify":
        verify(hist)
    else:
        step = int(sys.argv[4]) if len(sys.argv) > 4 else 60
        run(hist, sys.argv[3].split(","), step)
