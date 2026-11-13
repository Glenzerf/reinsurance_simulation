"""Authoritative market ledger, shared by oTree and the loopback instructor console.

SQLite BEGIN IMMEDIATE serializes every command, including across processes. A snapshot,
market state and append-only action log commit together. oTree owns participant login,
session membership and page delivery; it never caches a second writable decision book.
Use a persistent local disk for this single-host deployment.
"""
import json
import math
import os
import sqlite3
import uuid
import re
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from market_config import canonical, snapshot
from economics import cash, draw, settle


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    """A fresh connection per transaction avoids shared thread-local state."""
    path = os.environ.get(
        "MARKET_DB", str(Path(__file__).resolve().with_name("market.sqlite3"))
    )
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
    CREATE TABLE IF NOT EXISTS market(session TEXT PRIMARY KEY,cfg TEXT NOT NULL,hash TEXT NOT NULL,state TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS event(seq INTEGER PRIMARY KEY,session TEXT,time TEXT,actor TEXT,action TEXT,ok INTEGER,detail TEXT);
    CREATE INDEX IF NOT EXISTS by_session ON event(session,seq);
    """
    )
    return db


def create(session, slots, preset):
    """Slots are oTree participant id_in_session values, never assumed to indicate a role."""
    cfg, digest = snapshot(preset)
    state = dict(
        phase="setup",
        since=now(),
        rev=0,
        market_revision=0,
        slot_revisions={},
        book=0,
        slots=sorted(slots, key=int),
        assign={},
        opened={},
        removed={},
        removal_reviews={},
        names={},
        tickets={},
        books={},
        weights={},
        submitted={},
        freeze="",
        settlement="",
    )
    with closing(connect()) as db, db:
        db.execute(
            "INSERT INTO market VALUES(?,?,?,?)",
            (session, canonical(cfg), digest, canonical(state)),
        )


def read(db, session):
    row = db.execute("SELECT * FROM market WHERE session=?", (session,)).fetchone()
    require(row, "Unknown session")
    return json.loads(row["cfg"]), json.loads(row["state"]), row["hash"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def teams(s):
    return sorted(s["assign"].values())


def selected(s):
    """A candidate needs three signatures on its current version. A bound book is immutable."""
    return [t for t in s["tickets"].values() if t["status"] in ("signed", "bound")]


def dirty(s):
    """All firms sign the same ledger number, including firms with no contracts."""
    s["book"] += 1
    s["books"] = {}


def problems(cfg, s):
    """Check the candidate ledger as a set, including directed package dependencies."""
    errors = []
    lines = {}
    chosen = selected(s)
    ids = {t["id"] for t in chosen}
    for t in chosen:
        key = (t["buyer"], t["line"])
        lines.setdefault(key, []).append(t)
        for dep in t["requires"]:
            if dep not in ids:
                errors.append(f"{t['id']} requires signed {dep}")
        if t["package"] and any(
            other["id"] not in ids
            for other in s["tickets"].values()
            if other["package"] == t["package"]
        ):
            errors.append(f"Incomplete package {t['package']}")
    for key, rows in lines.items():
        terms = {(t["kind"], t["q"], t["limit"], t["attachment"]) for t in rows}
        if len(terms) > 1:
            errors.append("Conflicting structures for " + " ".join(key))
        if sum(Decimal(str(t["share"])) for t in rows) > 1:
            errors.append("Over-placement for " + " ".join(key))
    errors.extend(
        f"{r} cannot fund its book"
        for r, v in cash(cfg, teams(s), chosen).items()
        if v["funds"] < 0
    )
    return errors


def number(p, k):
    """Reject missing/nonfinite values and booleans before any arithmetic or persistence."""
    x = p.get(k)
    require(isinstance(x, (str, int, float)) and not isinstance(x, bool), f"Enter {k}")
    try:
        v = float(x)
    except (ValueError, OverflowError):
        raise ValueError(f"Invalid {k}") from None
    require(math.isfinite(v) and v >= 0, f"{k} must be finite and nonnegative")
    return v


def identifier(raw):
    """Short human-readable package and ticket references are safe join/display keys."""
    require(
        isinstance(raw, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", raw),
        "Invalid identifier",
    )
    return raw


def clear_linked_signatures(s, changed, previous=None):
    """A package may span brokers. If membership or terms change, each affected buyer
    and seller reviews its own ticket again. Preserve original broker timestamps and
    record all changed tickets in the same audit event. Follow transitive dependencies.
    """
    affected = {changed["id"]}
    packages = {
        p for p in (changed.get("package"), (previous or {}).get("package")) if p
    }
    while True:
        size = len(affected)
        for t in s["tickets"].values():
            if (
                t["id"] in affected
                or t["package"] in packages
                or affected.intersection(t["requires"])
            ):
                affected.add(t["id"])
                if t["package"]:
                    packages.add(t["package"])
        if len(affected) == size:
            break
    for k in affected - {changed["id"]}:
        t = s["tickets"][k]
        if t["status"] in ("signed", "pending"):
            t.update(
                status="pending",
                signatures={t["broker"]: t["signatures"][t["broker"]]},
                updated=now(),
            )


def ticket_action(cfg, s, r, p, op):
    """Broker identity comes from the login. Every change uses exact-version comparison."""
    require(s["phase"] == "trade", "Trading is closed")
    t = s["tickets"].get(p.get("id", ""))
    if op != "propose":
        require(
            t and t["status"] in ("pending", "signed", "rejected"),
            "Ticket no longer editable",
        )
        require(p.get("version") == t["version"], "Stale ticket version; refresh")
    if op in ("propose", "amend"):
        require(
            r.startswith("B") and (op == "propose" or t["broker"] == r),
            "Only the arranging broker may enter terms",
        )
        buyer, seller = p.get("buyer"), p.get("seller")
        require(
            buyer in teams(s)
            and buyer.startswith("I")
            and seller in teams(s)
            and seller.startswith("R"),
            "Inactive or invalid counterparty",
        )
        line, kind = p.get("line"), p.get("kind")
        require(line in list("ABCD") and kind in ("QS", "XOL"), "Invalid structure")
        premium, share = number(p, "premium"), number(p, "share")
        require(premium or p.get("zero") is True, "Confirm zero premium explicitly")
        require(0 < share <= 1, "Participation must be in (0,1]")
        q = number(p, "q") if kind == "QS" else None
        att = number(p, "attachment") if kind == "XOL" else None
        limit = number(p, "limit") if kind == "XOL" else None
        require(0 < q <= 1 if kind == "QS" else limit > 0, "Invalid structure terms")
        tid = "T" + str(len(s["tickets"]) + 1) if op == "propose" else t["id"]
        pkg = identifier(p["package"]) if p.get("package") else ""
        deps = p.get("requires", [])
        require(
            isinstance(deps, list)
            and all(
                isinstance(d, str) and d in s["tickets"] and d != tid for d in deps
            ),
            "Unknown/self-linked ticket",
        )
        fee = premium * cfg["public"]["brokerage"]
        require(math.isfinite(fee), "Fee too large")
        s["tickets"][tid] = dict(
            id=tid,
            version=1 if op == "propose" else t["version"] + 1,
            structure=buyer + "-" + line,
            buyer=buyer,
            seller=seller,
            broker=r,
            line=line,
            kind=kind,
            q=q,
            attachment=att,
            limit=limit,
            share=share,
            premium=premium,
            fee=fee,
            package=pkg,
            requires=deps,
            status="pending",
            created=now() if op == "propose" else t["created"],
            updated=now(),
            signatures={r: now()},
        )
    elif op == "withdraw":
        require(t["broker"] == r, "Only the arranging broker may withdraw")
        t.update(status="withdrawn", signatures={}, updated=now())
    else:
        require(
            r in (t["buyer"], t["seller"]) and t["status"] != "rejected",
            "Only current counterparties can sign",
        )
        if op == "reject":
            t.update(
                status="rejected",
                updated=now(),
                signatures={t["broker"]: t["signatures"][t["broker"]]},
            )
        else:
            require(r not in t["signatures"], "Already approved")
            t["signatures"][r] = now()
            if len(t["signatures"]) == 3:
                t["status"] = "signed"
                # Package members can finish signing later. Capacity, exclusivity and
                # funding are checked immediately, under the same write lock as signing.
                errors = [
                    e
                    for e in problems(cfg, s)
                    if "requires signed" not in e and "Incomplete package" not in e
                ]
                require(not errors, "; ".join(errors))
    if op in ("propose", "amend", "withdraw", "reject"):
        changed = s["tickets"][tid] if op in ("propose", "amend") else t
        clear_linked_signatures(s, changed, t)
    dirty(s)


def screen_revision(s, slot):
    """A book/phase change invalidates all desks; independent portfolio and confirmation
    updates only invalidate that team's desk. The instructor always sees a global revision.
    """
    if slot is None:
        return s["rev"]
    return max(s["market_revision"], s["slot_revisions"].get(slot, 0))


def transition(cfg, s, actor, p):
    """Only the console supplies actor=None. Student messages cannot set this argument."""
    op = p.get("op")
    require(isinstance(op, str), "Missing command")
    require(
        p.get("rev") == screen_revision(s, actor),
        "Stale screen. Refresh and review the current version.",
    )
    phase = s["phase"]
    if actor is None:
        if op == "open":
            require(phase == "setup", "Market already opened")
            a = p.get("assign", {})
            require(
                isinstance(a, dict)
                and set(a) <= set(s["slots"])
                and all(r in cfg["roster"] for r in a.values()),
                "Invalid assignment",
            )
            require(
                len(set(a.values())) == len(a)
                and {r[0] for r in a.values()} == set("IRB"),
                "Assign unique teams and at least one of each role",
            )
            s.update(assign=a.copy(), opened=a.copy(), phase="trade")
        elif op == "remove":
            r = p.get("role")
            require(
                phase in ("trade", "review")
                and r in teams(s)
                and p.get("reason", "").strip(),
                "Choose active team and give reason",
            )
            require(sum(x[0] == r[0] for x in teams(s)) > 1, "Last team of this role")
            for k in list(s["assign"]):
                if s["assign"][k] == r:
                    del s["assign"][k]
            for t in s["tickets"].values():
                if r in (t["buyer"], t["seller"], t["broker"]) and t["status"] in (
                    "pending",
                    "signed",
                    "rejected",
                ):
                    t.update(status="invalidated", signatures={}, updated=now())
                    clear_linked_signatures(s, t)
            s["removed"][r] = p["reason"]
            s["removal_reviews"][r] = False
            s["phase"] = "trade"
            dirty(s)
        elif op == "ack_remove":
            r = p.get("role")
            require(
                phase == "trade"
                and r in s["removal_reviews"]
                and not s["removal_reviews"][r],
                "No pending removal review",
            )
            s["removal_reviews"][r] = True
        elif op == "review":
            require(
                all(s["removal_reviews"].values()),
                "Review invalidated tickets and acknowledge each removal first",
            )
            require(phase == "trade", "Open trading first")
            s["phase"] = "review"
        elif op == "reopen":
            require(phase == "review", "Only a provisional review can reopen")
            s["phase"] = "trade"
            dirty(s)
        elif op == "close":
            require(phase == "review", "Enter whole-book review first")
            errors = problems(cfg, s)
            require(not errors, "; ".join(errors))
            require(
                all(s["books"].get(r, {}).get("book") == s["book"] for r in teams(s)),
                "Missing whole-book confirmation",
            )
            for t in s["tickets"].values():
                if t["status"] == "signed":
                    t.update(status="bound", bound=now())
                elif t["status"] in ("pending", "rejected"):
                    t.update(status="expired", updated=now())
            s["phase"] = "invest"
        elif op == "freeze":
            require(
                phase == "invest" and set(s["submitted"]) == set(teams(s)),
                "All active teams must submit investments",
            )
            s.update(phase="frozen", freeze=uuid.uuid4().hex)
        elif op == "unlock":
            require(
                phase == "frozen" and p.get("reason", "").strip(),
                "Unlock requires frozen decisions and a reason",
            )
            s.update(phase="invest", freeze="", submitted={})
        elif op == "settle":
            require(phase == "frozen", "Only a frozen, unsettled market may settle")
            z = draw(cfg, teams(s))
            rows, pays = settle(cfg, teams(s), selected(s), s["weights"], z)
            s.update(
                phase="settled",
                settlement=uuid.uuid4().hex,
                realization=z,
                results=rows,
                payments=pays,
            )
        else:
            raise ValueError("Unknown instructor action")
    else:
        r = s["assign"].get(actor)
        require(r, "Login is inactive")
        if op in ("propose", "amend", "withdraw", "approve", "reject"):
            ticket_action(cfg, s, r, p, op)
        elif op == "confirm":
            require(
                phase == "review" and p.get("book") == s["book"],
                "Review current whole book first",
            )
            require(
                not problems(cfg, s), "Unresolved market conditions; contact instructor"
            )
            s["books"][r] = dict(book=s["book"], time=now())
        elif op == "name":
            require(
                phase in ("trade", "review", "invest")
                and isinstance(p.get("name"), str)
                and len(p["name"]) <= 60,
                "Name unavailable or too long",
            )
            s["names"][r] = p["name"].strip()
        elif op in ("draft", "submit"):
            require(
                phase in ("trade", "review", "invest")
                and (op == "draft" or phase == "invest"),
                "Allocation unavailable in this phase",
            )
            w = [number(p, k) for k in ("short", "long", "etf")]
            total = sum(w)
            require(abs(total - 1) <= cfg["tolerance"], "Weights must sum to 100%")
            s["weights"][r] = [v / total for v in w]
            s["submitted"].pop(r, None)
            if op == "submit":
                s["submitted"][r] = now()
        else:
            raise ValueError("Unauthorized action")
    if s["phase"] != phase:
        s["since"] = now()
    s["rev"] += 1
    if actor is not None and op in ("name", "draft", "submit", "confirm"):
        s["slot_revisions"][actor] = s["rev"]
    else:
        s["market_revision"] = s["rev"]


def command(session, actor, p):
    """Atomic compare-and-set; failures log the attempted action without saving its effects.
    An interrupted draw rolls back and deterministic replay uses the original private seed.
    """
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        cfg, s, _ = read(db, session)
        before = {k: canonical(v) for k, v in s["tickets"].items()}
        who = (
            "instructor"
            if actor is None
            else s["assign"].get(actor, "inactive") + "@" + actor
        )
        try:
            transition(cfg, s, actor, p)
            encoded = canonical(s)
            db.execute("UPDATE market SET state=? WHERE session=?", (encoded, session))
            changed = [
                v for k, v in s["tickets"].items() if before.get(k) != canonical(v)
            ]
            detail = dict(
                command=p,
                tickets=changed,
                book=s["book"],
                rev=s["rev"],
                freeze=s["freeze"],
                settlement=s["settlement"],
            )
            error = ""
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as e:
            error = str(e) or "Invalid command"
            detail = dict(command=p, error=error)
        db.execute(
            "INSERT INTO event(session,time,actor,action,ok,detail) VALUES(?,?,?,?,?,?)",
            (
                session,
                now(),
                who,
                str(p.get("op", ""))
                if str(p.get("op", "")).isidentifier()
                else "invalid_command",
                int(not error),
                json.dumps(detail, default=str),
            ),
        )
        return error


def label(r):
    return {"I": "Insurer", "R": "Reinsurer", "B": "Broker"}[r[0]] + " " + r[1:]


def view(session, actor):
    """Whitelist student payloads. No seed, opponents' sheets or allocation book is sent."""
    with closing(connect()) as db:
        cfg, s, _ = read(db, session)
    common = dict(
        phase=s["phase"],
        since=s["since"],
        minutes=cfg["minutes"].get(s["phase"]),
        rev=screen_revision(s, actor),
        book=s["book"],
    )
    if actor is None:
        return dict(
            **common,
            slots=s["slots"],
            roles=cfg["roster"],
            assign=s["assign"],
            opened=s["opened"],
            removed=s["removed"],
            removal_reviews=s["removal_reviews"],
            teams=teams(s),
            names=s["names"],
            tickets=list(s["tickets"].values()),
            books=s["books"],
            missing_books=sorted(set(teams(s)) - set(s["books"])),
            missing_investments=sorted(set(teams(s)) - set(s["submitted"])),
            issues=problems(cfg, s),
            freeze=s["freeze"],
            settlement=s["settlement"],
        )
    r = s["assign"].get(actor)
    if not r:
        return dict(**common, slot=actor, public=cfg["public"])
    tickets = [
        t for t in s["tickets"].values() if r in (t["buyer"], t["seller"], t["broker"])
    ]
    v = dict(
        **common,
        slot=actor,
        role=r,
        label=label(r),
        name=s["names"].get(r, ""),
        teams=teams(s),
        public=cfg["public"],
        sheet=cfg["private"][r],
        tickets=tickets,
        confirmed=r in s["books"],
        submitted=r in s["submitted"],
        weights=s["weights"].get(r),
        decimals=cfg["decimals"],
        cash=cash(cfg, teams(s), selected(s))[r],
    )
    if s["phase"] == "settled":
        z = s["realization"]
        v.update(
            result=s["results"][r],
            market=z["market"],
            losses={k: x["scaled"] for k, x in z["losses"].get(r, {}).items()},
            payments={
                t["id"]: s["payments"][t["id"]]
                for t in tickets
                if t["status"] == "bound" and r[0] != "B"
            },
        )
    return v
