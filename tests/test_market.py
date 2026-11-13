"""Offline market regression suite. Each test uses an isolated durable file and real
transactions. Deliberately interrupted transactions must leave no partial settlement."""
import csv
import io
import math
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import numpy as np

import economics as econ
import ledger
import market_config as config
from exports import COLUMNS, csv_bytes
from reconstruct import reconstruct


class Market(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        env = patch.dict(os.environ, MARKET_DB=str(self.folder / "ledger.db"))
        env.start()
        self.addCleanup(env.stop)
        self.roles = ["I1", "R1", "B1", "R2", "I2", "B2"]
        ledger.create("test", [str(i) for i in range(1, 13)], "full")
        self.act(None, "open", assign={str(i): r for i, r in enumerate(self.roles, 1)})

    def state(self):
        with closing(ledger.connect()) as db:
            return ledger.read(db, "test")[1]

    def action(self, r, op, **p):
        slot = None if r is None else str(self.roles.index(r) + 1)
        return ledger.command(
            "test", slot, dict(rev=ledger.view("test", slot)["rev"], op=op, **p)
        )

    def act(self, r, op, **p):
        self.assertEqual(self.action(r, op, **p), "")

    def offer(self, **changes):
        p = dict(
            buyer="I1", seller="R1", kind="QS", line="D", q=0.8, share=0.5, premium=10
        )
        self.act("B1", "propose", **(p | changes))
        return list(self.state()["tickets"].values())[-1]["id"]

    def sign(self, tid):
        t = self.state()["tickets"][tid]
        for r in (t["buyer"], t["seller"]):
            self.act(r, "approve", id=tid, version=t["version"])

    def close_book(self):
        self.act(None, "review")
        for r in ledger.teams(self.state()):
            self.act(r, "confirm", book=self.state()["book"])
        self.act(None, "close")

    def freeze(self):
        for r in ledger.teams(self.state()):
            self.act(r, "submit", short=0.2, long=0.5, etf=0.3)
        self.act(None, "freeze")

    def test_presets_and_privacy(self):
        for k, n in [("full", 12), ("six", 10)]:
            c, h = config.snapshot(k)
            self.assertEqual(len(c["roster"]), n)
            self.assertEqual(len(h), 64)
        v = ledger.view("test", "1")
        self.assertEqual(v["sheet"]["capital"], 401.357)
        self.assertFalse(
            {"realization", "private", "seed", "assign", "weights_by_role"} & set(v)
        )
        self.assertNotIn("R2", v["sheet"]["beliefs"])
        self.assertNotIn("sheet", ledger.view("test", "12"))
        self.assertTrue(self.action("I1", "settle"))
        with patch.dict(config.PUBLIC, direct=999):
            self.assertEqual(ledger.view("test", "1")["public"]["direct"], 130)

    def test_smaller_market_unused_slots_and_no_trade(self):
        ledger.create("small", ["1", "2", "3", "4", "5"], "six")
        self.assertTrue(
            ledger.command(
                "small",
                None,
                dict(rev=0, op="open", assign={"1": "I1", "2": "I1", "3": "B1"}),
            )
        )
        self.assertFalse(
            ledger.command(
                "small",
                None,
                dict(rev=0, op="open", assign={"2": "I6", "3": "B1", "5": "R2"}),
            )
        )
        self.assertNotIn("sheet", ledger.view("small", "1"))
        self.close_book()
        self.freeze()
        self.act(None, "settle")
        v = ledger.view("test", "3")["result"]
        self.assertEqual(
            (v["funds"], v["assets"], v["profit"], v["roe"]), (0, 0, 0, None)
        )
        i = ledger.view("test", "1")["result"]
        self.assertAlmostEqual(i["funds"], i["opening"] + 120)
        self.assertAlmostEqual(i["profit"], 120 + i["gain"] - i["gross"])
        self.assertEqual(ledger.view("test", "2")["result"]["ratio"], 1)

    def test_amend_reject_and_stale(self):
        tid = self.offer()
        self.sign(tid)
        self.act(
            "B1",
            "amend",
            id=tid,
            version=1,
            buyer="I1",
            seller="R1",
            kind="QS",
            line="D",
            q=0.5,
            share=1,
            premium=0,
            zero=True,
        )
        self.assertEqual(set(self.state()["tickets"][tid]["signatures"]), {"B1"})
        self.assertTrue(self.action("I1", "approve", id=tid, version=1))
        self.assertTrue(self.action("B2", "withdraw", id=tid, version=2))
        self.assertTrue(self.action("R2", "approve", id=tid, version=2))
        self.act("I1", "reject", id=tid, version=2)
        self.close_book()
        self.assertEqual(self.state()["tickets"][tid]["status"], "expired")

    def test_validation_and_funding(self):
        for value in ["NaN", "Infinity", -1, 0]:
            with self.assertRaises(AssertionError):
                self.offer(premium=value)
        for values in [
            dict(share=0),
            dict(q=2),
            dict(kind="XOL", limit=0, attachment=3),
            dict(seller="R9"),
        ]:
            with self.assertRaises(AssertionError):
                self.offer(**values)
        tid = self.offer(premium=1000)
        self.act("I1", "approve", id=tid, version=1)
        self.assertIn("fund", self.action("R1", "approve", id=tid, version=1))

    def test_concurrent_final_signatures(self):
        a = self.offer(share=0.6)
        b = self.offer(share=0.6, seller="R2")
        for tid in (a, b):
            self.act("I1", "approve", id=tid, version=1)
        rev = self.state()["rev"]
        with ThreadPoolExecutor(2) as pool:
            replies = list(
                pool.map(
                    lambda pair: ledger.command(
                        "test",
                        pair[0],
                        dict(op="approve", rev=rev, id=pair[1], version=1),
                    ),
                    [("2", a), ("4", b)],
                )
            )
        self.assertEqual(replies.count(""), 1)
        loser = b if not replies[0] else a
        self.assertIn(
            "Over-placement",
            self.action("R2" if loser == b else "R1", "approve", id=loser, version=1),
        )
        self.assertEqual(len(ledger.selected(self.state())), 1)

    def test_packages_removal_and_versions(self):
        a = self.offer(package="P")
        b = self.offer(seller="R2", package="P", requires=[a])
        self.sign(a)
        self.sign(b)
        self.act(None, "review")
        self.act("I1", "confirm", book=self.state()["book"])
        self.act(None, "remove", role="R1", reason="team left")
        state = self.state()
        self.assertFalse(state["books"])
        self.assertEqual(state["tickets"][a]["status"], "invalidated")
        self.assertEqual(state["tickets"][b]["status"], "pending")
        self.assertTrue(self.action(None, "review"))
        self.act(None, "ack_remove", role="R1")
        self.act("B1", "withdraw", id=b, version=1)
        self.close_book()
        self.assertIn("invalidated", csv_bytes("test", "contract_history").decode())

    def test_weights_unlock_and_interruption(self):
        self.close_book()
        self.assertTrue(self.action(None, "freeze"))
        for w in [(0, 0, 0), (-1, 2, 0), (1, 0, "inf")]:
            self.assertTrue(self.action("B1", "submit", **dict(zip(econ.ASSETS, w))))
        self.freeze()
        first = self.state()["freeze"]
        self.act(None, "unlock", reason="clerical error")
        self.assertFalse(self.state()["submitted"])
        self.freeze()
        self.assertNotEqual(first, self.state()["freeze"])
        with patch("ledger.settle", side_effect=RuntimeError("interrupted after draw")):
            with self.assertRaises(RuntimeError):
                self.action(None, "settle")
        self.assertEqual(self.state()["phase"], "frozen")
        self.act(None, "settle")
        z = self.state()["realization"]
        key = self.state()["settlement"]
        self.assertTrue(self.action(None, "settle"))
        self.assertTrue(self.action(None, "unlock", reason="late"))
        self.assertEqual(
            (key, z), (self.state()["settlement"], self.state()["realization"])
        )

    def test_split_and_csv_reconstruction(self):
        a = self.offer(kind="XOL", attachment=40, limit=100, share=0.6)
        b = self.offer(kind="XOL", attachment=40, limit=100, share=0.4, seller="R2")
        self.sign(a)
        self.sign(b)
        self.act("I1", "name", name="=formula")
        self.close_book()
        self.freeze()
        self.assertEqual(
            len(
                list(
                    csv.DictReader(
                        io.StringIO(csv_bytes("test", "investments").decode())
                    )
                )
            ),
            6,
        )
        self.assertIn("'=formula", csv_bytes("test", "investments").decode())
        self.assertFalse(
            list(csv.DictReader(io.StringIO(csv_bytes("test", "realization").decode())))
        )
        self.act(None, "settle")
        for table in COLUMNS:
            (self.folder / (table + ".csv")).write_bytes(csv_bytes("test", table))
        replay = reconstruct(self.folder)
        self.assertEqual(len(replay["tickets"]), 2)
        self.assertEqual(set(replay["teams"]), set(self.roles))

    def test_structure_default_waterfalls(self):
        cfg, _ = config.snapshot("full")
        roles = ["I1", "R1", "R2", "B1"]
        t = dict(
            id="T1",
            buyer="I1",
            seller="R1",
            broker="B1",
            kind="XOL",
            attachment=50,
            limit=100,
            share=0.6,
            premium=10,
            fee=0.2,
            line="D",
        )
        for x, expected in [(49, 0), (50, 0), (120, 42), (150, 60), (200, 60)]:
            self.assertAlmostEqual(econ.recovery(t, x), expected)
        tickets = [t, t | dict(id="T2", seller="R2", share=0.4)]
        z = dict(
            market=dict(short=1, long=1, etf=1), losses={"I1": {"D": {"scaled": 150}}}
        )
        for c2, ratio2 in [(600, 1), (10, 0.5)]:
            cfg["private"]["R1"]["capital"] = 20
            cfg["private"]["R2"]["capital"] = c2
            rows, p = econ.settle(cfg, roles, tickets, {r: [1, 0, 0] for r in roles}, z)
            self.assertEqual(rows["R1"]["ratio"], 0.5)
            self.assertEqual(rows["R2"]["ratio"], ratio2)
            self.assertAlmostEqual(
                rows["I1"]["recovered"], rows["R1"]["paid"] + rows["R2"]["paid"]
            )
            self.assertAlmostEqual(rows["R1"]["shortfall"], 30)
            self.assertAlmostEqual(rows["I1"]["fees_paid"], rows["B1"]["fees_earned"])
            self.assertAlmostEqual(
                sum(v["funds"] for v in rows.values()),
                sum(v["opening"] for v in rows.values()) + 120,
            )

    def test_full_preset_teams_complete_both_markets(self):
        """Exercise every active participant in each preset, with one spare capacity slot."""
        for preset in ("full", "six"):
            roster = config.PRESETS[preset]
            slots = [str(i + 1) for i in range(len(roster) + 1)]
            ledger.create(preset, slots, preset)

            def send(slot, op, **terms):
                version = ledger.view(preset, slot)["rev"]
                self.assertFalse(
                    ledger.command(preset, slot, dict(op=op, rev=version, **terms))
                )

            send(None, "open", assign=dict(zip(slots, roster)))
            send(None, "review")
            for slot in slots[:-1]:
                send(slot, "confirm", book=ledger.view(preset, slot)["book"])
            send(None, "close")
            for slot in slots[:-1]:
                send(
                    slot,
                    "submit",
                    short=0.2,
                    long=0.3,
                    etf=0.5 + config.WEIGHT_TOLERANCE / 2,
                )
            send(None, "freeze")
            send(None, "settle")
            self.assertEqual(
                len(
                    list(
                        csv.DictReader(
                            io.StringIO(csv_bytes(preset, "settlement").decode())
                        )
                    )
                ),
                len(roster),
            )
            self.assertNotIn("sheet", ledger.view(preset, slots[-1]))
            self.assertAlmostEqual(sum(ledger.view(preset, "1")["weights"]), 1)
            self.assertEqual(ledger.view("test", None)["phase"], "trade")

    def test_hard_exit_rolls_back_draw(self):
        """Kill a separate writer between random generation and settlement commit."""
        self.close_book()
        self.freeze()
        freeze = self.state()["freeze"]
        child = """import os, ledger
def interrupt(*args):
    os._exit(23)
ledger.settle=interrupt
v=ledger.view('test',None)
ledger.command('test',None,dict(op='settle',rev=v['rev']))
"""
        run = subprocess.run([sys.executable, "-c", child], check=False)
        self.assertEqual(run.returncode, 23)
        self.assertEqual(self.state()["phase"], "frozen")
        self.assertNotIn("realization", self.state())
        with closing(ledger.connect()) as db:
            cfg, s, _ = ledger.read(db, "test")
        expected = econ.draw(cfg, ledger.teams(s))
        self.act(None, "settle")
        self.assertEqual(self.state()["freeze"], freeze)
        self.assertEqual(self.state()["realization"], expected)

    def test_competing_terms_packages_and_duplicate_commands(self):
        tid = self.offer(package="A")
        other = self.offer(
            seller="R2", kind="XOL", attachment=10, limit=40, package="A"
        )
        self.sign(tid)
        self.act("I1", "approve", id=other, version=1)
        self.assertIn("Conflicting", self.action("R2", "approve", id=other, version=1))
        self.act("B1", "withdraw", id=other, version=1)
        self.assertEqual(self.state()["tickets"][tid]["status"], "pending")
        self.sign(tid)
        self.assertIn("Incomplete package A", ledger.view("test", None)["issues"])
        self.act(
            "B1",
            "amend",
            id=tid,
            version=1,
            buyer="I1",
            seller="R1",
            line="D",
            kind="QS",
            q=0.8,
            share=0.5,
            premium=10,
        )
        self.sign(tid)
        self.close_book()
        same = dict(
            op="submit", rev=ledger.view("test", "1")["rev"], short=1, long=0, etf=0
        )
        self.assertFalse(ledger.command("test", "1", same))
        self.assertIn("Stale", ledger.command("test", "1", same))

    def test_multiple_claimants_share_one_default(self):
        cfg, _ = config.snapshot("full")
        cfg["private"]["R1"]["capital"] = 30
        roles = ["I1", "I2", "R1", "B1"]
        t = dict(
            id="T1",
            buyer="I1",
            seller="R1",
            broker="B1",
            kind="QS",
            q=1,
            share=1,
            premium=0,
            fee=0,
            line="D",
        )
        z = dict(
            market=dict(short=1, long=1, etf=1),
            losses={"I1": {"D": {"scaled": 1000}}, "I2": {"D": {"scaled": 500}}},
        )
        rows, pays = econ.settle(
            cfg,
            roles,
            [t, t | dict(id="T2", buyer="I2")],
            {r: [1, 0, 0] for r in roles},
            z,
        )
        self.assertEqual(rows["R1"]["ratio"], 0.02)
        self.assertEqual((pays["T1"]["paid"], pays["T2"]["paid"]), (20, 10))
        self.assertAlmostEqual(
            rows["I1"]["shortfall"], 1000 - rows["I1"]["policyholders_paid"]
        )
        self.assertEqual(rows["I1"]["residual"], 0)
        self.assertLess(rows["I1"]["profit"], 0)

    def test_zero_frequency_and_private_law(self):
        c, _ = config.snapshot("full")
        self.assertEqual(
            (
                c["realization"]["B"]["shape"],
                c["realization"]["C"]["mean"],
                c["realization"]["C"]["sd"],
                c["realization"]["D"]["prob"],
            ),
            (2.3, 2.75, 5.5, 0.17),
        )
        c["realization"]["A"]["count"] = c["realization"]["C"]["count"] = 0
        c["realization"]["D"]["prob"] = c["realization"]["B"]["prob"] = 0
        z = econ.draw(c, ["I1", "I2"])
        self.assertTrue(
            all(
                v["scaled"] == 0 and not v["severities"]
                for lines in z["losses"].values()
                for v in lines.values()
            )
        )
        self.assertEqual(c["private"]["I3"]["beliefs"]["C_sd_cases"], [5, 7])
        self.assertEqual(
            c["private"]["I4"]["beliefs"], dict(equity_floor=20, probability=0.01)
        )

    def test_distribution_moments_and_dependence(self):
        cfg, _ = config.snapshot("full")
        cfg["realization"] = cfg["public"]["loss"]
        vals = []
        events = []
        for seed in range(4000):
            cfg["seed"] = seed
            z = econ.draw(cfg, ["I1", "I2"])
            a = z["losses"]["I1"]
            b = z["losses"]["I2"]
            self.assertEqual(a["D"]["standard"], b["D"]["standard"])
            self.assertAlmostEqual(a["D"]["scaled"], 1.2 * a["D"]["standard"])
            self.assertAlmostEqual(
                z["market"]["long"], 1.033**4 / (1 + z["market"]["yield_end"]) ** 3
            )
            vals.append([a[k]["standard"] for k in "ABCD"] + [z["market"]["etf"]])
            events.append([a["B"]["count"], b["B"]["count"]])
        means = np.mean(vals, axis=0)
        for value, tolerance in zip(means[:4], [0.25, 4, 1, 3]):
            self.assertLess(abs(value - 25), tolerance)
        self.assertLess(abs(means[4] - 1.07), 0.012)
        self.assertLess(abs(np.std(np.array(vals)[:, 4]) - 0.2), 0.012)
        self.assertLess(abs(np.corrcoef(np.transpose(events))[0, 1]), 0.06)
        for mean, sd in [(2.5, 5), (2.75, 5.5), (1.07, 0.2)]:
            mu, sigma = econ.log_parameters(mean, sd)
            self.assertAlmostEqual(math.exp(mu + sigma**2 / 2), mean)
            self.assertAlmostEqual(mean * math.sqrt(math.expm1(sigma**2)), sd)


if __name__ == "__main__":
    unittest.main()
