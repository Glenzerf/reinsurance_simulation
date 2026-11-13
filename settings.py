"""Single-round classroom presets. Production secrets must be supplied by the operator."""
import os
from market_config import PRESETS

SESSION_CONFIGS = [
    dict(
        name="market_" + k,
        display_name="Reinsurance • " + k,
        app_sequence=["market"],
        num_demo_participants=len(v),
        preset=k,
    )
    for k, v in PRESETS.items()
]
SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.0, participation_fee=0.0, doc=""
)
SESSION_FIELDS = []
PARTICIPANT_FIELDS = []
LANGUAGE_CODE = "en"
REAL_WORLD_CURRENCY_CODE = "CAD"
USE_POINTS = False
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = os.environ["OTREE_ADMIN_PASSWORD"]
SECRET_KEY = os.environ["OTREE_SECRET_KEY"]
# Fail closed: debug pages and anonymous admin exports would disclose private data.
if (
    os.environ.get("OTREE_AUTH_LEVEL") != "STUDY"
    or os.environ.get("OTREE_PRODUCTION") != "1"
):
    raise RuntimeError(
        "Set OTREE_AUTH_LEVEL=STUDY and OTREE_PRODUCTION=1 before starting oTree."
    )
