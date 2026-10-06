import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useClubTheme } from "../clubs.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { formatLongDate, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { chosenSlot } from "../save.js";

// Première page : on choisit son nom de manager, un championnat, puis le club que
// l'on dirige. Après un limogeage, on y revient pour reprendre un autre club.
export default function StartCareer() {
  const navigate = useNavigate();
  const { data: clubs, error, loading } = useApi(useCallback(api.listClubs, []));
  const leagues = useApi(useCallback(api.listLeagues, []));
  const [leagueCode, setLeagueCode] = useState(null);
  const { data: dismissal } = useApi(useCallback(api.getLastDismissal, []));
  const [managerName, setManagerName] = useState("");
  useEffect(() => {
    if (dismissal) setManagerName(dismissal.manager_name);
  }, [dismissal]);
  const [clubId, setClubId] = useState(null);
  // Aperçu : l'interface prend les couleurs du club dès qu'on le sélectionne.
  useClubTheme(clubs?.find((club) => club.id === clubId)?.name);
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.startCareer(managerName.trim(), clubId);
      navigate("/", { replace: true });
    } catch (err) {
      setSubmitError(err);
      setSubmitting(false);
    }
  }

  // Le club se choisit dans une partie : on passe d'abord par l'écran des parties.
  if (chosenSlot() === null || error?.status === 409) return <Navigate to="/parties" replace />;
  if (loading || leagues.loading) return <p className="status">Chargement des clubs…</p>;
  if (error || leagues.error) {
    return (
      <p className="status status--error">
        Impossible de joindre l'API ({(error ?? leagues.error).message}). Lance-la avec
        <code> uv run uvicorn api.main:app --reload</code> dans backend/.
      </p>
    );
  }

  const canSubmit = managerName.trim() !== "" && clubId !== null && !submitting;
  // Un seul championnat (monde inventé) : on passe directement aux clubs.
  const league =
    leagues.data.length === 1 ? leagues.data[0] : leagues.data.find((l) => l.code === leagueCode);
  const pickLeague = (code) => {
    setLeagueCode(code);
    setClubId(null);
  };

  return (
    <form className="start" onSubmit={handleSubmit}>
      {dismissal ? (
        <div>
          <p className="eyebrow">
            <Link to="/parties">Parties</Link> · Limogé le {formatLongDate(dismissal.date)}
          </p>
          <h1 className="title">Rebondis ailleurs</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            La direction de {dismissal.club_name} a perdu confiance ({formatNote(dismissal.confidence)} / 20). Le
            monde continue : choisis un autre club, dans le championnat de ton choix.
          </p>
        </div>
      ) : (
        <div>
          <p className="eyebrow">
            <Link to="/parties">Parties</Link> · Partie {chosenSlot()} · Nouvelle carrière
          </p>
          <h1 className="title">Choisis ton club</h1>
        </div>
      )}

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

      {league ? (
        <div className="section">
          <div className="section__head">
            <p className="eyebrow">Les clubs · {league.name}</p>
            {leagues.data.length > 1 && (
              <button type="button" className="button button--small" onClick={() => pickLeague(null)}>
                ← Changer de championnat
              </button>
            )}
          </div>
          <ul className="club-list">
            {clubs
              .filter((club) => club.league === league.code)
              .map((club) => (
                <li key={club.id}>
                  <button
                    type="button"
                    className="club-option"
                    aria-pressed={club.id === clubId}
                    disabled={club.id === dismissal?.club_id}
                    onClick={() => setClubId(club.id)}
                  >
                    <span className="club-option__name with-crest">
                      <ClubCrest name={club.name} size={32} />
                      {club.name}
                    </span>
                    <span className="num">Niveau {formatNote(club.level)} / 20</span>
                  </button>
                </li>
              ))}
          </ul>
        </div>
      ) : (
        <div className="section">
          <p className="eyebrow">D'abord, le championnat</p>
          <ul className="club-list">
            {leagues.data.map((item) => (
              <li key={item.code}>
                <button type="button" className="club-option" onClick={() => pickLeague(item.code)}>
                  <span className="club-option__name">{item.name}</span>
                  <span className="muted">{item.country}</span>
                  <span className="num">{item.club_count} clubs</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {submitError && <p className="status--error">{submitError.message}</p>}

      <div>
        <button type="submit" className="button button--primary" disabled={!canSubmit}>
          Prendre les rênes
        </button>
      </div>
    </form>
  );
}
