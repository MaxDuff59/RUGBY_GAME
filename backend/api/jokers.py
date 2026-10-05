"""Jokers médicaux du club dirigé.

Quand un pro du club est absent plus de trois mois (engine/medical.py,
`allows_joker`), le manager peut recruter un agent libre en joker, en plus de
son effectif : il négocie son salaire (voie « joker » des transferts), et sa
pige dure jusqu'au retour du blessé, au plus tard jusqu'à la fin de la saison.
Un seul joker par blessure.

À la fin de la pige, un avis (affaire `joker_end`) propose de lui offrir un vrai
contrat ; sans réponse avant le match suivant, il repart, agent libre.
"""

import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.affairs import notify, pending_affairs, settle_unanswered
from api.free_agents import release
from api.ledger import current_season, game_date
from engine.economy import SQUAD_MAX
from engine.free_agents import free_agent_wage
from engine.medical import allows_joker
from engine.transfers import preferred_years
from models import Squad
from models.orm import AffairRow, CareerRow, ClubRow, InjuryRow, JokerRow, NegotiationRow, PlayerRow

LIVE = ("active", "ending")  # au club, en plus de l'effectif
SIGNED = (*LIVE, "kept", "left")  # la blessure a eu son joker


def _money(amount: int) -> str:
    return f"{amount:,} €".replace(",", " ")


def _name(player: PlayerRow) -> str:
    return f"{player.first_name} {player.last_name}"


# --- Lecture -------------------------------------------------------------------------------


def live_jokers(session: Session, club_id: int) -> list[JokerRow]:
    return list(
        session.scalars(
            select(JokerRow).where(JokerRow.club_id == club_id, JokerRow.status.in_(LIVE))
        )
    )


def joker_ids(session: Session, club_id: int) -> set[int]:
    """Joueurs du club en pige (ils ne comptent pas dans l'effectif)."""
    return {row.player_id for row in live_jokers(session, club_id)}


def squad_count(session: Session, club_row: ClubRow) -> int:
    """Effectif pro, jokers médicaux non compris (limites SQUAD_MIN / SQUAD_MAX)."""
    jokers = joker_ids(session, club_row.id)
    return sum(1 for player in club_row.players if player.id not in jokers)


def joker_slots(session: Session, club_row: ClubRow, day: datetime.date) -> list[InjuryRow]:
    """Blessures en cours qui autorisent un joker, et qui n'en ont pas encore."""
    taken = set(
        session.scalars(
            select(JokerRow.injury_id).where(
                JokerRow.club_id == club_row.id, JokerRow.status.in_(SIGNED)
            )
        )
    )
    jokers = joker_ids(session, club_row.id)
    rows = session.scalars(
        select(InjuryRow)
        .join(PlayerRow)
        .where(PlayerRow.club_id == club_row.id, PlayerRow.squad == Squad.PRO.value)
        .order_by(InjuryRow.return_date)
    )
    return [
        row
        for row in rows
        if row.id not in taken
        and row.player_id not in jokers
        and allows_joker(row.to_domain(), day)
    ]


def joker_of(session: Session, injury_id: int) -> JokerRow | None:
    """Le joker recruté pour cette blessure, s'il y en a un."""
    return session.scalars(
        select(JokerRow).where(JokerRow.injury_id == injury_id, JokerRow.status.in_(SIGNED))
    ).first()


# --- Recrutement (voie « joker » des transferts) ---------------------------------------------


def start_talks(
    session: Session, club_id: int, negotiation: NegotiationRow, injury_id: int
) -> None:
    session.add(
        JokerRow(
            club_id=club_id,
            player_id=negotiation.player_id,
            injury_id=injury_id,
            negotiation_id=negotiation.id,
            status="talks",
        )
    )


