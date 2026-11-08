"""Des noms inventés qui sonnent juste pour chaque pays.

Un joueur inventé d'une nationalité connue ici prend un prénom et un nom de son pays
(data/generator.py) : un pilier américain ne s'appelle plus « Cyrian Ganquet ». Ce sont
des prénoms et des patronymes courants, combinés au hasard. La France (et un joueur sans
nationalité) garde les noms inventés du générateur.
"""

import random

# Prénoms, patronymes.
# fmt: off
_POOLS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "english": (
        ("Jack", "Tom", "Harry", "Oliver", "George", "Sam", "Ben", "Will", "Joe", "Luke",
         "Jamie", "Ryan", "Josh", "Matt", "Charlie", "Alex"),
        ("Smith", "Taylor", "Brown", "Walker", "Wright", "Green", "Hall", "Wood", "Harris",
         "Clarke", "Turner", "Hill", "Cooper", "Ward", "Baker", "Mitchell", "Carter", "Parker"),
    ),
    "welsh": (
        ("Rhys", "Dafydd", "Gareth", "Owen", "Huw", "Iwan", "Dylan", "Aled", "Gethin", "Rhodri"),
        ("Jones", "Williams", "Davies", "Evans", "Thomas", "Roberts", "Hughes", "Lewis", "Morgan",
         "Griffiths", "Price", "Powell", "Jenkins", "Lloyd"),
    ),
    "scottish": (
        ("Callum", "Fraser", "Ewan", "Angus", "Hamish", "Rory", "Finlay", "Euan", "Craig", "Ross"),
        ("Campbell", "Stewart", "MacDonald", "Murray", "Cameron", "Ross", "Fraser", "Robertson",
         "Graham", "Hamilton", "McLeod", "Sinclair", "Kerr"),
    ),
    "irish": (
        ("Conor", "Ciarán", "Seán", "Cian", "Darragh", "Oisín", "Pádraig", "Eoin", "Niall",
         "Rónán"),
        ("Murphy", "Kelly", "O'Brien", "Byrne", "Ryan", "O'Sullivan", "Doyle", "McCarthy", "Walsh",
         "O'Connor", "Gallagher", "Kennedy", "Brennan", "Quinn"),
    ),
    "afrikaans": (
        ("Pieter", "Johan", "Francois", "Ruan", "Jaco", "Wian", "Schalk", "Dewald", "Hendré",
         "Thabo", "Sipho", "Lwazi"),
        ("van der Merwe", "Botha", "du Toit", "Pretorius", "Venter", "Steyn", "du Plessis",
         "Nel", "Coetzee", "Fourie", "Mthembu", "Dlamini", "Nkosi", "Kruger"),
    ),
    "maori": (
        ("Tane", "Rawiri", "Wiremu", "Hemi", "Nikora", "Josh", "Sam", "Liam", "Cody", "Dane"),
        ("Ngata", "Tipene", "Walker", "Smith", "Parata", "Wilson", "Te Moana", "Henare",
         "Thompson", "Reid", "Hohaia", "Anderson"),
    ),
    "fijian": (
        ("Semi", "Waisea", "Josua", "Viliame", "Jiuta", "Peceli", "Isoa", "Mesake", "Kitione",
         "Eroni", "Sireli", "Apisalome"),
        ("Ravai", "Tuilau", "Vuniwai", "Nakarawa", "Rokoduru", "Matanavou", "Vakacegu",
         "Qerewaqa", "Bola", "Tuidraki", "Naqelevuki", "Waqaniburotu"),
    ),
    "polynesian": (
        ("Sione", "Tevita", "Siosaia", "Viliami", "Ioane", "Losaline", "Malakai", "Tasi",
         "Faleono", "Afa", "Pita", "Fonoti"),
        ("Fifita", "Tupou", "Taufa", "Vaipulu", "Leota", "Faasalele", "Tuilagi", "Lealamanua",
         "Mataele", "Havili", "Sapolu", "Fonua"),
    ),
    "spanish": (
        ("Mateo", "Santiago", "Joaquín", "Tomás", "Felipe", "Ignacio", "Gonzalo", "Nicolás",
         "Facundo", "Agustín", "Pablo", "Álvaro", "Diego", "Javier"),
        ("García", "Fernández", "González", "Rodríguez", "López", "Martínez", "Pérez", "Sánchez",
         "Romero", "Álvarez", "Díaz", "Torres", "Ruiz", "Castro", "Ortiz", "Silva"),
    ),
    "portuguese": (
        ("João", "Tiago", "Rodrigo", "Duarte", "Gonçalo", "Francisco", "Pedro", "Lucas", "Gabriel",
         "Rafael", "Bruno", "Vinícius"),
        ("Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues", "Martins",
         "Sousa", "Almeida", "Carvalho", "Lima", "Ribeiro", "Moreira"),
    ),
    "italian": (
        ("Marco", "Luca", "Alessandro", "Matteo", "Lorenzo", "Federico", "Giacomo", "Simone",
         "Tommaso", "Andrea", "Riccardo", "Niccolò"),
        ("Rossi", "Bianchi", "Ferrari", "Esposito", "Romano", "Colombo", "Ricci", "Marino",
         "Greco", "Bruno", "Gallo", "Conti", "Costa", "Mancini"),
    ),
    "georgian": (
        ("Giorgi", "Levan", "Lasha", "Beka", "Vasil", "Tornike", "Luka", "Davit", "Nika",
         "Shalva", "Mikheil", "Saba"),
        ("Beridze", "Kapanadze", "Lomidze", "Gogichashvili", "Maisuradze", "Abuladze",
         "Chkhaidze", "Tsiklauri", "Japaridze", "Gelashvili", "Kvaratskhelia", "Nadiradze"),
    ),
    "romanian": (
        ("Andrei", "Mihai", "Ionuț", "Alexandru", "Florin", "Cristian", "Vlad", "Marius",
         "Răzvan", "Bogdan", "Ștefan", "Adrian"),
        ("Popescu", "Ionescu", "Stan", "Dumitru", "Constantin", "Gheorghe", "Radu", "Munteanu",
         "Matei", "Lazăr", "Neagu", "Tudor"),
    ),
    "dutch": (
        ("Daan", "Bram", "Sem", "Thijs", "Lars", "Ruben", "Jesse", "Stijn", "Koen", "Wout",
         "Pieter", "Joris"),
        ("de Jong", "Jansen", "de Vries", "van den Berg", "Bakker", "Visser", "Smit", "Meijer",
         "Mulder", "Peeters", "Maes", "Janssens", "Claes", "Wouters"),
    ),
    "german": (
        ("Lukas", "Jonas", "Felix", "Leon", "Niklas", "Tobias", "Florian", "Moritz", "Fabian",
         "Jannik", "Nico", "Simon"),
        ("Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Wagner", "Becker", "Hoffmann",
         "Keller", "Huber", "Meier", "Brunner", "Zimmermann", "Graf"),
    ),
    "japanese": (
        ("Takuya", "Kenta", "Shota", "Yuto", "Ryota", "Daiki", "Kazuki", "Naoto", "Haruto",
         "Sho", "Kotaro", "Yusuke"),
        ("Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura",
         "Kobayashi", "Kato", "Yoshida", "Matsuda", "Inoue", "Kimura"),
    ),
    "korean": (
        ("Min-jun", "Seo-jun", "Ji-ho", "Hyun-woo", "Jun-young", "Dong-hyun", "Sung-min",
         "Tae-yang", "Woo-jin", "Jae-won"),
        ("Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim", "Han", "Shin"),
    ),
    "hong_kong": (
        ("Ka-ho", "Chun-yin", "Wai-lun", "Max", "Ben", "Jamie", "Callum", "Tom", "Kwan", "Hugo"),
        ("Chan", "Wong", "Leung", "Cheung", "Lau", "Ng", "Lee", "Ho", "Fenn", "Rowe", "Ellis",
         "Hamilton"),
    ),
    "sri_lankan": (
        ("Kasun", "Dilshan", "Nuwan", "Tharindu", "Chamara", "Sachith", "Isuru", "Ravindu",
         "Kavindu", "Danushka"),
        ("Perera", "Fernando", "Silva", "Jayasuriya", "Wickramasinghe", "Bandara", "Dissanayake",
         "Gunawardena", "Rajapaksa", "Senanayake"),
    ),
    "arabic": (
        ("Karim", "Yacine", "Mehdi", "Sofiane", "Amine", "Bilal", "Rayan", "Nassim", "Omar",
         "Ali", "Hamza", "Ilyes"),
        ("Benali", "Haddad", "Mansouri", "Bouzid", "Saidi", "Belkacem", "Cherif", "Hamdi",
         "Al Mansoori", "Al Hashimi", "Khalil", "Rahmani"),
    ),
    "kenyan": (
        ("Brian", "Collins", "Dennis", "Kevin", "Samuel", "Daniel", "Felix", "Vincent", "Alvin",
         "George"),
        ("Odhiambo", "Otieno", "Kamau", "Wanjala", "Ochieng", "Mwangi", "Kiprono", "Njoroge",
         "Omondi", "Wekesa", "Kariuki", "Onyango"),
    ),
    "zimbabwean": (
        ("Tinotenda", "Tafadzwa", "Tendai", "Kudakwashe", "Brandon", "Takudzwa", "Simbarashe",
         "Ian", "Hilton", "Liam"),
        ("Moyo", "Ncube", "Dube", "Sibanda", "Chikwanha", "Mupfurutsa", "Nyakane", "Mudariki",
         "Gumbo", "Mutasa", "Chirwa", "Maposa"),
    ),
}
# fmt: on

