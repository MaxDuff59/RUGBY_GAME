import { useState } from "react";

import { api } from "../api.js";

// Jeu complet : 2 €, une fois, par Stripe (backend/api/billing.py). Le compte gratuit
// garde une partie et joue deux saisons en tout, supprimées comprises.
export const PRICE_LABEL = "2 €";
// Réponse de l'API quand c'est la formule gratuite qui bloque (backend/api/plans.py).
export const PAYMENT_REQUIRED = 402;

// Part vers la page de paiement Stripe ; le retour se fait sur /parties.
export function UnlockButton({ label = `Débloquer le jeu complet · ${PRICE_LABEL}` }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function checkout() {
    setBusy(true);
    setError(null);
    try {
      const { url } = await api.checkout();
      window.location.assign(url);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="button button--primary" disabled={busy} onClick={checkout}>
        {busy ? "Ouverture du paiement…" : label}
      </button>
      {error && <p className="status--error full-game__error">{error.message}</p>}
    </>
  );
}

// Le refus d'une action : son message, et l'offre du jeu complet quand c'est la
// formule gratuite qui bloque.
export function ActionError({ error, className = "status--error" }) {
  if (!error) return null;
  if (error.status !== PAYMENT_REQUIRED) return <p className={className}>{error.message}</p>;
  return (
    <div className="full-game full-game--inline">
      <p className="full-game__text">{error.message}</p>
      <UnlockButton />
    </div>
  );
}

// Ce que le compte peut encore faire (écran des parties). `saves` : parties occupées.
// Rien quand la formule est en pause (`paywall`, backend/api/plans.py) : tout est gratuit.
export function PlanCard({ me, saves }) {
  if (!me.paywall) return null;
  if (me.premium) {
    return (
      <p className="full-game full-game--done">
        <span className="eyebrow">Jeu complet</span>
        <span className="muted">Parties et saisons sans limite. Merci !</span>
      </p>
    );
  }
  // Une saison compte dès qu'elle commence : celle en cours est déjà comptée.
  const left = me.seasons_left;
  let status;
  if (left === 0) {
    status = saves
      ? "Dernière saison gratuite : ta partie s'arrête à la fin de celle-ci."
      : `Tes ${me.free_seasons} saisons gratuites sont jouées.`;
  } else if (me.seasons_played === 0) {
    status = `${me.free_seasons} saisons gratuites à jouer.`;
  } else {
    status = `Saison gratuite ${me.seasons_played} sur ${me.free_seasons} : encore ${left} à lancer.`;
  }
  return (
    <div className="full-game">
      <div className="full-game__body">
        <p className="eyebrow">Compte gratuit</p>
        <p className="full-game__text">{status}</p>
        <p className="muted full-game__hint">
          Une seule partie, et {me.free_seasons} saisons en tout : supprimer une carrière ne rend pas ses saisons. Le
          jeu complet ouvre trois parties et des saisons sans fin, pour {PRICE_LABEL}, une fois.
        </p>
      </div>
      <div className="full-game__action">
        <UnlockButton />
      </div>
    </div>
  );
}

// Le compte gratuit peut-il commencer une nouvelle partie ? (sinon, pourquoi)
export function newSaveBlocked(me, saves) {
  if (me?.guest && saves >= 1) return "Sans compte, une seule partie : crée un compte pour en mener plusieurs";
  if (!me || !me.paywall || me.premium) return null;
  if (me.seasons_left === 0) return "Tes saisons gratuites sont jouées : passe au jeu complet";
  if (saves >= me.free_saves) return "Le compte gratuit garde une seule partie";
  return null;
}
