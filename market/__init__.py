"""oTree adapter. Each team keeps its own participant URL for the entire exercise.
A live page can render every phase without a wait page or a gate on absent players.
"""
from otree.api import BaseConstants, BaseSubsession, BaseGroup, BasePlayer, Page
import ledger
from exports import COLUMNS, dataset
from market_config import canonical


class C(BaseConstants):
    NAME_IN_URL = "reinsurance"
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    pass


def creating_session(subsession):
    """oTree creates exactly one market group when PLAYERS_PER_GROUP is None."""
    (group,) = subsession.get_groups()
    ledger.create(
        subsession.session.code,
        [str(p.participant.id_in_session) for p in group.get_players()],
        subsession.session.config["preset"],
    )


class Desk(Page):
    @staticmethod
    def live_method(player, data):
        """Identity is determined by oTree. Never accept an actor or session from JS."""
        key, slot = player.session.code, str(player.participant.id_in_session)
        error = ""
        if not isinstance(data, dict):
            error = "Invalid request"
        elif data.get("op") != "sync":
            error = ledger.command(key, slot, data)
        return {player.id_in_group: dict(state=ledger.view(key, slot), error=error)}

    @staticmethod
    def error_message(player, values):
        """Even a manual next-page POST keeps the login on its live team desk."""
        return "Keep this desk open or revisit your participant link."


page_sequence = [Desk]


def custom_export(players):
    """oTree 5 supports one custom export function. This long-form envelope preserves
    all seven schemas; the password-protected console offers separate ordinary CSVs."""
    yield ["dataset", "row_json"]
    for session in sorted({p.session.code for p in players}):
        for name in COLUMNS:
            stream = iter(dataset(session, name))
            header = next(stream)
            for row in stream:
                yield [name, canonical(dict(zip(header, row)))]
