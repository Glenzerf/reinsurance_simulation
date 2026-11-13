"""Rebuild the classroom settlement using only exported decisions and observed draws.

Run 'python reconstruct.py path/to/csvs'. Uses only the standard library, independently
recomputes cash balances, asset payoffs, promises, rationing and accounting, and checks
exported settlement and ticket payments if present. No database or random generator.
"""
import csv
import json
import math
import sys
from pathlib import Path


def reconstruct(folder):
    """Return independently calculated team and ticket figures; reject mixed downloads."""
    common = None

    def load(name):
        nonlocal common
        with (Path(folder) / (name + ".csv")).open(
            encoding="utf-8-sig", newline=""
        ) as f:
            records = list(csv.DictReader(f))
        for r in records:
            ids = tuple(r[x] for x in ("schema", "session", "freeze"))
            if common is None:
                common = ids
            if ids != common or not ids[2]:
                raise ValueError("Mixed session or decision freeze")
        return records

    params = {
        r["path"]: json.loads(r["value_json"])
        for r in load("configuration")
        if r["set"] != "attendance"
    }
    teams = load("investments")
    tickets = load("contracts")
    observed = load("realization")
    if not observed:
        raise ValueError("Settlement draw is still pending")
    shocks = {r["key"]: float(r["value"]) for r in observed if r["record"] == "market"}
    years = params["/public/assets/remaining_years"]
    returns = [
        1 + params["/public/assets/short_yield"],
        (1 + params["/public/assets/long_yield"]) ** (years + 1)
        / (1 + shocks["yield_end"]) ** years,
        shocks["etf"],
    ]
    exposure = {r["role"]: r for r in teams}
    losses = {
        (r["role"], r["line"]): float(r["standard"])
        * float(exposure[r["role"]]["exposure_" + r["line"]])
        for r in observed
        if r["record"] == "line"
    }
    rows = {}
    for t in teams:
        r = t["role"]
        opening = params["/private/" + r + "/capital"]
        direct = params["/public/direct"] if r[0] == "I" else 0.0
        expenses = params["/public/expenses"] if r[0] == "I" else 0.0
        bought = sum(float(k["premium"]) for k in tickets if k["buyer"] == r)
        sold = sum(float(k["premium"]) for k in tickets if k["seller"] == r)
        fees_paid = bought * params["/public/brokerage"]
        fees_earned = (
            sum(float(k["premium"]) for k in tickets if k["broker"] == r)
            * params["/public/brokerage"]
        )
        funds = opening + direct - expenses - bought + sold - fees_paid + fees_earned
        h = sum(
            float(t["weight_" + a]) * v
            for a, v in zip(("short", "long", "etf"), returns)
        )
        rows[r] = dict(
            opening=opening,
            direct=direct,
            expenses=expenses,
            bought=bought,
            sold=sold,
            fees_paid=fees_paid,
            fees_earned=fees_earned,
            funds=funds,
            H=h,
            assets=funds * h,
            gain=funds * (h - 1),
            gross=sum(v for (buyer, _), v in losses.items() if buyer == r),
            promised=0.0,
            paid=0.0,
            promised_in=0.0,
            recovered=0.0,
        )
    payments = {}
    for t in tickets:
        loss = losses[t["buyer"], t["line"]]
        base = (
            float(t["q"]) * loss
            if t["kind"] == "QS"
            else min(float(t["limit"]), max(0.0, loss - float(t["attachment"])))
        )
        amount = float(t["share"]) * base
        payments[t["id"]] = dict(promised=amount)
        rows[t["seller"]]["promised"] += amount
        rows[t["buyer"]]["promised_in"] += amount
    for r, v in rows.items():
        v["ratio"] = (
            (min(1.0, v["assets"] / v["promised"]) if v["promised"] else 1.0)
            if r[0] == "R"
            else None
        )
    for t in tickets:
        p = payments[t["id"]]
        p["paid"] = p["promised"] * rows[t["seller"]]["ratio"]
        rows[t["seller"]]["paid"] += p["paid"]
        rows[t["buyer"]]["recovered"] += p["paid"]
    for r, v in rows.items():
        equity = v["assets"] + v["recovered"] - v["promised"] - v["gross"]
        profit = equity - v["opening"]
        v.update(
            equity=equity,
            profit=profit,
            roe=profit / v["opening"] if v["opening"] else None,
            shortfall=max(0.0, -equity),
            residual=max(0.0, equity),
            policyholders_paid=min(v["gross"], v["assets"] + v["recovered"]),
        )
    for name, key, calc in [
        ("settlement", "role", rows),
        ("ticket_payments", "id", payments),
    ]:
        if (Path(folder) / (name + ".csv")).exists():
            reference = load(name)
            if set(calc) != {r[key] for r in reference}:
                raise ValueError("Missing rows in " + name)
            for rec in reference:
                for k, v in calc[rec[key]].items():
                    if v is None and not rec[k]:
                        continue
                    if not math.isclose(float(rec[k]), v, rel_tol=1e-11, abs_tol=1e-10):
                        raise ValueError(f"Mismatch: {name}, {rec[key]}, {k}")
    return dict(teams=rows, tickets=payments)


if __name__ == "__main__":
    print(json.dumps(reconstruct(sys.argv[1]), indent=2))
