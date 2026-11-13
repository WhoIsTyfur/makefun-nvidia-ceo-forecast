"""Fetch every universe market's 1-minute Yes price history from Polymarket and put it on the rules' grid.

Usage: python bench/fetch.py <case.in with the full universe> <out.json>
Writes {"markets": [{"id","name","start_ts","prices":[...]}], "end_ts": ...} where prices[i] is the grid price
at minute start_ts + 60*i (last point at or before that minute's first second, carried forward).
"""
import json
import sys
import time
import urllib.request

API = "https://clob.polymarket.com/prices-history?market={tok}&startTs={s}&endTs={e}&fidelity=1"
CHUNK = 24 * 3600


def fetch_points(token, start, end):
    pts = {}
    s = start
    while s < end:
        e = min(end, s + CHUNK)
        url = API.format(tok=token, s=s, e=e)
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "forecast-bench/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
                break
            except Exception as ex:  # retry transient errors
                print("retry", token[:10], s, ex, file=sys.stderr)
                time.sleep(2 + attempt * 2)
        else:
            raise RuntimeError("fetch failed")
        for p in data.get("history", []):
            pts[int(p["t"])] = float(p["p"])
        s = e
    return sorted(pts.items())


def to_grid(points, end):
    if not points:
        return None, []
    first = points[0][0]
    start = -(-first // 60) * 60  # first whole minute at or after the first point
    prices = []
    j = 0
    last = None
    m = start
    while m <= end:
        while j < len(points) and points[j][0] <= m:
            last = points[j][1]
            j += 1
        prices.append(last)
        m += 60
    return start, prices


def main():
    case = json.load(open(sys.argv[1], encoding="utf-8"))
    end = int(time.time()) // 60 * 60 - 120
    begin = 1762560000  # 2025-11-08, well before the event's first trade
    begin = int(time.mktime(time.strptime("2026-11-09", "%Y-%m-%d")))
    out = {"end_ts": end, "markets": []}
    for m in case["markets"]:
        pts = fetch_points(m["yes_token"], begin, end)
        start, prices = to_grid(pts, end)
        print(m["name"], len(pts), "points", start, file=sys.stderr)
        out["markets"].append({"id": m["id"], "name": m["name"], "start_ts": start, "prices": prices})
    json.dump(out, open(sys.argv[2], "w"))


if __name__ == "__main__":
    main()
