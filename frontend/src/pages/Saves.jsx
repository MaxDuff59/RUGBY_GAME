import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { adminApi } from "../adminApi.js";
import { api } from "../api.js";
import { clubTheme } from "../clubs.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import { ActionError, PlanCard, newSaveBlocked } from "../components/FullGame.jsx";
import { formatLongDate, formatSavedAt } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { chooseSlot, leaveSlot } from "../save.js";

// Écran d'accueil : reprendre une des trois parties, ou en commencer une nouvelle
// dans un emplacement libre. Une partie se sauvegarde toute seule pendant le jeu.
export default function Saves() {
  const navigate = useNavigate();
  const me = useApi(useCallback(api.me, []));
  const saves = useApi(useCallback(api.listSaves, []));
  // Backoffice : adminApi.me répond 403 aux comptes qui ne sont pas admin (data reste null).
  const admin = useApi(useCallback(adminApi.me, []));
  const confirm = useConfirm();
  const [busy, setBusy] = useState(null); // emplacement en cours d'ouverture
  const [error, setError] = useState(null);
  // Retour de la page de paiement Stripe : ?paiement=ok&session_id=... ou ?paiement=annule.
  const [params, setParams] = useSearchParams();
  const [payment, setPayment] = useState(null); // { ok, text }
  const paid = params.get("paiement");
  const sessionId = params.get("session_id");
  const setMe = me.setData;

  useEffect(() => {
    if (!paid) return;
    setParams({}, { replace: true });
    if (paid !== "ok" || !sessionId) {
      setPayment({ ok: false, text: "Paiement annulé : rien n'a été débité." });
      return;
    }
    setPayment({ ok: true, text: "Confirmation du paiement…" });
    api
      .confirmPayment(sessionId)
      .then((user) => {
        setMe(user);
        setPayment({ ok: true, text: "Merci ! Le jeu complet est débloqué." });
      })
      .catch((err) => setPayment({ ok: false, text: err.message }));
  }, [paid, sessionId, setParams, setMe]);

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

  async function logout() {
    await api.logout();
    leaveSlot();
    navigate("/connexion", { replace: true });
  }

  if (saves.error?.status === 401) return <Navigate to="/connexion" replace />;
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
  const occupied = saves.data.filter((save) => !save.empty).length;
  // Compte gratuit : une partie, deux saisons en tout (components/FullGame.jsx).
  const blocked = newSaveBlocked(me.data, occupied);

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
        <div className="saves__account">
          {me.data && <span className="muted">{me.data.email}</span>}
          {admin.data && (
            <Link className="button" to="/backoffice">
              Backoffice
            </Link>
          )}
          <button type="button" className="button" disabled={busy !== null} onClick={logout}>
            Se déconnecter
          </button>
          <button
            type="button"
            className="button button--primary"
            disabled={!free || blocked !== null || busy !== null}
            title={blocked ?? (free ? undefined : "Supprime une partie pour en commencer une nouvelle")}
            onClick={() => create(free.slot)}
          >
            Nouvelle carrière
          </button>
        </div>
      </header>

      {me.data && <PlanCard me={me.data} saves={occupied} />}
      {payment && <p className={payment.ok ? "status" : "status--error"}>{payment.text}</p>}
      <ActionError error={error} />

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
                  <button
                    type="button"
                    className="button"
                    disabled={blocked !== null || busy !== null}
                    title={blocked ?? undefined}
                    onClick={() => create(save.slot)}
                  >
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
