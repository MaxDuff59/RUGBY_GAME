import { useState } from "react";

import { api } from "../api.js";
import { parseDate } from "../format.js";

// Jeu complet : abonnement de 2 € par an chez Stripe (backend/api/billing.py), qui vaut
// jusqu'au 1er juillet, fin de la saison du jeu, et se renouvelle chaque 1er juillet.
// Le compte gratuit garde une partie et joue deux saisons en tout, supprimées comprises.
export const PRICE_LABEL = "2 € par an";
// Réponse de l'API quand c'est la formule gratuite qui bloque (backend/api/plans.py).
export const PAYMENT_REQUIRED = 402;

// « 1er juillet 2027 », d'une date "AAAA-MM-JJ" de l'API.
const untilDay = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" });
export const formatUntil = (iso) => untilDay.format(parseDate(iso)).replace(/^1 /, "1er ");

// Part vers une page de Stripe (`open` renvoie son adresse) ; le retour se fait sur /parties.
function StripeButton({ open, label, primary = true, disabled = false }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const { url } = await open();
      window.location.assign(url);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className={primary ? "button button--primary" : "button"} disabled={busy || disabled} onClick={go}>
        {busy ? "Ouverture de Stripe…" : label}
      </button>
      {error && <p className="status--error full-game__error">{error.message}</p>}
    </>
  );
}

// La case à cocher avant de payer : CGV acceptées, accès immédiat demandé, donc pas de
// droit de rétractation (contenu numérique, art. L221-28 13° du code de la
// consommation). L'API refuse le paiement sans elle et garde l'accord chez Stripe.
export function UnlockButton({ label = `S'abonner au jeu complet · ${PRICE_LABEL}` }) {
  const [accepted, setAccepted] = useState(false);
  return (
    <>
      <label className="full-game__terms">
        <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
        <span>
          J'accepte les{" "}
          <a href="/cgv" target="_blank" rel="noreferrer">
            CGV
          </a>{" "}
          et je veux accéder au jeu complet tout de suite : je renonce donc à mon droit de rétractation de 14 jours.
        </span>
      </label>
      <StripeButton open={() => api.checkout(true)} label={label} disabled={!accepted} />
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
    let text = "Parties et saisons sans limite. Merci !";
    if (me.premium_until) {
      text = me.subscribed
        ? `Parties et saisons sans limite jusqu'au ${formatUntil(me.premium_until)} ; l'abonnement se renouvelle chaque 1er juillet, sauf résiliation. Merci !`
        : `Parties et saisons sans limite jusqu'au ${formatUntil(me.premium_until)}, fin de la saison du jeu. Merci !`;
    }
    return (
      <div className="full-game full-game--done">
        <div className="full-game__body">
          <p className="eyebrow">Jeu complet</p>
          <p className="muted full-game__hint">{text}</p>
        </div>
        {me.subscribed && (
          <div className="full-game__action">
            <StripeButton open={api.billingPortal} label="Gérer mon abonnement" primary={false} />
          </div>
        )}
      </div>
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
          jeu complet ouvre trois parties et des saisons sans fin, pour {PRICE_LABEL} : il vaut pour la saison, jusqu'au{" "}
          {formatUntil(me.season_end)}, puis l'abonnement se renouvelle chaque 1er juillet, avec la nouvelle version du
          jeu. Résiliable à tout moment.
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
