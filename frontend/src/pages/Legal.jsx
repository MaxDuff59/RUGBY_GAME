import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { PRICE_LABEL } from "../components/FullGame.jsx";

// Pages légales, ouvertes à tous (sans compte ni partie) : mentions légales (LCEN,
// art. 6 III), conditions générales de vente (code de la consommation) et politique
// de confidentialité (RGPD, art. 13). Un onglet par page, le texte défile dans sa carte.
//
// L'identité de l'éditeur est rassemblée ici : c'est le seul endroit à mettre à jour.
const EDITOR = {
  name: "Maxence Duffuler",
  status: "Entrepreneur individuel",
  address: "41 Rue Boucicaut 92260 Fontenay-aux-Roses",
  siret: "[à compléter : numéro SIRET]",
  director: "[à compléter : prénom et nom du directeur de la publication]",
  vat: "[à compléter : « TVA non applicable, art. 293 B du CGI » en franchise de TVA, sinon numéro de TVA intracommunautaire]",
  mediator:
    "[à compléter : nom, adresse et site du médiateur de la consommation choisi]",
};
const EMAIL = "contact@rugby-manager.app";
const SITE = "www.rugby-manager.app";

const Mail = () => <a href={`mailto:${EMAIL}`}>{EMAIL}</a>;

