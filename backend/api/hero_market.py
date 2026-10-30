"""Carrière de joueur : le mercato de fin de saison (engine/hero_market.py).

Une fois la saison de son championnat finie, le joueur reçoit des offres : prolonger
dans son club, partir dans un club à sa portée, ou être prêté s'il a peu joué. Elles se
calculent une fois par saison et par agent, puis restent (`HeroRow.offers`). Le choix
(`HeroRow.choice`) s'applique à l'intersaison, après la fin des prêts
(api/hero.py, `apply_choice`).
"""

import random

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import careers
from api import hero as heroes
from api.deps import load_club
from api.ledger import current_season
from api.routers.seasons import _phase, focus_league
from api.schemas import ClubRef, HeroOfferOut, HeroOffersOut
from data.leagues import league_config
from engine import hero_market as rules
from engine.economy import wage_for
from engine.match_engine import FORMATION, RATING_FOR_POSITION
from models import Position
from models.orm import ClubRow, PlayerRow


def season_finished(session: Session) -> bool:
    season = current_season(session)
    return season is not None and _phase(season, focus_league(session)) == "finished"


def _role(session: Session, club_id: int, player) -> str:
    """Sa place dans ce club, à son poste : titulaire, rotation ou espoir."""
    club = load_club(session, club_id)
    rating = RATING_FOR_POSITION[player.position]
    better = sum(
        1 for p in club.players if p.position == player.position and p.id != player.id
        and rating(p) > rating(player)
    )  # fmt: skip
    slots = FORMATION[Position(player.position)]
    return "starter" if better < slots else "rotation" if better <= slots else "prospect"


def offers(session: Session) -> list[dict]:
    """Les offres de la fin de saison, calculées une fois par saison et par agent."""
    row = heroes.hero(session)
    season = current_season(session)
    if not season_finished(session):
        return []
    cached = row.offers or {}
    if cached.get("year") == season.year and cached.get("agent") == row.agent:
        return cached["list"]
    player_row = session.get(PlayerRow, row.player_id)
    player = player_row.to_domain()
    current = player.club_id
    agent = rules.AGENTS[row.agent]
    out = heroes.hero_out(session, season)
    played = [m for m in out.matches if m.minutes > 0]
    average = sum(m.rating or 6 for m in played) / len(played) if played else None
    club_matches = [m for m in [*season.matches, *season.cup_matches]
                    if m.is_played and current in (m.home_club_id, m.away_club_id)]  # fmt: skip
    share = sum(m.minutes for m in out.matches) / max(1, 80 * len(club_matches))
    worth = rules.value(player.overall, average, len(played))
    market = careers.market(session)
    levels, prestige = market.levels, market.prestige
    rng = random.Random(f"hero-offers:{season.year}:{player.id}:{row.agent}")
    base = wage_for(player)
    found = [
        {
            "kind": "extend",
            "club_id": current,
            "wage": rules.wage(base, 0.0, agent),
            "years": rules.EXTENSION_YEARS,
        }
    ]
    for club_id in rules.transfer_clubs(worth, current, levels, prestige, agent, rng):
        found.append(
            {
                "kind": "transfer",
                "club_id": club_id,
                "wage": rules.wage(base, prestige[club_id] - prestige[current], agent),
                "years": rng.randint(*rules.TRANSFER_YEARS),
            }
        )
    for club_id in rules.loan_clubs(current, levels, prestige, share, rng):
        found.append({"kind": "loan", "club_id": club_id, "wage": player.wage, "years": 1})
    for offer in found:
        offer["role"] = _role(session, offer["club_id"], player)
        offer["level"] = round(levels[offer["club_id"]], 1)
    row.offers = {"year": season.year, "agent": row.agent, "list": found}
    return found


def offers_out(session: Session) -> HeroOffersOut:
    row = heroes.hero(session)
    player = session.get(PlayerRow, row.player_id)
    found = offers(session)
    ids = [offer["club_id"] for offer in found]
    clubs = {club.id: club for club in session.scalars(select(ClubRow).where(ClubRow.id.in_(ids)))}
    agent = rules.AGENTS[row.agent]
    chosen = row.choice or {}
    return HeroOffersOut(
        open=season_finished(session),
        wage=player.wage,
        contract_until=player.contract_until,
        agent=row.agent,
        offers=[
            HeroOfferOut(
                index=index,
                kind=offer["kind"],
                club=ClubRef(id=offer["club_id"], name=clubs[offer["club_id"]].name),
                league_name=league_config(clubs[offer["club_id"]].league).short_name,
                level=offer["level"],
                wage=offer["wage"],
                net_wage=round(offer["wage"] * (1 - agent.commission)),
                years=offer["years"],
                role=offer["role"],
                chosen=chosen.get("kind") == offer["kind"]
                and chosen.get("club_id") == offer["club_id"],
            )
            for index, offer in enumerate(found)
        ],
    )


def choose(session: Session, index: int | None) -> None:
    """Choisit une offre (None : ne rien changer). 400 hors mercato ou offre inconnue."""
    found = offers(session)
    if not found:
        raise HTTPException(status_code=400, detail="Le mercato ouvre à la fin de la saison")
    row = heroes.hero(session)
    if index is None:
        row.choice = None
        return
    if not 0 <= index < len(found):
        raise HTTPException(status_code=404, detail="Offre inconnue")
    row.choice = dict(found[index])


def set_agent(session: Session, agent: str) -> None:
    if agent not in rules.AGENTS:
        raise HTTPException(status_code=400, detail=f"Agent « {agent} » inconnu")
    row = heroes.hero(session)
    row.agent = agent
    row.choice = None  # les offres changent avec l'agent
