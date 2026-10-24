import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useClubTheme } from "../clubs.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { ActionError } from "../components/FullGame.jsx";
import {
  DIFFICULTIES,
  formatLongDate,
  formatNote,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { chosenSlot } from "../save.js";

// Première page : on choisit son nom de manager, puis un club (un championnat, puis le
// club que l'on dirige) ou une sélection nationale. Après un départ (limogé, parti de
// soi-même, contrat échu), on y revient pour reprendre un club à sa portée.
// Comment s'est fini le dernier passage du manager (`dismissal.reason`).
const DEPARTURES = { dismissed: "Limogé", resigned: "Parti", expired: "Fin de contrat" };

export default function StartCareer() {
  const navigate = useNavigate();
  const { data: clubs, error, loading } = useApi(useCallback(api.listClubs, []));
  const leagues = useApi(useCallback(api.listLeagues, []));
  // Vide dans un monde de clubs inventés : pas de sélections à diriger.
  const nations = useApi(useCallback(api.listNations, []));
  const [kind, setKind] = useState("club"); // "club" ou "nation"
  const [nationCode, setNationCode] = useState(null);
  const [leagueCode, setLeagueCode] = useState(null);
  const { data: dismissal } = useApi(useCallback(api.getLastDismissal, []));
  const [managerName, setManagerName] = useState("");
  useEffect(() => {
    if (dismissal) setManagerName(dismissal.manager_name);
  }, [dismissal]);
  const [clubId, setClubId] = useState(null);
  // Aperçu : l'interface prend les couleurs du club (ou de la sélection) dès qu'on le choisit.
  const chosenName =
    kind === "nation"
      ? nations.data?.find((nation) => nation.code === nationCode)?.name
      : clubs?.find((club) => club.id === clubId)?.name;
  useClubTheme(chosenName);
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [difficulty, setDifficulty] = useState("normal");

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (kind === "nation") await api.startSelectorCareer(managerName.trim(), nationCode);
      else await api.startCareer(managerName.trim(), clubId, difficulty);
      navigate("/", { replace: true });
    } catch (err) {
      setSubmitError(err);
      setSubmitting(false);
    }
  }

  // Le club se choisit dans une partie : on passe d'abord par l'écran des parties.
  if (error?.status === 401) return <Navigate to="/connexion" replace />;
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

  const chosen = kind === "nation" ? nationCode !== null : clubId !== null;
  const canSubmit = managerName.trim() !== "" && chosen && !submitting;
  // Le même manager ne reprend qu'un club à sa portée ; un nouveau nom repart de zéro.
  const outOfReach = (id) =>
    dismissal?.reachable != null && managerName.trim() === dismissal.manager_name && !dismissal.reachable.includes(id);
  const hasNations = (nations.data?.length ?? 0) > 0;
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
            <Link to="/parties">Parties</Link> · {DEPARTURES[dismissal.reason]} le {formatLongDate(dismissal.date)}
          </p>
          <h1 className="title">Rebondis ailleurs</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            {dismissal.reason === "dismissed"
              ? `La direction de ${dismissal.club_name} a perdu confiance (${formatNote(dismissal.confidence)} / 20).`
              : dismissal.reason === "resigned"
                ? `Tu as quitté ${dismissal.club_name} avant la fin de ton contrat.`
                : `Ton contrat avec ${dismissal.club_name} s'est achevé.`}{" "}
            Le monde continue : choisis un club à ta portée, pas plus prestigieux que le dernier, à ta réputation près.
          </p>
        </div>
      ) : (
        <div>
          <p className="eyebrow">
            <Link to="/parties">Parties</Link> · Partie {chosenSlot()} · Nouvelle carrière
          </p>
          <h1 className="title">{kind === "nation" ? "Choisis ta sélection" : "Choisis ton club"}</h1>
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

      {hasNations && (
        <div className="chips" role="group" aria-label="Carrière">
          <button type="button" className="chip" aria-pressed={kind === "club"} onClick={() => setKind("club")}>
            Manager d'un club
          </button>
          <button type="button" className="chip" aria-pressed={kind === "nation"} onClick={() => setKind("nation")}>
            Sélectionneur national
          </button>
        </div>
      )}

      {kind === "club" && (
        <div className="field field--wide">
          <span className="field__label">Difficulté</span>
          <div className="chips" role="group" aria-label="Difficulté">
            {Object.entries(DIFFICULTIES).map(([key, level]) => (
              <button key={key} type="button" className="chip" aria-pressed={difficulty === key} onClick={() => setDifficulty(key)}>
                {level.label}
              </button>
            ))}
          </div>
          <span className="muted">{DIFFICULTIES[difficulty].scope} Les matchs, eux, ne changent pas.</span>
        </div>
      )}

      {kind === "nation" ? (
        <div className="section">
          <div className="section__head">
            <p className="eyebrow">Les sélections</p>
            <span className="muted">
              Pas de club à gérer : une liste de 42 joueurs à annoncer avant chaque rendez-vous, puis les matchs.
            </span>
          </div>
          <ul className="club-list">
            {nations.data.map((nation) => (
              <li key={nation.code}>
                <button
                  type="button"
                  className="club-option"
                  aria-pressed={nation.code === nationCode}
                  onClick={() => setNationCode(nation.code)}
                >
                  <span className="club-option__name with-crest">
                    <ClubCrest name={nation.name} size={32} />
                    {nation.name}
                  </span>
                  <span className="num">Niveau {formatNote(nation.level)} / 20</span>
                  <span className="club-option__detail">{nation.competitions.join(" · ")}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : league ? (
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
                    disabled={club.id === dismissal?.club_id || outOfReach(club.id)}
                    onClick={() => setClubId(club.id)}
                  >
                    <span className="club-option__name with-crest">
                      <ClubCrest name={club.name} size={32} />
                      {club.name}
                    </span>
                    <span className="num">
                      Niveau {formatNote(club.level)} / 20
                      {outOfReach(club.id) && club.id !== dismissal.club_id && " · hors de portée"}
                    </span>
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

      <ActionError error={submitError} />

      <div>
        <button type="submit" className="button button--primary" disabled={!canSubmit}>
          Prendre les rênes
        </button>
      </div>
    </form>
  );
}
