# Frontend (React + Vite)

Interface du jeu. Elle consomme l'API FastAPI du dossier `backend/`.
La direction visuelle est décrite dans [DESIGN.md](DESIGN.md).

## Lancer

Il faut deux terminaux : l'API, puis l'interface.

```bash
# Terminal 1 — l'API (depuis backend/)
uv run uvicorn api.main:app --reload

# Terminal 2 — l'interface (depuis frontend/)
npm install        # la première fois seulement
npm run dev        # puis ouvrir http://localhost:5173
```

En développement, Vite relaie les appels `/api/...` vers `http://localhost:8000`
(voir `vite.config.js`) : le navigateur ne parle qu'à un seul serveur, donc
pas de configuration CORS.

## Organisation

```
src/
  main.jsx            point d'entrée (React + routeur)
  App.jsx             les routes
  api.js              appels à l'API (une fonction par route)
  format.js           libellés des postes, attributs, formats de nombres
  styles.css          styles globaux (variables de DESIGN.md)
  hooks/useApi.js     charge une ressource de l'API : { data, error, loading, reload, setData }
  hooks/useSort.js    tri d'un tableau par colonne (avec components/SortHeader.jsx)
  components/
    Layout.jsx        navigation + en-tête, charge la carrière en cours
    Level.jsx         niveau de 1 à 5 en petits carrés
    SortHeader.jsx    en-tête de colonne cliquable
    FormPills.jsx     derniers résultats en pastilles V / N / D
    MatchList.jsx     affiches d'une journée avec leur score
  pages/
    StartCareer.jsx   choisir son nom et son club (première visite)
    Club.jsx          tableau de bord : prochain match, simuler la journée, rapport de
                      force, classement, derniers résultats, phases finales
    Calendar.jsx      calendrier de la saison : vues semaine, mois, saison
    Squad.jsx         XV de départ sur le terrain + attributs de tout l'effectif (blessés signalés)
    Medical.jsx       infirmerie : blessés et choix du protocole de soins, joueurs fragiles,
                      staff médical, dossier médical
    Staff.jsx         ton staff (8 postes), licencier, embaucher parmi les candidats
    Transfers.jsx     acheter chez les autres clubs, vendre ses joueurs
    Facilities.jsx    stade, centre d'entraînement, centre de formation
    Finances.jsx      trésorerie, masse salariale, et toutes les opérations (grand livre)
```

Pas de TypeScript ni de bibliothèque de composants : du JavaScript, du CSS
simple, et `react-router-dom` pour les pages.
