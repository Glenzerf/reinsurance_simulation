"""Instructor configuration. Edit before creating a session. Cash and severity are millions;
probabilities, yields, returns, portfolio weights and treaty shares are decimal fractions.
The classroom engine reads the stored snapshot, never these defaults, after creation.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
import secrets
import platform
from importlib.metadata import version

LOSS = dict(
    A=dict(count=250, shape=2, scale=0.05),
    B=dict(prob=0.10, minimum=150, shape=2.5),
    C=dict(count=10, mean=2.5, sd=5),
    D=dict(prob=0.15, shape=4, scale=41.667),
)
PUBLIC = dict(
    loss=LOSS,
    direct=130,
    expenses=10,
    brokerage=0.02,
    target=0.10,
    ordinary_cost=0.10,
    shortfall_cost=0.20,
    solvency=0.01,
    assets=dict(
        short_yield=0.02,
        long_yield=0.033,
        remaining_years=3,
        yields=[0.013, 0.033, 0.053],
        probabilities=[0.25, 0.50, 0.25],
        etf_mean=1.07,
        etf_sd=0.20,
    ),
)
# Overrides apply to a deep copy of the benchmark; there is only one realized market.
REALIZATION = deepcopy(LOSS)
REALIZATION["B"]["shape"] = 2.3
REALIZATION["C"].update(mean=2.75, sd=5.5)
REALIZATION["D"]["prob"] = 0.17
# Private regulatory checks supplement the public law in the external assessment only.
BELIEFS = {
    "I3": dict(C_mean=2.5, C_sd_cases=[5, 7]),
    "I4": dict(equity_floor=20, probability=0.01),
    "R1": dict(B_shape=2.2, D_prob=0.18),
    "R2": dict(C_mean=2.2, C_sd=5, D_prob=0.12),
}
# Role IDs are persistent keys. Add another R or B here, provide its text below, then
# include it in a preset. Each insurer has exactly four annual aggregate multipliers.
INSURERS = [
    (401.357, [1, 0.8, 1, 1.2]),
    (465, [0.8, 1.4, 0.8, 1]),
    (315, [1.2, 1, 1.4, 0.4]),
    (423.610, [1, 0.6, 1, 1.4]),
    (356.591, [1.4, 0.8, 0.8, 1]),
    (467.434, [0.8, 1.2, 1, 1]),
    (482.332, [1, 1, 0.6, 1.4]),
    (408.732, [0.8, 1, 1.2, 1]),
]
ROLES = {
    f"I{i}": dict(capital=c, exposures=dict(zip("ABCD", x)))
    for i, (c, x) in enumerate(INSURERS, 1)
}
ROLES.update(
    R1=dict(capital=600), R2=dict(capital=600), B1=dict(capital=0), B2=dict(capital=0)
)
PRESETS = dict(full=list(ROLES), six=[r for r in ROLES if r not in ("I7", "I8")])
# A null seed requests fresh private entropy. A fixed integer reproduces a rehearsal.
SEED = None
WEIGHT_TOLERANCE = 1e-8
DISPLAY_DECIMALS = 3
PHASE_MINUTES = (
    {}
)  # Optional advisory countdown, e.g. {'trade':45}. Never signs for a team.

# Private handout wording, updated for the financial charge.
MANDATES = {
    "B1": "Your market information\n"
    "A catastrophe study estimates the probability of a widespread flood at about 20%, with "
    "considerable uncertainty. It flags Insurer 4 and Insurer 7 as potentially more exposed to "
    "flooding than a standard insurer. Their actual multipliers are private.",
    "B2": "Your market information\n"
    "A claims survey suggests the average individual product liability claim may be 10–25% larger "
    "than the public estimate of 2.5. The survey gives no new estimate of dispersion. Some insurers "
    "may be particularly concerned about liability, but the survey does not identify them.",
    "I1": "Your mandate\n"
    "Your board prefers a probability of negative ending equity of at most 0.5%. How much is the "
    "extra rating buffer worth to you? Use the common 1% rule for required capital. The 0.5% "
    "preference does not change the post-class capital charge.",
    "I2": "Your mandate\n"
    "Preserve room for growth. Seek the most free capital you can obtain on economically sound "
    "terms. Measure headroom as opening equity less the capital your final book requires. The game "
    "assigns no separate cash payoff to future growth.",
    "I3": "Your mandate\n"
    "Your claims staff consider two possible standard deviations for individual product liability "
    "claims: 5 and 7. In both models the mean is 2.5. You must meet the 1% solvency rule under both "
    "models. Use the larger capital requirement to value each strategy and determine any shortfall.",
    "I4": "Your mandate\n"
    "Your lender requires the probability that ending equity falls below 20 to be at most 1%. This "
    "covenant applies alongside the solvency rule. Add 20 to retained claims before dividing by H in "
    "the capital calculation. Use the covenant when valuing a placement and calculating any equity "
    "shortfall.",
    "I5": "Your mandate\n"
    "Your shareholders seek economic value and accept operating close to the 1% solvency limit. "
    "Compare the expected signed ending equity with the expected residual paid to shareholders. "
    "Losses left with creditors can make these measures differ.",
    "I6": "Your mandate\n"
    "Your board values stable earnings. Consider both the standard deviation of ending equity and "
    "the probability that accounting profit is negative. Decide how much expected economic value, if "
    "any, you would give up for smoother earnings.",
    "I7": "Your mandate\n"
    "Your board prefers that no single line account for more than 50% of retained losses in the "
    "worst 1% of years for total retained claims. In those same years, divide each line’s mean "
    "retained claims by the mean total. Use actual recoveries. This is a preference; it does not "
    "change the post-class capital charge.",
    "I8": "Your mandate\n"
    "Your board prefers that no reinsurer account for more than 70% of promised recoveries in the "
    "worst 1% of years for your gross losses. In those years, divide each seller’s average promised "
    "recovery by the combined average. If the denominator is zero, the measure is undefined. This "
    "preference does not change the post-class capital charge.",
    "R1": "Your loss estimates\n"
    "For regional wildfire, use Pareto shape 2.2. For widespread flooding, use an annual event "
    "probability of 18%. Keep all other public parameters.\n"
    "Your mandate\n"
    "Your board prefers a default probability of at most 0.5%. Decide how much business you would "
    "give up for this buffer. Use the common 1% rule to calculate required capital. The 0.5% "
    "preference does not change the post-class capital charge.",
    "R2": "Your loss estimates\n"
    "For individual product liability claims, use an arithmetic mean of 2.2 and a standard deviation "
    "of 5. For widespread flooding, use an annual event probability of 12%. Keep all other public "
    "parameters.\n"
    "Your mandate\n"
    "Your board wants profitable growth and efficient use of capital. It accepts a book close to the "
    "1% solvency limit if the premiums justify the risk.",
}


def canonical(obj):
    """Portable representation for snapshot hashing and durable journal payloads."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def snapshot(preset):
    """Fail during setup for invalid laws, rosters or numerical conventions."""
    roles = PRESETS[preset]
    assert_valid(
        len(roles) == len(set(roles)) and {r[0] for r in roles} == set("IRB"),
        "Invalid preset",
    )
    for r in roles:
        assert_valid(
            re.fullmatch(r"[IRB][1-9][0-9]*", r) and r in MANDATES, "Missing role sheet"
        )
        c = ROLES[r]["capital"]
        assert_valid(c == 0 if r[0] == "B" else c > 0, "Invalid opening capital")
        if r[0] == "I":
            x = ROLES[r]["exposures"]
            assert_valid(
                set(x) == set("ABCD") and min(x.values()) >= 0, "Invalid exposures"
            )
        assert_valid(
            isinstance(MANDATES[r], str) and MANDATES[r].strip(),
            "Empty private handout",
        )
        for key, value in BELIEFS.get(r, {}).items():
            if key in ("D_prob", "probability"):
                assert_valid(0 <= value <= 1, "Invalid private probability")
            elif key == "C_sd_cases":
                assert_valid(
                    value and all(v >= 0 for v in value),
                    "Invalid private severity cases",
                )
            elif key == "B_shape":
                assert_valid(value > 1, "Private Pareto mean must exist")
            elif key in ("C_mean", "C_sd", "equity_floor"):
                assert_valid(
                    value > 0 if key == "C_mean" else value >= 0,
                    "Invalid private check",
                )
    for law in (PUBLIC["loss"], REALIZATION):
        fields = {
            "A": {"count", "shape", "scale"},
            "B": {"prob", "minimum", "shape"},
            "C": {"count", "mean", "sd"},
            "D": {"prob", "shape", "scale"},
        }
        assert_valid(
            set(law) == set(fields)
            and all(set(law[k]) == v for k, v in fields.items()),
            "Incomplete loss law",
        )
        for line, p in law.items():
            for k, v in p.items():
                ok = (
                    0 <= v <= 1
                    if k == "prob"
                    else v >= 0
                    if k in ("count", "sd")
                    else v > 0
                )
                assert_valid(ok, f"Invalid {line}.{k}")
        assert_valid(law["B"]["shape"] > 1, "Pareto mean must exist")
    a = PUBLIC["assets"]
    assert_valid(
        len(a["yields"]) == len(a["probabilities"])
        and min(a["probabilities"]) >= 0
        and math.isclose(sum(a["probabilities"]), 1)
        and min([a["short_yield"], a["long_yield"], *a["yields"]]) > -1
        and a["etf_mean"] > 0
        and a["etf_sd"] >= 0
        and a["remaining_years"] >= 1,
        "Invalid asset law",
    )
    assert_valid(
        0 < PUBLIC["solvency"] < 1
        and 0 <= PUBLIC["ordinary_cost"] <= PUBLIC["shortfall_cost"]
        and min(PUBLIC[k] for k in ("direct", "expenses", "brokerage", "target")) >= 0,
        "Invalid costs",
    )
    assert_valid(
        0 < WEIGHT_TOLERANCE < 0.001 and 0 <= DISPLAY_DECIMALS <= 12,
        "Invalid precision",
    )
    assert_valid(
        all(
            k in ("trade", "review", "invest") and v > 0
            for k, v in PHASE_MINUTES.items()
        ),
        "Invalid timer",
    )
    cfg = deepcopy(
        dict(
            version=1,
            public=PUBLIC,
            private={
                r: {**ROLES[r], "mandate": MANDATES[r], "beliefs": BELIEFS.get(r, {})}
                for r in roles
            },
            realization=REALIZATION,
            roster=roles,
            seed=secrets.randbits(128) if SEED is None else SEED,
            seed_mode="random" if SEED is None else "fixed",
            tolerance=WEIGHT_TOLERANCE,
            decimals=DISPLAY_DECIMALS,
            minutes=PHASE_MINUTES,
            code="1.0",
            rng="PCG64",
            numpy=version("numpy"),
            otree=version("otree"),
            python=platform.python_version(),
        )
    )
    assert_valid(
        isinstance(cfg["seed"], int) and cfg["seed"] >= 0,
        "Seed must be a nonnegative integer",
    )
    return cfg, hashlib.sha256(canonical(cfg).encode()).hexdigest()


def assert_valid(condition, message):
    """Raise even when Python runs with optimizations enabled."""
    if not condition:
        raise ValueError(message)
