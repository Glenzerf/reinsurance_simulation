"""Annual cash accounting. No function simulates solvency or applies capital charges."""
import math
import numpy as np

ASSETS = ("short", "long", "etf")


def log_parameters(mean, sd):
    """Convert arithmetic moments to normal parameters for log(X)."""
    variance = math.log1p((sd / mean) ** 2)
    return math.log(mean) - variance / 2, math.sqrt(variance)


def draw(cfg, teams):
    """Local PCG64, stable insurer order. Store frequencies, severities, event outcomes
    and market prices as well as aggregates so replay requires no random library."""
    rng = np.random.Generator(np.random.PCG64(cfg["seed"]))
    a = cfg["public"]["assets"]
    law = cfg["realization"]
    y = float(rng.choice(a["yields"], p=a["probabilities"]))
    years = a["remaining_years"]
    shocks = dict(
        yield_end=y,
        short=1 + a["short_yield"],
        long=(1 + a["long_yield"]) ** (years + 1) / (1 + y) ** years,
        etf=rng.lognormal(*log_parameters(a["etf_mean"], a["etf_sd"])),
    )
    flood = rng.random() < law["D"]["prob"]
    shared = rng.gamma(law["D"]["shape"], law["D"]["scale"]) if flood else 0.0
    losses = {}
    for r in sorted(teams):
        if r[0] != "I":
            continue
        n = int(rng.poisson(law["A"]["count"]))
        fires = rng.gamma(law["A"]["shape"], law["A"]["scale"], n).tolist()
        wildfire = rng.random() < law["B"]["prob"]
        severity = (
            law["B"]["minimum"] * (1 + rng.pareto(law["B"]["shape"]))
            if wildfire
            else 0.0
        )
        n = int(rng.poisson(law["C"]["count"]))
        claims = rng.lognormal(
            *log_parameters(law["C"]["mean"], law["C"]["sd"]), n
        ).tolist()
        losses[r] = {}
        for line, samples in zip(
            "ABCD",
            (fires, [severity] if wildfire else [], claims, [shared] if flood else []),
        ):
            standard = math.fsum(samples)
            losses[r][line] = dict(
                count=len(samples),
                severities=samples,
                standard=standard,
                scaled=standard * cfg["private"][r]["exposures"][line],
            )
    return dict(
        market=shocks, flood_event=bool(flood), flood_severity=shared, losses=losses
    )


def cash(cfg, teams, tickets):
    """Compute cash before investing; bought/sold are positive premium magnitudes."""
    rows = {}
    for r in teams:
        insurer = r.startswith("I")
        rows[r] = dict(
            opening=cfg["private"][r]["capital"],
            direct=cfg["public"]["direct"] if insurer else 0,
            expenses=cfg["public"]["expenses"] if insurer else 0,
            bought=0.0,
            sold=0.0,
            fees_paid=0.0,
            fees_earned=0.0,
        )
    for t in tickets:
        rows[t["buyer"]]["bought"] += t["premium"]
        rows[t["buyer"]]["fees_paid"] += t["fee"]
        rows[t["seller"]]["sold"] += t["premium"]
        rows[t["broker"]]["fees_earned"] += t["fee"]
    for v in rows.values():
        v["funds"] = (
            v["opening"]
            + v["direct"]
            - v["expenses"]
            - v["bought"]
            + v["sold"]
            - v["fees_paid"]
            + v["fees_earned"]
        )
    return rows


def recovery(t, loss):
    """Limit the annual aggregate structure before allocating the seller's share."""
    full = (
        t["q"] * loss
        if t["kind"] == "QS"
        else min(max(loss - t["attachment"], 0), t["limit"])
    )
    return t["share"] * full


def settle(cfg, teams, tickets, weights, realization):
    """Use original capital throughout. Seller waterfall pays all creditors pari passu."""
    rows = cash(cfg, teams, tickets)
    payments = {}
    for r, v in rows.items():
        h = sum(w * realization["market"][a] for w, a in zip(weights[r], ASSETS))
        v.update(
            H=h,
            assets=v["funds"] * h,
            gain=v["funds"] * (h - 1),
            promised=0.0,
            paid=0.0,
            promised_in=0.0,
            recovered=0.0,
            gross=sum(x["scaled"] for x in realization["losses"].get(r, {}).values()),
        )
    for t in tickets:
        amount = recovery(t, realization["losses"][t["buyer"]][t["line"]]["scaled"])
        payments[t["id"]] = dict(buyer=t["buyer"], seller=t["seller"], promised=amount)
        rows[t["seller"]]["promised"] += amount
        rows[t["buyer"]]["promised_in"] += amount
    for r, v in rows.items():
        v["ratio"] = (
            (min(1.0, v["assets"] / v["promised"]) if v["promised"] else 1.0)
            if r[0] == "R"
            else None
        )
    for p in payments.values():
        p["paid"] = p["promised"] * rows[p["seller"]]["ratio"]
        rows[p["seller"]]["paid"] += p["paid"]
        rows[p["buyer"]]["recovered"] += p["paid"]
    for r, v in rows.items():
        equity = v["assets"] + v["recovered"] - v["gross"] - v["promised"]
        profit = equity - v["opening"]
        v.update(
            equity=equity,
            profit=profit,
            roe=profit / v["opening"] if v["opening"] else None,
            residual=max(0.0, equity),
            shortfall=max(0.0, -equity),
            policyholders_paid=min(v["gross"], v["assets"] + v["recovered"]),
            assessment="exempt" if r[0] == "B" else "pending",
        )
    return rows, payments
