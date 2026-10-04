"""Les 14 clubs du Top 14 (saison 2025-26), avec leur stade et leur poids.

Seuls les clubs sont réels : les joueurs et le staff restent inventés par le
générateur. `level` est le niveau sportif visé (sur 20, comme les attributs) ;
`wealth` dose l'argent et le staff (0 = club modeste, 1 = gros budget).
Les capacités sont arrondies.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RealClub:
    name: str
    city: str
    stadium: str
    capacity: int
    level: float
    wealth: float


TOP14 = [
    RealClub("Stade Toulousain", "Toulouse", "Stade Ernest-Wallon", 19_000, 14.0, 1.0),
    RealClub("Union Bordeaux-Bègles", "Bordeaux", "Stade Chaban-Delmas", 33_000, 13.5, 0.85),
    RealClub("RC Toulon", "Toulon", "Stade Mayol", 16_000, 12.5, 0.8),
    RealClub("Stade Rochelais", "La Rochelle", "Stade Marcel-Deflandre", 16_000, 12.5, 0.75),
    RealClub(
        "ASM Clermont Auvergne", "Clermont-Ferrand", "Stade Marcel-Michelin", 19_000, 12.0, 0.7
    ),
    RealClub("Racing 92", "Nanterre", "Paris La Défense Arena", 30_000, 11.5, 0.85),
    RealClub("Aviron Bayonnais", "Bayonne", "Stade Jean-Dauger", 17_000, 11.5, 0.55),
    RealClub("Castres Olympique", "Castres", "Stade Pierre-Fabre", 12_500, 11.5, 0.5),
    RealClub("Section Paloise", "Pau", "Stade du Hameau", 18_000, 11.0, 0.55),
    RealClub("Stade Français Paris", "Paris", "Stade Jean-Bouin", 20_000, 10.5, 0.75),
    RealClub("LOU Rugby", "Lyon", "Matmut Stadium de Gerland", 25_000, 10.5, 0.65),
    RealClub("Montpellier Hérault Rugby", "Montpellier", "GGL Stadium", 15_500, 10.5, 0.65),
    RealClub("USA Perpignan", "Perpignan", "Stade Aimé-Giral", 14_500, 10.0, 0.45),
    RealClub("US Montauban", "Montauban", "Stade Sapiac", 11_000, 8.5, 0.2),
]