CULTURE_OF = {
    "ENG": "english", "AUS": "english", "USA": "english", "CAN": "english",
    "WAL": "welsh", "SCO": "scottish", "IRE": "irish", "NZL": "maori",
    "RSA": "afrikaans", "NAM": "afrikaans", "ZIM": "zimbabwean", "KEN": "kenyan",
    "FIJ": "fijian", "SAM": "polynesian", "TON": "polynesian",
    "ARG": "spanish", "ESP": "spanish", "URU": "spanish", "CHI": "spanish", "PAR": "spanish",
    "POR": "portuguese", "BRA": "portuguese", "ITA": "italian", "GEO": "georgian",
    "ROU": "romanian", "NED": "dutch", "BEL": "dutch", "GER": "german", "SUI": "german",
    "JPN": "japanese", "KOR": "korean", "HKG": "hong_kong", "SRI": "sri_lankan",
    "UAE": "arabic", "ALG": "arabic",
}  # fmt: skip


def local_name(nationality: str | None, player_id: int) -> tuple[str, str] | None:
    """Un prénom et un nom du pays (None : on garde ceux du générateur). Toujours les mêmes
    pour un même joueur, sans toucher au hasard de la partie."""
    culture = CULTURE_OF.get(nationality or "")
    if culture is None:
        return None
    first_names, last_names = _POOLS[culture]
    rng = random.Random(f"name-{nationality}-{player_id}")
    return rng.choice(first_names), rng.choice(last_names)
