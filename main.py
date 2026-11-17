"""GTA VI Twitch CCU launch-day forecast — make.fun entry (gta6-twitch-ccu-forecast-01).

Model: US/EU-unlock-aligned comparable launch ratio curves, size-weighted
(Gaussian weights on |ln(comp_anchor / target_hour1)|), log-normal quantiles.
Core ported from the validated salvage model_v1 (size weight S=0.75);
DST handling corrected to exact last-Sunday rules; robustness fallbacks added.
Optional small blend of the target game's own pre-launch category hourly
pattern (target-history comparables entry), disabled unless it scores better.

Python 3.13, standard library only. Deterministic: no randomness, no time
dependence, fixed iteration order throughout.
"""
import json, math, os, statistics
from datetime import datetime, timedelta

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z = {0.05: -1.6448536269514722, 0.25: -0.6744897501960817, 0.5: 0.0,
     0.75: 0.6744897501960817, 0.95: 1.6448536269514722}
ZL = (-1.6448536269514722, -0.6744897501960817, 0.0,
      0.6744897501960817, 1.6448536269514722)

DEFAULT_CFG = {
    "S": 0.55,             # size-weight scale (log units)
    "min_jump": 0.08,      # min log-jump for the US-unlock filter
    "sigma_floor": 0.10,   # floor on per-hour log spread
    "smooth": True,        # 1-2-1 smoothing of mu/sigma curves
    "dst_fix": True,       # exact last-Sunday DST rules for EU offset
    "blend_w": 0.3,        # weight of target pre-launch pattern blend (0 = off)
    "blend_stat": "mean",  # "mean" or "median" hourly aggregator
    "blend_days": 30,      # history window (days before day_start) for pattern
}

Q_MIN, Q_MAX = 0.5, 1e9


def hparse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _last_sunday(y, m):
    d = datetime(y, m, 31)
    while d.weekday() != 6:  # Sunday
        d -= timedelta(days=1)
    return d.day


def eu_unlock_offset(dt, dst_fix=True):
    """Hours before day_start when EU/CET midnight local happened (winter -1, summer -2)."""
    y, m = dt.year, dt.month
    if not dst_fix:
        # salvage heuristic (kept for A/B only)
        if m in (11, 12, 1, 2):
            return -1
        if m in (4, 5, 6, 7, 8, 9, 10):
            return -2
        if m == 3:
            return -1 if dt.day < _last_sunday(y, 3) else -2
        return -2
    if m in (11, 12, 1, 2):
        return -1
    if m in (4, 5, 6, 7, 8, 9):
        return -2
    if m == 3:
        return -1 if dt.day < _last_sunday(y, 3) else -2
    # October: summer time until last Sunday
    return -2 if dt.day < _last_sunday(y, 10) else -1


def comp_hours(comp):
    """Map of UTC hour -> viewers for [day_start-2h, day_start+24h)."""
    day0 = hparse(comp["day_start"])
    out = {}
    for row in comp["hourly"]:
        t = hparse(row["from"])
        if day0 - timedelta(hours=2) <= t < day0 + timedelta(hours=24):
            out[t] = row["viewers"]
    return out


def tier_of(comp):
    u = comp.get("unlock", "") or ""
    for t in ("early-access-contaminated", "target-history", "weak", "comparable"):
        if f"Tier: {t}" in u:
            return t
    return "?"