const PAGES = [
  {
    path: "/mentions-legales",
    tab: "Mentions légales",
    title: "Mentions légales",
    sections: [
      {
        title: "Éditeur",
        body: (
          <>
            <p>
              Le site {SITE} et le jeu Rugby Manager sont édités par{" "}
              {EDITOR.name}, {EDITOR.status}.
            </p>
            <ul>
              <li>Adresse : {EDITOR.address}</li>
              <li>SIRET : {EDITOR.siret}</li>
              <li>
                Contact : <Mail />
              </li>
              <li>Directeur de la publication : {EDITOR.director}</li>
            </ul>
          </>
        ),
      },
      {
        title: "Hébergement",
        body: (
          <ul>
            <li>
              Interface du jeu : Vercel Inc., 440 N Barranca Ave #4133, Covina,
              CA 91723, États-Unis (vercel.com).
            </li>
            <li>
              Serveur et base de données : Railway Corporation, 548 Market St
              PMB 68956, San Francisco, CA 94104, États-Unis (railway.com).
            </li>
          </ul>
        ),
      },
      {
        title: "Jeu indépendant",
        body: (
          <>
            <p>
              Rugby Manager est un jeu indépendant. Il n'est ni affilié, ni
              approuvé, ni soutenu par les clubs, ligues, fédérations,
              compétitions ou joueurs cités. Leurs noms, logos et marques
              appartiennent à leurs propriétaires respectifs et ne servent qu'à
              les désigner.
            </p>
            <p>
              Les photos de joueurs viennent de Wikimedia Commons, chacune sous
              la licence indiquée sur sa page (auteur et licence). Un titulaire
              de droits qui souhaite le retrait d'un contenu peut écrire à{" "}
              <Mail /> : il sera retiré rapidement.
            </p>
          </>
        ),
      },
      {
        title: "Propriété intellectuelle",
        body: (
          <p>
            Le code, les textes, les graphismes et le moteur du jeu sont la
            propriété de l'éditeur. Toute reproduction sans autorisation est
            interdite.
          </p>
        ),
      },
    ],
  },
  {
    path: "/cgv",
    tab: "CGV",
    title: "Conditions générales de vente",
    sections: [
      {
        title: "1. Objet",
        body: (
          <p>
            Ces conditions régissent la vente du « jeu complet » de Rugby
            Manager par {EDITOR.name} (l'éditeur, voir les mentions légales) à
            toute personne qui s'y abonne depuis le jeu (toi). Les accepter est
            une condition de l'abonnement : une case à cocher le confirme avant
            le paiement.
          </p>
        ),
      },
      {
        title: "2. Ce qui est vendu",
        body: (
          <>
            <p>
              Le compte gratuit garde une partie et joue deux saisons de jeu en
              tout. Le jeu complet ouvre trois parties et des saisons sans
              limite, jusqu'au 1er juillet suivant (fin de la saison du jeu),
              puis d'année en année tant que l'abonnement court. Il s'agit d'un
              contenu numérique, fourni en ligne, sans support matériel.
            </p>
            <p>
              Le jeu évolue : de nouvelles versions peuvent modifier ou ajouter
              des fonctions. L'éditeur fait au mieux pour que le jeu reste
              disponible, sans garantir une disponibilité sans interruption
              (maintenance, incident technique).
            </p>
          </>
        ),
      },
      {
        title: "3. Prix et paiement",
        body: (
          <p>
            Le prix est de {PRICE_LABEL}, toutes taxes comprises ({EDITOR.vat}).
            Il se paie par carte bancaire sur la page sécurisée de Stripe, notre
            prestataire de paiement : l'éditeur ne voit jamais les numéros de
            carte. Le premier paiement couvre la saison en cours, jusqu'au 1er
            juillet suivant ; il est débité tout de suite.
          </p>
        ),
      },
      {
        title: "4. Renouvellement et résiliation",
        body: (
          <>
            <p>
              L'abonnement se renouvelle automatiquement chaque 1er juillet,
              pour un an, au prix de {PRICE_LABEL}, sur la carte enregistrée. Tu
              peux le résilier à tout moment, sans frais, depuis l'écran « Tes
              parties » → « Gérer mon abonnement » : il s'arrête alors à la fin
              de la période payée, sans remboursement de la période en cours.
              Sans renouvellement (résiliation, carte refusée), le compte
              repasse en formule gratuite ; tes parties restent gardées.
            </p>
            <p>
              Un changement de prix est annoncé par e-mail au moins un mois
              avant le renouvellement concerné : tu peux alors résilier avant
              qu'il s'applique.
            </p>
          </>
        ),
      },
      {
        title: "5. Droit de rétractation",
        body: (
          <p>
            Le jeu complet est un contenu numérique fourni dès le paiement.
            Avant de payer, tu demandes expressément cet accès immédiat et tu
            reconnais perdre ainsi ton droit de rétractation de 14 jours
            (article L221-28 13° du code de la consommation), en cochant la case
            prévue. Sans cette case, le paiement n'est pas possible.
          </p>
        ),
      },
      {
        title: "6. Garantie légale de conformité",
        body: (
          <p>
            Tu bénéficies de la garantie légale de conformité des contenus
            numériques (articles L224-25-1 et suivants du code de la
            consommation) : en cas de défaut, écris à <Mail /> ; l'éditeur remet
            le jeu en conformité ou, à défaut, te rembourse.
          </p>
        ),
      },
      {
        title: "7. Réclamations et médiation",
        body: (
          <p>
            Pour toute réclamation, écris d'abord à <Mail />. Si le désaccord
            persiste, tu peux recourir gratuitement au médiateur de la
            consommation : {EDITOR.mediator}.
          </p>
        ),
      },
      {
        title: "8. Droit applicable",
        body: (
          <p>
            Ces conditions sont soumises au droit français. À défaut d'accord
            amiable, le litige relève des tribunaux compétents selon les règles
            du code de la consommation.
          </p>
        ),
      },
    ],
  },
  {
    path: "/confidentialite",
    tab: "Confidentialité",
    title: "Confidentialité",
    sections: [
      {
        title: "Responsable du traitement",
        body: (
          <p>
            {EDITOR.name}, {EDITOR.address}. Pour toute question sur tes données
            : <Mail />.
          </p>
        ),
      },
      {
        title: "Ce que le jeu garde",
        body: (
          <ul>
            <li>
              Ton adresse e-mail et ton mot de passe, chiffré (haché) : on ne
              peut pas le lire.
            </li>
            <li>
              Tes parties : ton club ou ta sélection, tes choix et l'avancée de
              tes saisons.
            </li>
            <li>
              Si tu t'abonnes : les références de ton client et de tes paiements
              chez Stripe, et les dates de ton abonnement. Les données de carte
              restent chez Stripe.
            </li>
            <li>
              La date à laquelle tu as demandé à ne plus recevoir nos e-mails,
              le cas échéant.
            </li>
            <li>
              Sans compte (invité) : seulement ta partie, rattachée à un cookie,
              sans e-mail ni autre information.
            </li>
          </ul>
        ),
      },
      {
        title: "Pourquoi",
        body: (
          <ul>
            <li>
              Faire fonctionner ton compte et tes parties (exécution du
              contrat).
            </li>
            <li>
              Encaisser l'abonnement et garder les justificatifs (contrat,
              obligations comptables).
            </li>
            <li>
              T'écrire au sujet du jeu (intérêt légitime) : chaque e-mail porte
              un lien pour ne plus en recevoir, en un clic.
            </li>
            <li>
              Protéger le jeu : ton adresse IP sert, en mémoire et quelques
              minutes, à freiner les tentatives de connexion répétées (intérêt
              légitime).
            </li>
          </ul>
        ),
      },
      {
        title: "Combien de temps",
        body: (
          <ul>
            <li>
              Compte et parties : tant que le compte existe ; écris-nous pour le
              supprimer.
            </li>
            <li>Partie sans compte : effacée après 7 jours sans visite.</li>
            <li>Session de connexion : 30 jours.</li>
            <li>Justificatifs de paiement : 10 ans (obligation comptable).</li>
            <li>
              Journaux techniques de l'hébergeur : quelques semaines au plus.
            </li>
          </ul>
        ),
      },
      {
        title: "Qui y a accès",
        body: (
          <>
            <p>
              L'éditeur, et ses prestataires, chacun pour sa part : Vercel
              (interface du jeu), Railway (serveur et base de données), Stripe
              (paiement), Resend (envoi des e-mails). Ces prestataires sont
              établis aux États-Unis : les transferts sont encadrés par le Data
              Privacy Framework UE–États-Unis ou par les clauses contractuelles
              types de la Commission européenne.
            </p>
            <p>
              Rien n'est vendu ni partagé à des fins publicitaires. Le jeu n'a
              ni publicité, ni mesure d'audience, ni enregistrement de session.
              Ses polices et ses photos sont servies par nos propres serveurs :
              ton navigateur ne contacte aucun autre site pour les afficher.
            </p>
          </>
        ),
      },
      {
        title: "Cookies et stockage",
        body: (
          <p>
            Un seul cookie : celui de ta session, indispensable pour rester
            connecté. Le navigateur garde aussi tes réglages (guide, scènes 3D)
            et la partie ouverte. Rien de tout cela ne sert à te suivre ; ces
            éléments, strictement nécessaires au jeu, ne demandent pas de
            consentement.
          </p>
        ),
      },
      {
        title: "Tes droits",
        body: (
          <>
            <p>
              Tu peux accéder à tes données, les faire corriger ou effacer,
              t'opposer à leur usage, en limiter l'usage ou les recevoir dans un
              format lisible (portabilité) : écris à <Mail />. Si tu estimes que
              tes droits ne sont pas respectés, tu peux saisir la CNIL
              (cnil.fr).
            </p>
            <p>
              Si tu as moins de 15 ans, demande l'accord d'un parent avant de
              créer un compte.
            </p>
          </>
        ),
      },
    ],
  },
];

