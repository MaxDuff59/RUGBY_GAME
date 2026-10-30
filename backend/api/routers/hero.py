"""Carrière de joueur : créer son joueur, suivre sa progression, placer ses points.

`POST /hero` crée le joueur (18 ans, faible niveau, le profil de son poste) dans
l'effectif pro du club choisi, et remplace toute autre carrière de la partie. Il
joue ensuite les journées de son club : en direct (api/routers/live.py), où le match
s'arrête sur ses dilemmes, ou simulées (`POST /seasons/current/play`). Chaque
journée lui rapporte de l'expérience (api/hero.py), donc des points d'attributs à
placer (`POST /hero/train`). Les réseaux sociaux parlent de lui (`GET /hero/social`).
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete

from api import hero as heroes
from api import hero_market, plans
from api.auth import UserDep
from api.deps import SessionDep, load_club
from api.ledger import current_season, game_date
from api.routers.seasons import FIRST_SEASON_YEAR, create_season
from api.schemas import (
    CareerOut,
    HeroAgentIn,
    HeroCareerOut,
    HeroChoiceIn,
    HeroHurtIn,
    HeroIn,
    HeroOffersOut,
    HeroOut,
    HeroTrainIn,
    SocialOut,
)
from data.leagues import league_config
from data.nations import home_nation
from engine import hero as rules
from engine.economy import wage_for
from models import Player, Squad
from models.orm import (
    CareerRow,
    DismissalRow,
    HeroRow,
    LiveInternationalRow,
    LiveMatchRow,
    PlayerRow,
    SelectorRow,
)

router = APIRouter(prefix="/hero", tags=["carrière de joueur"])


def hero_career_out(session, row: HeroRow) -> CareerOut:
    """La carrière de joueur sous la forme commune des carrières (`GET /career`)."""
    player = session.get(PlayerRow, row.player_id)
    club = load_club(session, player.club_id) if player.club_id is not None else None
    return CareerOut(
        id=row.id,
        manager_name=f"{player.first_name} {player.last_name}",
        kind="player",
        club_id=club.id if club else 0,
        club_name=club.name if club else "Sans club",
        league=club.league if club else "",
        league_name=league_config(club.league).name if club else "Retraité",
    )


@router.post("", response_model=CareerOut, status_code=201)
def start_hero(payload: HeroIn, session: SessionDep, user: UserDep) -> CareerOut:
    """Crée le joueur et sa carrière dans le club choisi. Dans un monde neuf, ouvre la
    première saison, qui compte dans celles du compte (api/plans.py)."""
    season = current_season(session)
    first_season = season is None
    if first_season:
        plans.require_season(user)
    club = load_club(session, payload.club_id)
    kinds = (CareerRow, SelectorRow, HeroRow, DismissalRow)
    for table in (*kinds, LiveMatchRow, LiveInternationalRow):
        session.execute(delete(table))
    if first_season:
        session.commit()
        season = create_season(session, FIRST_SEASON_YEAR)
        plans.count_season(user)

    player = Player(
        id=0,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        age=rules.START_AGE,
        position=payload.position,
        club_id=club.id,
        squad=Squad.PRO,
        nationality=home_nation(club.name),
        contract_until=season.year + rules.START_CONTRACT_YEARS,
        **rules.start_attributes(payload.position),
    )
    player.wage = wage_for(player)
    player_row = PlayerRow.from_domain(player)
    player_row.id = None
    # Il progresse par ses points, pas tout seul : son potentiel est sa note du jour.
    player_row.potential = round(player.level, 1)
    session.add(player_row)
    session.flush()
    row = HeroRow(
        player_id=player_row.id,
        points=rules.START_POINTS,
        xp=0,
        rewarded=[],
        signed_on=game_date(session),
    )
    session.add(row)
    session.commit()
    return hero_career_out(session, row)


def _hero_or_404(session):
    row = heroes.hero(session)
    if row is None:
        raise HTTPException(status_code=404, detail="Aucune carrière de joueur en cours")
    return row


@router.get("", response_model=HeroOut)
def get_hero(session: SessionDep) -> HeroOut:
    """Le joueur incarné : attributs, prix du point suivant, place dans l'effectif, ses
    matchs de la saison et ce qu'a rapporté la dernière journée."""
    _hero_or_404(session)
    return heroes.hero_out(session, current_season(session))


@router.post("/train", response_model=HeroOut)
def train(payload: HeroTrainIn, session: SessionDep) -> HeroOut:
    """Place des points dans un attribut : un point de plus, au prix de sa valeur."""
    _hero_or_404(session)
    try:
        heroes.train(session, payload.attribute)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    session.commit()
    return heroes.hero_out(session, current_season(session))


@router.get("/social", response_model=SocialOut)
def get_social(session: SessionDep) -> SocialOut:
    """Ce que les médias, les journalistes et les supporters disent du joueur incarné."""
    _hero_or_404(session)
    # En fin de saison, la presse parle des clubs qui le veulent.
    wanted = [o["club_id"] for o in hero_market.offers(session) if o["kind"] == "transfer"]
    out = heroes.social_out(session, wanted)
    session.commit()
    return out


@router.post("/play-hurt", response_model=HeroOut)
def play_hurt(payload: HeroHurtIn, session: SessionDep) -> HeroOut:
    """Blessé, il joue quand même le prochain match de son club (diminué, et au risque
    d'aggraver sa blessure) ; ou il se soigne."""
    _hero_or_404(session)
    heroes.set_play_hurt(session, payload.play)
    session.commit()
    return heroes.hero_out(session, current_season(session))


@router.get("/offers", response_model=HeroOffersOut)
def get_offers(session: SessionDep) -> HeroOffersOut:
    """Le mercato de fin de saison : prolonger, partir, ou être prêté (vide avant la fin
    de la saison de son championnat)."""
    _hero_or_404(session)
    out = hero_market.offers_out(session)
    session.commit()  # les offres calculées restent pour la saison
    return out


@router.post("/offers/choose", response_model=HeroOffersOut)
def choose_offer(payload: HeroChoiceIn, session: SessionDep) -> HeroOffersOut:
    """Choisit une offre, appliquée à l'intersaison (`index` à None : ne rien changer)."""
    _hero_or_404(session)
    hero_market.choose(session, payload.index)
    session.commit()
    return hero_market.offers_out(session)


@router.post("/agent", response_model=HeroOffersOut)
def set_agent(payload: HeroAgentIn, session: SessionDep) -> HeroOffersOut:
    """Change d'agent : plus d'offres et de meilleurs salaires, contre une commission."""
    _hero_or_404(session)
    hero_market.set_agent(session, payload.agent)
    session.commit()
    return hero_market.offers_out(session)


@router.get("/career", response_model=HeroCareerOut)
def get_career(session: SessionDep) -> HeroCareerOut:
    """Son palmarès : saison par saison, titres, trophées individuels, sélections."""
    _hero_or_404(session)
    return heroes.career_out(session)


@router.post("/retire", response_model=HeroCareerOut)
def retire(session: SessionDep) -> HeroCareerOut:
    """Il raccroche, au bilan d'une saison (celle de son championnat finie) : renvoie son
    bilan, puis la carrière s'arrête. Le monde continue : on peut y commencer une
    carrière d'entraîneur."""
    _hero_or_404(session)
    if not hero_market.season_finished(session):
        raise HTTPException(status_code=400, detail="On raccroche au bilan de la saison")
    career = heroes.retire(session, game_date(session))
    session.commit()
    return career
