import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";

// Première page : on choisit son nom de manager et le club que l'on dirige.
export default function StartCareer() {
  const navigate = useNavigate();
  const { data: clubs, error, loading } = useApi(useCallback(api.listClubs, []));
  const [managerName, setManagerName] = useState("");
  const [clubId, setClubId] = useState(null);
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

  if (loading) return <p className="status">Chargement des clubs…</p>;
  if (error) {
    return (
      <p className="status status--error">
        Impossible de joindre l'API ({error.message}). Lance-la avec
        <code> uv run uvicorn api.main:app --reload</code> dans backend/.
      </p>
    );
  }

  const canSubmit = managerName.trim() !== "" && clubId !== null && !submitting;

  return (
    <form className="start" onSubmit={handleSubmit}>
      <div>
        <p className="eyebrow">Nouvelle carrière</p>
        <h1 className="title">Choisis ton club</h1>
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

      <div className="section">
        <p className="eyebrow">Les clubs du championnat</p>
        <ul className="club-list">
          {clubs.map((club) => (
            <li key={club.id}>
              <button
                type="button"
                className="club-option"
                aria-pressed={club.id === clubId}
                onClick={() => setClubId(club.id)}
              >
                <span className="club-option__name">{club.name}</span>
                <span className="num">Niveau {formatNote(club.level)} / 20</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {submitError && <p className="status--error">{submitError.message}</p>}

      <div>
        <button type="submit" className="button button--primary" disabled={!canSubmit}>
          Prendre les rênes
        </button>
      </div>
    </form>
  );
}
