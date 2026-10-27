import { useCallback, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useClubTheme } from "../clubs.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { ActionError } from "../components/FullGame.jsx";
import { DIFFICULTIES } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { chosenSlot } from "../save.js";

// Les deux compétitions qu'on peut jouer seules (api/competition.py).
const COMPETITIONS = [
  {
    code: "champions_cup",
    name: "Coupe d'Europe",
    detail: "24 clubs : les huit meilleurs du Top 14, de la Premiership et de l'URC. Poules, puis quarts, demies et finale.",
  },
  {
    code: "world_cup",
    name: "Coupe du monde",
    detail: "16 nations, invitées comprises. Quatre poules de quatre, puis quarts, demies et finale.",
  },
];

// Nouvelle partie en mode compétition : d'abord la compétition (la saison se tire, et
// avec elle les qualifiés), puis le nom du manager et l'équipe parmi les participants.
// La partie s'arrête au titre ou à l'élimination.
export default function StartCompetition() {
  const navigate = useNavigate();
  const competition = useApi(useCallback(api.getCompetition, []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [managerName, setManagerName] = useState("");
  const [teamId, setTeamId] = useState(null);
  const [difficulty, setDifficulty] = useState("normal");
  const chosen = competition.data?.teams.find((team) => team.id === teamId);
  useClubTheme(chosen?.name);

  if (competition.error?.status === 401) return <Navigate to="/connexion" replace />;
  if (chosenSlot() === null || competition.error?.status === 409) return <Navigate to="/parties" replace />;
  if (competition.loading) return <p className="status">Chargement…</p>;
  if (competition.error && competition.error.status !== 404) {
    return <p className="status status--error">{competition.error.message}</p>;
  }
  if (competition.data?.team) return <Navigate to="/" replace />;

  async function choose(code) {
    setBusy(true);
    setError(null);
    try {
      competition.setData(await api.chooseCompetition(code));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.chooseCompetitionTeam(managerName.trim(), teamId, difficulty);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const crumbs = (
    <p className="eyebrow">
      <Link to="/parties">Parties</Link> · Partie {chosenSlot()} · Mode compétition
    </p>
  );

  // Première étape : la compétition.
  if (!competition.data) {
    return (
      <div className="start start--career">
        <div>
          {crumbs}
          <h1 className="title">Choisis ta compétition</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Tu gères ton équipe de bout en bout ; la partie s'arrête au titre ou à l'élimination.
          </p>
        </div>
        <ActionError error={error} />
        <div className="section">
          <div className="club-list__scroll">
            <ul className="club-list">
              {COMPETITIONS.map((item) => (
                <li key={item.code}>
                  <button type="button" className="club-option" disabled={busy} onClick={() => choose(item.code)}>
                    <span className="club-option__name">{item.name}</span>
                    <span className="club-option__detail">{item.detail}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
        {busy && <p className="status">Tirage de la saison…</p>}
      </div>
    );
  }

  // Deuxième étape : le manager et son équipe.
  const club = competition.data.code === "champions_cup";
  const canSubmit = managerName.trim() !== "" && teamId !== null && !busy;
  return (
    <form className="start start--career" onSubmit={handleSubmit}>
      <div>
        {crumbs}
        <h1 className="title">{club ? "Choisis ton club" : "Choisis ta sélection"}</h1>
      </div>

      <div className="field">
        <label htmlFor="manager">Ton nom de manager</label>
        <input
          id="manager"
          className="input"
          value={managerName}
          onChange={(event) => setManagerName(event.target.value)}
          autoComplete="name"
          required
        />
      </div>

      {club && (
        <div className="field field--wide">
          <span className="field__label">Difficulté</span>
          <div className="chips" role="group" aria-label="Difficulté">
            {Object.entries(DIFFICULTIES).map(([key, level]) => (
              <button key={key} type="button" className="chip" aria-pressed={difficulty === key} onClick={() => setDifficulty(key)}>
                {level.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="section">
        <div className="section__head">
          <p className="eyebrow">
            {competition.data.name} · {competition.data.teams.length} {club ? "clubs qualifiés" : "nations"}
          </p>
        </div>
        <div className="club-list__scroll">
          <ul className="club-list">
            {competition.data.teams.map((team) => (
              <li key={team.id}>
                <button
                  type="button"
                  className="club-option"
                  aria-pressed={team.id === teamId}
                  onClick={() => setTeamId(team.id)}
                >
                  <span className="club-option__name with-crest">
                    <ClubCrest name={team.name} size={32} />
                    {team.name}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <ActionError error={error} />

      <div className="start__submit">
        <button type="submit" className="button button--primary" disabled={!canSubmit}>
          {busy ? "Un instant…" : "Prendre les rênes"}
        </button>
      </div>
    </form>
  );
}
