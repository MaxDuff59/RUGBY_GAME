import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { clubTheme } from "../clubs.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import { formatLongDate, formatSavedAt } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { chooseSlot } from "../save.js";

// Écran d'accueil : reprendre une des trois parties, ou en commencer une nouvelle
// dans un emplacement libre. Une partie se sauvegarde toute seule pendant le jeu.
export default function Saves() {
  const navigate = useNavigate();
  const saves = useApi(useCallback(api.listSaves, []));
  const confirm = useConfirm();
  const [busy, setBusy] = useState(null); // emplacement en cours d'ouverture
  const [error, setError] = useState(null);

  async function open(slot, call, next) {
    setBusy(slot);
    setError(null);
    try {
      const save = await call(slot);
      chooseSlot(slot);
      navigate(next(save));
    } catch (err) {
      setError(err);
      setBusy(null);
    }
  }

  const resume = (save) => open(save.slot, api.loadSave, (loaded) => (loaded.manager_name ? "/" : "/start"));
  const create = (slot) => open(slot, api.newSave, () => "/start");

  const remove = (save) =>
    confirm.ask({
      eyebrow: `Partie ${save.slot}`,
      title: save.club_name ? `Supprimer ${save.club_name}` : "Supprimer la partie",
      text: "La partie est effacée pour de bon : son monde, ses saisons et sa carrière.",
      confirmLabel: "Supprimer",
      onConfirm: async () => saves.setData(await api.deleteSave(save.slot)),
    });

  if (saves.loading) return <p className="status">Chargement des parties…</p>;
  if (saves.error) {
    return (
      <p className="status status--error">
        Impossible de joindre l'API ({saves.error.message}). Lance-la avec
        <code> uv run uvicorn api.main:app --reload</code> dans backend/.
      </p>
    );
  }

  const free = saves.data.find((save) => save.empty);

  return (
    <div className="start">
      {confirm.dialog}
      <header className="page-head">
        <div>
          <p className="eyebrow">Rugby Manager</p>
          <h1 className="title">Tes parties</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Trois emplacements. Une partie se sauvegarde automatiquement à chaque action.
          </p>
        </div>
        <button
          type="button"
          className="button button--primary"
          disabled={!free || busy !== null}
          title={free ? undefined : "Supprime une partie pour en commencer une nouvelle"}
          onClick={() => create(free.slot)}
        >
          Nouvelle carrière
        </button>
      </header>

      {error && <p className="status--error">{error.message}</p>}

      <ul className="saves">
        {saves.data.map((save) => (
          <li
            key={save.slot}
            className={`card card--padded save${save.empty ? " save--empty" : ""}`}
            // Chaque partie à l'accent de son club (bouton « Continuer »).
            style={save.club_name && !save.outdated ? { "--accent": clubTheme(save.club_name).accent } : undefined}
          >
            <p className="eyebrow">
              Partie {save.slot}
              {save.active && !save.empty && " · dernière jouée"}
            </p>
            {save.empty ? (
              <>
                <p className="save__club muted">Emplacement libre</p>
                <div className="save__actions">
                  <button type="button" className="button" disabled={busy !== null} onClick={() => create(save.slot)}>
                    {busy === save.slot ? "Création du monde…" : "Nouvelle carrière"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="save__club with-crest">
                  {save.club_name && !save.outdated && <ClubCrest name={save.club_name} size={36} />}
                  {save.outdated ? "Ancien format" : (save.club_name ?? "Carrière à choisir")}
                </p>
                <div className="save__details">
                  {save.outdated ? (
                    <span className="muted">Cette partie ne s'ouvre plus avec cette version du jeu.</span>
                  ) : (
                    <>
                      {save.manager_name && (
                        <span>
                          {save.manager_name} · {save.league_name}
                        </span>
                      )}
                      {save.season_year && (
                        <span className="muted">
                          Saison {save.season_year}-{String(save.season_year + 1).slice(2)} ·{" "}
                          {formatLongDate(save.game_date)}
                        </span>
                      )}
                    </>
                  )}
                  <span className="muted">Sauvegardée {formatSavedAt(save.saved_at)}</span>
                </div>
                <div className="save__actions">
                  {!save.outdated && (
                    <button
                      type="button"
                      className="button button--primary"
                      disabled={busy !== null}
                      onClick={() => resume(save)}
                    >
                      {busy === save.slot ? "Chargement…" : "Continuer"}
                    </button>
                  )}
                  <button type="button" className="button" disabled={busy !== null} onClick={() => remove(save)}>
                    Supprimer
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
