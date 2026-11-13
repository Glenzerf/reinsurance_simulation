"""Stable UTF-8 CSV schemas. Blank cells mean unavailable or inapplicable; floats use
Python's shortest round-trip representation. The immutable snapshot uses JSON types."""
import csv
import io
from contextlib import closing
from economics import ASSETS, cash
from ledger import connect, read, selected, teams, label
from market_config import canonical

META = "schema session freeze settlement".split()
CASH = "opening direct expenses bought sold fees_paid fees_earned funds".split()
COLUMNS = {
    "contracts": "id version structure buyer line seller broker kind q attachment limit share premium fee package requires created updated signatures bound".split(),
    "investments": [
        "role",
        "role_label",
        "name",
        "slot",
        *["exposure_" + x for x in "ABCD"],
        *CASH,
        *["weight_" + x for x in ASSETS],
        *["amount_" + x for x in ASSETS],
        "submitted",
    ],
    "configuration": "set path value_json unit snapshot_hash".split(),
    "realization": "record role line key value count severities standard scaled".split(),
    "settlement": [
        "role",
        *CASH,
        *"H assets gain gross promised paid promised_in recovered ratio policyholders_paid shortfall equity residual profit roe assessment".split(),
    ],
    "ticket_payments": "id buyer seller promised paid".split(),
    "contract_history": "seq time actor action ok detail".split(),
}


def unit(path):
    """Units for typed scalar snapshot leaves, including privately assessed conditions."""
    k = path[-1]
    if (
        k
        in (
            "capital",
            "equity_floor",
            "direct",
            "expenses",
            "scale",
            "minimum",
            "mean",
            "sd",
            "C_mean",
            "C_sd",
        )
        or "C_sd_cases" in path
    ):
        return "million"
    if k == "count":
        return "claims/year"
    if "minutes" in path:
        return "minutes"
    if k == "remaining_years":
        return "years"
    if (
        k
        in (
            "prob",
            "D_prob",
            "probability",
            "solvency",
            "target",
            "ordinary_cost",
            "shortfall_cost",
            "brokerage",
            "short_yield",
            "long_yield",
            "tolerance",
        )
        or "yields" in path
        or "probabilities" in path
    ):
        return "fraction"
    if k in ("etf_mean", "etf_sd"):
        return "gross payoff per dollar"
    if "exposures" in path or k in ("shape", "B_shape"):
        return "dimensionless"
    return "metadata"


def leaves(value, path=()):
    """JSON-pointer path plus JSON-valued leaves; preserve even empty objects and arrays."""
    if isinstance(value, (dict, list)) and value:
        pairs = value.items() if isinstance(value, dict) else enumerate(value)
        for k, v in pairs:
            yield from leaves(v, path + (str(k),))
    else:
        yield path, value


def rows(db, session, table):
    cfg, s, digest = read(db, session)
    active = teams(s)
    bound = [t for t in selected(s) if t["status"] == "bound"]
    if table == "contracts":
        yield from bound
    elif table == "investments":
        balances = cash(cfg, active, bound)
        for slot, r in s["assign"].items():
            w = s["weights"].get(r, [])
            name = s["names"].get(r, "")
            # Prefix untrusted text only. Numeric negative equities remain numeric.
            if name.lstrip().startswith(("=", "+", "-", "@")) or name.startswith(
                ("\t", "\r", "\n")
            ):
                name = "'" + name
            yield dict(
                role=r,
                role_label=label(r),
                slot=slot,
                name=name,
                **balances[r],
                **{
                    "exposure_" + k: v
                    for k, v in cfg["private"][r].get("exposures", {}).items()
                },
                **{"weight_" + k: v for k, v in zip(ASSETS, w)},
                **{"amount_" + k: v * balances[r]["funds"] for k, v in zip(ASSETS, w)},
                submitted=s["submitted"].get(r)
            )
    elif table == "configuration":
        for section, obj in [
            ("snapshot", cfg),
            (
                "attendance",
                dict(
                    opened=s["opened"],
                    active=s["assign"],
                    removed=s["removed"],
                    books=s["books"],
                ),
            ),
        ]:
            for path, v in leaves(obj):
                yield dict(
                    set=section if section == "attendance" else path[0],
                    path="/" + "/".join(path),
                    value_json=canonical(v),
                    unit=unit(path),
                    snapshot_hash=digest,
                )
    elif table == "realization" and "realization" in s:
        z = s["realization"]
        for k, v in {
            **z["market"],
            "flood_event": int(z["flood_event"]),
            "flood_severity": z["flood_severity"],
        }.items():
            yield dict(record="market", key=k, value=v)
        for r, lines in z["losses"].items():
            for line, values in lines.items():
                yield dict(record="line", role=r, line=line, **values)
    elif table == "settlement":
        for r, v in s.get("results", {}).items():
            yield dict(role=r, **v)
    elif table == "ticket_payments":
        for k, v in s.get("payments", {}).items():
            yield dict(id=k, **v)
    elif table == "contract_history":
        yield from (
            dict(row)
            for row in db.execute(
                "SELECT * FROM event WHERE session=? ORDER BY seq", (session,)
            )
        )


def dataset(session, table):
    """One consistent read transaction even when a concurrent request settles the game."""
    with closing(connect()) as db, db:
        db.execute("BEGIN")
        _, s, _ = read(db, session)
        yield META + COLUMNS[table]
        for row in rows(db, session, table):
            data = dict(
                row,
                schema=1,
                session=session,
                freeze=s["freeze"],
                settlement=s["settlement"],
            )
            yield [
                canonical(data[k])
                if isinstance(data.get(k), (list, dict))
                else data.get(k)
                for k in META + COLUMNS[table]
            ]


def csv_bytes(session, table):
    out = io.StringIO(newline="")
    csv.writer(out).writerows(dataset(session, table))
    return out.getvalue().encode("utf-8")