def analyze_comp(comp, cfg):
    """Return dict with aligned ratio curve r[g] g=2..24 (GTA-clock), anchor, jump info."""
    day0 = hparse(comp["day_start"])
    hv = comp_hours(comp)
    # release-day hours 1..24 at day_start + (h-1)h
    v = {}
    for h in range(1, 25):
        v[h] = hv.get(day0 + timedelta(hours=h - 1))
    pre1 = hv.get(day0 - timedelta(hours=1))   # 23:00Z prev day
    pre2 = hv.get(day0 - timedelta(hours=2))   # 22:00Z prev day
    present = [v[h] for h in range(1, 25) if v[h]]
    if len(present) < 20 or not v[1] or v[1] <= 0:
        return None
    # observed jump hour: argmax log-increase h-1 -> h for h in 4..9
    jump_h, jump_mag = None, 0.0
    for h in range(4, 10):
        a, b = v[h - 1], v[h]
        if a and b and a > 0 and b > 0:
            m = math.log(b / a)
            if m > jump_mag:
                jump_mag, jump_h = m, h
    return {"name": comp["name"], "v": v, "pre1": pre1, "pre2": pre2,
            "jump_h": jump_h, "jump_mag": jump_mag, "tier": tier_of(comp),
            "day0": day0, "eu_off": eu_unlock_offset(day0, cfg.get("dst_fix", True))}


def build_ratios(info):
    """Aligned ratio curve on the GTA clock (hours since EU unlock).

    GTA hour g covers t in [g, g+1) where t = hours since EU unlock.
    eu_off = -1 (CET/EST): comp hour c covers t in [c, c+1) -> comp hour g aligns.
    eu_off = -2 (CEST/EDT): comp hour c covers t in [c+1, c+2) -> comp hour g-1
    aligns; anchor (t in [1,2)) = pre1 (23:00Z prev day).
    """
    eu_off = info["eu_off"]  # -1 or -2
    v, pre1 = info["v"], info["pre1"]
    if eu_off == -1:
        if not v[1] or v[1] <= 0:
            return None
        anchor = v[1]
        shift = 0
    else:
        if pre1 is None or pre1 <= 0:
            return None
        anchor = pre1
        shift = -1  # comp hour index = g + shift
    r = {}
    for g in range(2, 25):
        c = g + shift
        val = v.get(c) if 1 <= c <= 24 else None
        if val and val > 0 and anchor and anchor > 0:
            r[g] = val / anchor
    if len(r) < 18:
        return None
    return {"r": r, "anchor": anchor, **info}


def select_comp(info, cfg):
    if info is None:
        return None
    if info["tier"] in ("weak", "target-history", "early-access-contaminated"):
        return None
    jh, jm = info["jump_h"], info["jump_mag"]
    if jh not in (5, 6) or jm < cfg.get("min_jump", 0.08):
        return None
    return info


def smooth_curve(d):
    """1-2-1 kernel over hours 2..24, missing-aware."""
    out = {}
    for g in d:
        num, den = 0.0, 0.0
        for gg, wgt in ((g - 1, 1.0), (g, 2.0), (g + 1, 1.0)):
            if gg in d and d[gg] is not None:
                num += wgt * d[gg]
                den += wgt
        out[g] = num / den if den else d[g]
    return out


def target_hour1(case):
    """Hour-1 viewers of the target, with fallbacks."""
    for k in case.get("known", []):
        v = k.get("viewers")
        if v and v > 0:
            return float(v)
    day0 = hparse(case["day_start"])
    best = None
    for row in case.get("history_hourly", []):
        v = row.get("viewers")
        if not v or v <= 0:
            continue
        t = hparse(row["from"])
        if day0 - timedelta(hours=48) <= t < day0:
            best = max(best or 0.0, float(v))
    return float(best) if best else 1.0


def target_pattern(case, cfg):
    """Centered log hour-of-day pattern from the target-history comparables entry.

    Returns {g: m_g} for g in 2..24 with weighted mean 0 over g, or None.
    """
    w = float(cfg.get("blend_w", 0.0) or 0.0)
    if w <= 0.0:
        return None
    stat = cfg.get("blend_stat", "mean")
    days = int(cfg.get("blend_days", 30))
    best = None
    for comp in case.get("comparables", []):
        if "target-history" not in (comp.get("unlock") or ""):
            continue
        if best is None or len(comp.get("hourly", [])) > len(best.get("hourly", [])):
            best = comp
    if best is None:
        return None
    day0 = hparse(case["day_start"])
    cutoff = day0 - timedelta(days=days)
    by_hour = {}
    for row in best.get("hourly", []):
        v = row.get("viewers")
        if not v or v <= 0:
            continue
        t = hparse(row["from"])
        if t < cutoff or t >= day0:
            continue
        by_hour.setdefault(t.hour, []).append(math.log(float(v)))
    if len(by_hour) < 12:
        return None
    pat = {}
    for h, xs in by_hour.items():
        pat[h] = statistics.median(xs) if stat == "median" else sum(xs) / len(xs)
    m = {}
    for g in range(2, 25):
        uh = (day0.hour + g - 1) % 24
        if uh not in pat:
            return None
        m[g] = pat[uh]
    bar = sum(m.values()) / len(m)
    return {g: w * (m[g] - bar) for g in m}


