import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

// Le guide de la première saison : sous l'en-tête, un conseil du staff pour la page
// ouverte. « Compris » range ce conseil, « Masquer le guide » les range tous. Ce que
// le joueur a déjà lu reste dans son navigateur ; « Revoir le guide » (menu) remet tout.
const KEY = "rugby.guide";

const TIPS = {
  "/": "Ton tableau de bord. « Simuler la journée » joue la prochaine journée ; « Jouer le match » te met au bord du terrain. La vie du club, à droite, dit si le vestiaire, la direction et les supporters te suivent.",
  "/effectif":
    "Touche un joueur du terrain pour changer ton XV, une ligne du tableau pour sa fiche. Pot. est le potentiel estimé par le staff : un jeune qui joue et joue bien s'en approche match après match.",
  "/entrainement":
    "Le rythme de la semaine arbitre entre fraîcheur et progrès ; le thème oriente les progrès et donne un petit plus au match suivant. Ils valent jusqu'à ce que tu les changes.",
  "/transferts":
    "Les joueurs en dernière année de contrat (pré-contrat), les prêts et les agents libres coûtent bien moins cher qu'un transfert. Les notes marquées ≈ sont estimées : supervise un joueur pour connaître sa vraie valeur. Attention au plafond salarial de ton championnat.",
  "/medical":
    "Chaque blessé attend son protocole : prudent (plus long, peu de rechutes), normal, ou accéléré (retour plus tôt, rechute plus fréquente, et ça se paie).",
  "/formation":
    "Les espoirs jouent leur championnat et progressent vers leur potentiel. Promeus les meilleurs avant 22 ans, sinon ils quittent le centre.",
  "/staff":
    "Chaque poste du staff pèse sur le match ou sur la récupération : un entraîneur à 3 étoiles ne change rien, chaque étoile en plus ou en moins déplace le curseur.",
  "/finances": "Billetterie et sponsors à chaque match à domicile, salaires à chaque journée. Une trésorerie dans le rouge entame la confiance de la direction.",
  "/calendrier": "Clique un score pour la fiche du match : statistiques, météo, public. La colonne Sélections signale les doublons, quand tes internationaux manquent.",
  "/palmares": "Les champions, les trophées de chaque saison et ton parcours : les titres et les phases finales font grimper ta réputation, et les grands clubs finissent par appeler.",
};

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) ?? { seen: [], off: false };
  } catch {
    return { seen: [], off: false };
  }
}

function write(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // Stockage indisponible : le conseil reviendra à la prochaine ouverture.
  }
}

// Remet le guide à zéro (« Revoir le guide ») ; le bandeau se rouvre aussitôt.
export function resetGuide() {
  write({ seen: [], off: false });
  window.dispatchEvent(new Event(KEY));
}

export default function Guide() {
  const { pathname } = useLocation();
  const [state, setState] = useState(read);
  useEffect(() => {
    const reload = () => setState(read());
    window.addEventListener(KEY, reload);
    return () => window.removeEventListener(KEY, reload);
  }, []);
  const tip = TIPS[pathname];
  if (!tip || state.off || state.seen.includes(pathname)) return null;

  const update = (next) => {
    write(next);
    setState(next);
  };

  return (
    <aside className="guide" aria-label="Conseil du staff">
      <div>
        <p className="eyebrow">Conseil du staff</p>
        <p className="guide__text">{tip}</p>
      </div>
      <div className="guide__actions">
        <button type="button" className="button button--small" onClick={() => update({ ...state, seen: [...state.seen, pathname] })}>
          Compris
        </button>
        <button type="button" className="link-button muted" onClick={() => update({ ...state, off: true })}>
          Masquer le guide
        </button>
      </div>
    </aside>
  );
}