def sign(session: Session, negotiation: NegotiationRow, year: int) -> str:
    """Accord trouvé : le joker arrive, sous contrat jusqu'à la fin de la saison au plus."""
    joker = session.scalars(
        select(JokerRow).where(JokerRow.negotiation_id == negotiation.id)
    ).first()
    injured = _name(joker.injury.player)
    if joker_of(session, joker.injury_id) is not None:
        raise HTTPException(status_code=400, detail=f"{injured} a déjà son joker médical")
    player = negotiation.player
    player.wage = negotiation.wage
    player.contract_until = year
    player.club_id = negotiation.club_id
    joker.status = "active"
    joker.signed_on = game_date(session)
    return (
        f"{_name(player)} arrive en joker médical jusqu'au retour de {injured}, "
        f"prévu le {joker.injury.return_date:%d/%m/%Y}."
    )


# --- Fin de pige -------------------------------------------------------------------------------


def end_piges(session: Session, season_finished: bool) -> list[AffairRow]:
    """Après une journée : les piges terminées (blessé de retour, ou saison finie)
    donnent lieu à un avis. Renvoie les avis (affaires) créés."""
    career = session.scalars(select(CareerRow)).first()
    season = current_season(session)
    if career is None or season is None:
        return []
    club_row = session.get(ClubRow, career.club_id)
    club = club_row.to_domain()
    day = game_date(session)
    notices = []
    for joker in live_jokers(session, club_row.id):
        player = joker.player
        if player.club_id != club_row.id:
            joker.status = "left"
            continue
        back = joker.injury.return_date <= day
        if joker.status != "active" or not (back or season_finished):
            continue
        joker.status = "ending"
        injured = _name(joker.injury.player)
        domain = next(p for p in club.players if p.id == player.id)
        wage = free_agent_wage(domain, club)
        years = preferred_years(domain)[0]
        # Une saison finie : le contrat court à partir de la saison prochaine.
        first = season.year + 1 if season_finished else season.year
        context = {
            "player": _name(player),
            "player_id": player.id,
            "joker_id": joker.id,
            "injured": injured,
            "reason": (
                f"{injured} est de retour"
                if back
                else f"{injured} n'est pas encore rétabli, mais la saison est finie"
            ),
            "wage": _money(wage),
            "wage_amount": wage,
            "years_label": f"{years} saison{'s' if years > 1 else ''}",
            "contract_until": first + years - 1,
        }
        notices.append(notify(session, club_row.id, season, "joker_end", context))
    session.commit()
    return notices


def _ending_joker(session: Session, club_row: ClubRow, joker_id: int) -> JokerRow:
    joker = session.get(JokerRow, joker_id)
    if (
        joker is None
        or joker.club_id != club_row.id
        or joker.status not in LIVE
        or joker.player.club_id != club_row.id
    ):
        raise HTTPException(status_code=400, detail="Ce joker n'est plus au club")
    return joker


def keep_joker(session: Session, club_row: ClubRow, context: dict) -> None:
    """Le joker signe un vrai contrat : il entre dans l'effectif (s'il y a de la place)."""
    joker = _ending_joker(session, club_row, context["joker_id"])
    if squad_count(session, club_row) >= SQUAD_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Effectif complet ({SQUAD_MAX} joueurs) : libère une place pour le garder",
        )
    joker.player.wage = context["wage_amount"]
    joker.player.contract_until = context["contract_until"]
    joker.status = "kept"


def release_joker(session: Session, club_row: ClubRow, context: dict) -> None:
    """Fin de pige sans contrat : il redevient agent libre."""
    joker = _ending_joker(session, club_row, context["joker_id"])
    # Sa pige compte comme un contrat de la saison en cours (il n'a pas passé
    # une saison entière sans club).
    release(joker.player, current_season(session).year + 1)
    joker.status = "left"


def close_jokers(session: Session, year: int) -> None:
    """Intersaison (avant les mouvements) : les avis restés sans réponse sont réglés
    d'office, et les jokers encore en pige repartent."""
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        return
    club_row = session.get(ClubRow, career.club_id)
    for row in pending_affairs(session, club_row.id):
        if row.scenario == "joker_end":
            settle_unanswered(session, club_row, row)
    for joker in live_jokers(session, club_row.id):
        if joker.player.club_id == club_row.id:
            release(joker.player, year)
        joker.status = "left"
    session.commit()
