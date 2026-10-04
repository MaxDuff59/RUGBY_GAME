"""Marché des transferts, du point de vue du club dirigé par le joueur.

Les clubs IA vendent au prix demandé et rachètent à la valeur marchande.
La fenêtre est toujours ouverte pour l'instant (elle se fermera avec le jeu
journée par journée).
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.ledger import game_date, record
from api.schemas import ListingOut, PlayerOut, TransfersOverview
from engine.economy import SQUAD_MAX, SQUAD_MIN, TransactionCategory, asking_price, sale_price
from models.orm import ClubRow, PlayerRow

router = APIRouter(prefix="/transfers", tags=["transferts"])


def _overview(session: Session, club: ClubRow) -> TransfersOverview:
    others = session.scalars(
        select(PlayerRow).where(PlayerRow.club_id.is_not(None), PlayerRow.club_id != club.id)
    )
    day = game_date(session)
    listings = []
    for row in others:
        player = row.to_domain()
        price = asking_price(player)
        listings.append(
            ListingOut(
                player=PlayerOut.from_player(player, day),
                club_id=row.club_id,
                club_name=row.club.name,
                asking_price=price,
                affordable=club.balance >= price,
            )
        )
    listings.sort(key=lambda listing: listing.player.value, reverse=True)
    return TransfersOverview(
        balance=club.balance,
        squad_size=len(club.players),
        squad_min=SQUAD_MIN,
        squad_max=SQUAD_MAX,
        listings=listings,
    )


@router.get("", response_model=TransfersOverview)
def get_market(session: SessionDep) -> TransfersOverview:
    """Joueurs des autres clubs, avec leur prix demandé."""
    return _overview(session, load_my_club_row(session))


@router.post("/buy/{player_id}", response_model=TransfersOverview)
def buy(player_id: int, session: SessionDep) -> TransfersOverview:
    """Achète un joueur d'un autre club au prix demandé."""
    club = load_my_club_row(session)
    row = session.get(PlayerRow, player_id)
    if row is None or row.club_id is None or row.club_id == club.id:
        raise HTTPException(status_code=404, detail="Joueur introuvable sur le marché")
    if len(club.players) >= SQUAD_MAX:
        raise HTTPException(status_code=400, detail=f"Effectif complet ({SQUAD_MAX} joueurs)")

    price = asking_price(row.to_domain())
    if club.balance < price:
        raise HTTPException(status_code=400, detail="Trésorerie insuffisante")

    seller, day, name = row.club, game_date(session), f"{row.first_name} {row.last_name}"
    record(
        session, club, TransactionCategory.TRANSFER, f"Achat · {name} ({seller.name})", -price, day
    )
    record(
        session, seller, TransactionCategory.TRANSFER, f"Vente · {name} ({club.name})", price, day
    )
    row.club_id = club.id
    session.commit()
    session.refresh(club)
    return _overview(session, club)


@router.post("/sell/{player_id}", response_model=TransfersOverview)
def sell(player_id: int, session: SessionDep) -> TransfersOverview:
    """Vend un de ses joueurs à sa valeur marchande, au club IA le moins fourni."""
    club = load_my_club_row(session)
    row = session.get(PlayerRow, player_id)
    if row is None or row.club_id != club.id:
        raise HTTPException(status_code=404, detail="Ce joueur n'est pas dans ton effectif")
    if len(club.players) <= SQUAD_MIN:
        raise HTTPException(
            status_code=400, detail=f"Effectif minimum atteint ({SQUAD_MIN} joueurs)"
        )

    buyers = [
        c
        for c in session.scalars(select(ClubRow))
        if c.id != club.id and len(c.players) < SQUAD_MAX
    ]
    if not buyers:
        raise HTTPException(status_code=400, detail="Aucun club n'a de place dans son effectif")
    buyer = min(buyers, key=lambda c: len(c.players))

    price = sale_price(row.to_domain())
    day, name = game_date(session), f"{row.first_name} {row.last_name}"
    record(
        session, club, TransactionCategory.TRANSFER, f"Vente · {name} ({buyer.name})", price, day
    )
    record(
        session, buyer, TransactionCategory.TRANSFER, f"Achat · {name} ({club.name})", -price, day
    )
    row.club_id = buyer.id
    session.commit()
    session.refresh(club)
    return _overview(session, club)