def baseline(case):
    p1 = target_hour1(case)
    return {h: [p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in ZL]
            for h in range(2, 25)}


def forecast_case(case, cfg=None):
    cfg = dict(DEFAULT_CFG if cfg is None else cfg)
    try:
        return _forecast_case(case, cfg)
    except Exception:
        return baseline(case)


def _forecast_case(case, cfg):
    p1 = target_hour1(case)
    rats = []
    for comp in case.get("comparables", []):
        info = analyze_comp(comp, cfg)
        if not select_comp(info, cfg):
            continue
        rr = build_ratios(info)
        if rr:
            rats.append(rr)
    if not rats:
        return baseline(case)
    # size weights
    ws = []
    for rr in rats:
        lw = math.log(max(rr["anchor"], 1.0) / p1)
        S = cfg.get("S", 0.75)
        w = math.exp(-0.5 * (lw / S) ** 2) if S else 1.0
        ws.append(w)
    # per-hour weighted log mean/std
    mu, sg = {}, {}
    for g in range(2, 25):
        xs = [math.log(rr["r"][g]) for rr in rats if g in rr["r"]]
        ws_ = [w for rr, w in zip(rats, ws) if g in rr["r"]]
        if not xs:
            mu[g], sg[g] = None, None
            continue
        tw = sum(ws_)
        m = sum(w * x for w, x in zip(ws_, xs)) / tw
        var = sum(w * (x - m) ** 2 for w, x in zip(ws_, xs)) / tw
        mu[g], sg[g] = m, math.sqrt(var)
    if cfg.get("smooth", True):
        mu = smooth_curve(mu)
        sg = smooth_curve(sg)
    pat = target_pattern(case, cfg)
    out = {}
    for g in range(2, 25):
        if mu[g] is None:
            out[g] = [p1] * 5
            continue
        s = max(sg[g], cfg.get("sigma_floor", 0.10))
        mg = mu[g] + (pat[g] if pat else 0.0)
        out[g] = [p1 * math.exp(mg + Z[t] * s) for t in LEVELS]
    return out


def finalize(rows):
    """Clamp to (0, 1e9], enforce non-decreasing, round-free floats."""
    out = {}
    for h in range(2, 25):
        qs = rows.get(h)
        if not qs:
            qs = [1.0] * 5
        qs = [min(max(float(q), Q_MIN), Q_MAX) for q in qs]
        out[h] = sorted(qs)
    return out


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    names = sorted(n for n in os.listdir(in_dir)
                   if n.endswith(".in") and os.path.isfile(os.path.join(in_dir, n)))
    for name in names:
        cid = name[:-3]
        try:
            with open(os.path.join(in_dir, name), "r", encoding="utf-8") as f:
                case = json.load(f)
            rows = finalize(forecast_case(case))
        except Exception:
            # unreadable/degenerate case: emit a neutral valid forecast rather
            # than no file (log-space middle guess under total ignorance)
            rows = {h: [3e4] * 5 for h in range(2, 25)}
        payload = {"hours": [{"hour": h, "q": rows[h]} for h in range(2, 25)]}
        with open(os.path.join(out_dir, cid + ".out"), "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
    return len(names)


if __name__ == "__main__":
    main()
