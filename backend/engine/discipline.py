"""Discipline : la commission de discipline passe après les cartons.

Après chaque match de club :
- un carton rouge direct vaut de un à six matchs de suspension, selon la gravité
  de la faute (tirée au sort, les petites peines sont les plus fréquentes) ;
- un rouge pour un second jaune dans le même match vaut un match ;
- trois cartons jaunes dans la saison valent un match, et le compteur repart à zéro.

Un joueur suspendu purge sa peine sur les matchs de son club (ni blessé, ni
retenu : il n'est simplement pas qualifié) ; un match international ne compte
pas. Le compteur de jaunes repart à zéro à chaque saison, les suspensions
restantes courent d'une saison à l'autre.
"""

import random
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from models import Club, EventType, Match, Player

# Matchs de suspension pour un rouge direct, et leurs chances.
RED_CARD_BANS = {1: 0.20, 2: 0.35, 3: 0.25, 4: 0.12, 6: 0.08}
SECOND_YELLOW_BAN = 1
YELLOW_CARDS_LIMIT = 3
YELLOW_CARDS_BAN = 1


class Reason(StrEnum):
    RED_CARD = "red_card"  # carton rouge direct
    SECOND_YELLOW = "second_yellow"  # deux jaunes dans le même match
    YELLOW_CARDS = "yellow_cards"  # trois jaunes dans la saison


@dataclass(frozen=True)
class Suspension:
    club_id: int
    player_id: int
    matches: int
    reason: Reason


def serve(club: Club) -> list[Player]:
    """Le club a joué : chacun de ses suspendus purge un match, espoirs compris (un espoir
    monté pour un doublon a pu prendre un carton). Renvoie ceux qui en purgeaient."""
    serving = [p for p in [*club.players, *club.youths] if p.is_suspended]
    for player in serving:
        player.suspended_matches -= 1
    return serving


def sanctions(match: Match, players: dict[int, Player], rng: random.Random) -> list[Suspension]:
    """Les suspensions que vaut ce match ; elles s'ajoutent aussitôt aux joueurs."""
    suspensions = []
    yellows: dict[int, int] = {}
    for event in match.events:
        player = players.get(event.player_id)
        if player is None:
            continue
        if event.type == EventType.YELLOW_CARD:
            yellows[player.id] = yellows.get(player.id, 0) + 1
            player.yellow_cards += 1
        elif event.type == EventType.RED_CARD:
            if yellows.get(player.id):
                # Les deux jaunes valent ce rouge : ils ne comptent plus au cumul (le
                # second n'est pas un événement à part, seul le premier est à retirer).
                player.yellow_cards -= 1
                matches, reason = SECOND_YELLOW_BAN, Reason.SECOND_YELLOW
            else:
                bans = list(RED_CARD_BANS)
                matches = rng.choices(bans, weights=list(RED_CARD_BANS.values()))[0]
                reason = Reason.RED_CARD
            suspensions.append(_suspend(event.club_id, player, matches, reason))
    for player_id in yellows:
        player = players[player_id]
        if player.yellow_cards >= YELLOW_CARDS_LIMIT:
            player.yellow_cards -= YELLOW_CARDS_LIMIT
            club_id = next(e.club_id for e in match.events if e.player_id == player_id)
            suspensions.append(_suspend(club_id, player, YELLOW_CARDS_BAN, Reason.YELLOW_CARDS))
    return suspensions


def _suspend(club_id: int, player: Player, matches: int, reason: Reason) -> Suspension:
    player.suspended_matches += matches
    return Suspension(club_id, player.id, matches, reason)


def new_season(players: Iterable[Player]) -> None:
    """Intersaison : les jaunes de la saison passée ne comptent plus."""
    for player in players:
        player.yellow_cards = 0