export default function Legal() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const page = PAGES.find((p) => p.path === pathname) ?? PAGES[0];

  // Ouverte dans un nouvel onglet (lien de la case CGV) : pas d'historique, retour au jeu.
  function back() {
    if (window.history.length > 1) navigate(-1);
    else navigate("/parties");
  }

  return (
    <div className="start legal">
      <header className="page-head">
        <div>
          <p className="eyebrow">Rugby Manager</p>
          <h1 className="title">{page.title}</h1>
        </div>
        <button type="button" className="button" onClick={back}>
          Retour
        </button>
      </header>

      <nav className="chips" aria-label="Pages légales">
        {PAGES.map((p) => (
          <NavLink key={p.path} to={p.path} replace className="chip legal__tab">
            {p.tab}
          </NavLink>
        ))}
      </nav>

      <article className="card legal__body">
        {page.sections.map((section) => (
          <section key={section.title} className="legal__section">
            <h2 className="legal__heading">{section.title}</h2>
            {section.body}
          </section>
        ))}
        <p className="muted legal__updated">Mise à jour : 6 novembre 2026.</p>
      </article>
    </div>
  );
}

// Les liens vers les pages légales, en pied d'écran (connexion, parties).
export function LegalLinks({ className = "" }) {
  return (
    <nav
      className={`legal-links ${className}`}
      aria-label="Informations légales"
    >
      {PAGES.map((p) => (
        <NavLink key={p.path} to={p.path}>
          {p.tab}
        </NavLink>
      ))}
    </nav>
  );
}
