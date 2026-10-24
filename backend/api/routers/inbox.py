"""La boîte « à traiter » : ce qui attend une décision du manager, page par page.

Rien n'y est stocké : chaque élément se relit dans l'état du jeu (une affaire sans
réponse, un blessé sans protocole, une négociation ouverte, des fins de contrat...),
et disparaît dès que le manager l'a réglé.
"""

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import careers
from api.affairs import affair_out, pending_affairs
from api.deps import SessionDep, load_my_club_row
from api.ledger import current_season, game_date
from api.routers.contracts import contracts_overview
from api.routers.seasons import _phase, focus_league
from api.schemas import InboxItemOut, InboxOut
from engine.regulations import cap_room
from models.orm import ClubRow, InjuryRow, NegotiationRow, PlayerRow


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count > 1 else ''}"


router = APIRouter(prefix="/inbox", tags=["à traiter"])


def _items(session: Session, me: ClubRow) -> list[InboxItemOut]:
    items: list[InboxItemOut] = []
    day = game_date(session)
    season = current_season(session)
    finished = season is not None and _phase(season, focus_league(session)) == "finished"

    for affair in pending_affairs(session, me.id):
        items.append(
            InboxItemOut(
                kind="affair",
                title=affair_out(affair).title,
                detail="Une affaire attend ta réponse avant la prochaine journée.",
                link="/",
                urgent=True,
            )
        )

    undecided = session.scalars(
        select(InjuryRow)
        .join(PlayerRow, InjuryRow.player_id == PlayerRow.id)
        .where(
            PlayerRow.club_id == me.id,
            InjuryRow.protocol_chosen.is_(False),
            InjuryRow.return_date > day,
        )
    ).all()
    if undecided:
        names = ", ".join(f"{i.player.first_name} {i.player.last_name}" for i in undecided)
        items.append(
            InboxItemOut(
                kind="medical",
                title=f"{_plural(len(undecided), 'blessé')} sans protocole",
                detail=f"Choisis leur protocole de soins : {names}.",
                link="/medical",
                urgent=True,
            )
        )

    talks = session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == me.id, NegotiationRow.stage.in_(("club", "player"))
        )
    ).all()
    for talk in talks:
        player = talk.player
        waiting = "son club" if talk.stage == "club" else "le joueur"
        items.append(
            InboxItemOut(
                kind="transfer",
                title=f"Négociation : {player.first_name} {player.last_name}",
                detail=f"À toi de faire une offre à {waiting}.",
                link="/transferts",
            )
        )

    suspended = [p for p in me.players if p.suspended_matches > 0]
    if suspended:
        names = ", ".join(f"{p.first_name} {p.last_name}" for p in suspended)
        items.append(
            InboxItemOut(
                kind="discipline",
                title=f"{_plural(len(suspended), 'suspendu')}",
                detail=f"Ils ne peuvent pas jouer : {names}.",
                link="/effectif",
            )
        )

    room = cap_room(me.to_domain())
    if room is not None and room < 0:
        items.append(
            InboxItemOut(
                kind="finances",
                title="Plafond salarial dépassé",
                detail="Ta masse salariale dépasse le plafond : vends avant de signer.",
                link="/transferts",
                urgent=True,
            )
        )

    if season is not None:
        contracts = contracts_overview(session, me)
        open_pros = [c for c in contracts.pros if c.status == "open"]
        leaving = [c for c in contracts.youths if c.status == "leaving_academy"]
        if open_pros:
            items.append(
                InboxItemOut(
                    kind="contract",
                    title=f"{_plural(len(open_pros), 'contrat')} en fin de course",
                    detail="Prolonge ceux que tu veux garder, sinon ils partent libres.",
                    link="/" if finished else "/transferts",
                    urgent=finished,
                )
            )
        if leaving:
            items.append(
                InboxItemOut(
                    kind="academy",
                    title=f"{_plural(len(leaving), 'espoir')} à faire passer pro",
                    detail="Trop âgés pour le centre : promeus-les ou ils partent.",
                    link="/formation",
                )
            )
        if finished and contracts.squad_next < contracts.squad_min:
            items.append(
                InboxItemOut(
                    kind="contract",
                    title="Effectif insuffisant pour la saison prochaine",
                    detail=(
                        f"{contracts.squad_next} pros sous contrat, il en faut "
                        f"{contracts.squad_min} pour lancer la saison."
                    ),
                    link="/",
                    urgent=True,
                )
            )

    if finished:
        offers = careers.offers(session)
        if offers:
            names = ", ".join(session.get(ClubRow, club_id).name for club_id in offers)
            items.append(
                InboxItemOut(
                    kind="career",
                    title=f"{_plural(len(offers), 'offre')} pour toi",
                    detail=f"Ils veulent te confier leur équipe : {names}. Voir le bilan.",
                    link="/",
                )
            )
    return items


@router.get("", response_model=InboxOut)
def get_inbox(session: SessionDep) -> InboxOut:
    """Ce qui attend une décision du manager, le plus pressant d'abord."""
    me = load_my_club_row(session)
    items = _items(session, me)
    items.sort(key=lambda item: not item.urgent)
    return InboxOut(items=items)
