import { useCallback, useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useClubTheme } from "../clubs.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { chosenSlot, leaveSlot } from "../save.js";
import ClubCrest from "./ClubCrest.jsx";
import Guide, { resetGuide } from "./Guide.jsx";
import Inbox from "./Inbox.jsx";
import { ManagerContractModal } from "./ManagerContract.jsx";
import NavIcon from "./NavIcon.jsx";
import { DIFFICULTIES, formatContractEnd } from "../format.js";

// `primary` : les entrées de la barre d'onglets du téléphone ; les autres passent
// dans le volet « Plus ». `icon` : clé du pictogramme (NavIcon).
const NAV_ITEMS = [
  { to: "/", label: "Club", icon: "club", primary: true },
  { to: "/journal", label: "Journal", icon: "journal" },
  { to: "/calendrier", label: "Calendrier", icon: "calendrier", primary: true },
  { to: "/effectif", label: "Effectif", icon: "effectif", primary: true },
  { to: "/entrainement", label: "Entraînement", icon: "entrainement" },
  { to: "/medical", label: "Médical", icon: "medical" },
  { to: "/formation", label: "Formation", icon: "formation" },
  { to: "/staff", label: "Staff", icon: "staff" },
  { to: "/transferts", label: "Transferts", icon: "transferts", primary: true },
  { to: "/infrastructures", label: "Infrastructures", icon: "infrastructures" },
  { to: "/finances", label: "Finances", icon: "finances" },
  { to: "/international", label: "Sélections", icon: "selections" },
  { to: "/palmares", label: "Palmarès", icon: "palmares" },
  // La page Match (/match) n'a pas d'entrée ici : on y va par « Jouer le match », page Club.
];

// Carrière de sélectionneur : pas de club à gérer, ses quatre pages et le journal.
const SELECTOR_NAV_ITEMS = [
  { to: "/", label: "Sélection", icon: "club", primary: true },
  { to: "/journal", label: "Journal", icon: "journal" },
  { to: "/liste", label: "Liste", icon: "liste", primary: true },
  { to: "/effectif", label: "Le XV", icon: "effectif", primary: true },
  { to: "/international", label: "Calendrier", icon: "calendrier", primary: true },
];

// Cadre commun à toutes les pages : sur ordinateur, navigation à gauche et en-tête avec
// le club ; sur téléphone (PHONE_QUERY), en-tête compact et barre d'onglets en bas.
// Les pages reçoivent la carrière via useOutletContext(), et `onContract` pour y
// reporter le contrat du manager quand il change (prolongation). Un sélectionneur
// (`career.kind === "nation"`) a sa propre navigation ; `career.club_id` et
// `career.club_name` sont alors ceux de sa sélection.
export default function Layout() {
  const { data: career, error, loading, setData } = useApi(useCallback(api.getCareer, []));
  // Le contrat du manager se lit (et se prolonge) depuis le pied de la navigation.
  const [contractOpen, setContractOpen] = useState(false);
  useClubTheme(career?.club_name);
  const phone = useMediaQuery(PHONE_QUERY);

  // Chaque ouverture du jeu passe par l'écran des parties.
  if (error?.status === 401) return <Navigate to="/connexion" replace />;
  if (chosenSlot() === null || error?.status === 409) return <Navigate to="/parties" replace />;
  if (loading) return <p className="status">Chargement…</p>;
  // Pas de carrière : on commence par choisir un club.
  if (error?.status === 404) return <Navigate to="/start" replace />;
  if (error) return <p className="status status--error">{error.message}</p>;

  const items = career.kind === "nation" ? SELECTOR_NAV_ITEMS : NAV_ITEMS;
  const openContract = () => setContractOpen(true);
  const onContract = (contract) => setData({ ...career, contract_until: contract.until });

  return (
    <div className={phone ? "app app--phone" : "app"}>
      {!phone && <Sidebar career={career} items={items} onContract={openContract} />}

      <main className="main">
        <header className="header">
          <div className="header__club">
            <ClubCrest name={career.club_name} size={phone ? 40 : 50} />
            <div>
              <div className="header__name">{career.club_name}</div>
              <div className="muted">{career.league_name}</div>
            </div>
          </div>
          {career.kind !== "nation" && <Inbox />}
        </header>
        {career.kind !== "nation" && <Guide />}
        <Outlet context={{ career, onContract }} />
      </main>

      {phone && <TabBar career={career} items={items} onContract={openContract} />}
      {contractOpen && (
        <ManagerContractModal
          onClose={() => setContractOpen(false)}
          onChange={onContract}
        />
      )}
    </div>
  );
}

function LeaveButton({ className = "" }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className={`button button--small ${className}`}
      onClick={() => {
        leaveSlot();
        navigate("/parties");
      }}
    >
      Quitter la partie
    </button>
  );
}

// Ordinateur : colonne de navigation à gauche.
// Le contrat du manager de club, en une ligne qui ouvre sa fenêtre.
function ContractLink({ career, onContract, className = "" }) {
  if (career.kind === "nation" || career.contract_until == null) return null;
  return (
    <button type="button" className={`link-button ${className}`} onClick={onContract}>
      Contrat jusqu'en {formatContractEnd(career.contract_until)}
    </button>
  );
}

function Sidebar({ career, items, onContract }) {
  return (
    <nav className="sidebar" aria-label="Navigation principale">
      <div className="brand">
        <img className="brand__mark" src="/logo-mark.png" alt="" />
        <span className="brand__name">Rugby Manager</span>
      </div>
      <ul className="nav">
        {items.map((item) => (
          <li key={item.label}>
            <NavLink to={item.to} end className="nav__link">
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="sidebar__footer">
        <div>
          {career.kind === "nation" ? "Sélectionneur" : "Manager"} : {career.manager_name}
        </div>
        <div>
          Partie {chosenSlot()} · sauvegarde auto
          {career.difficulty && career.difficulty !== "normal" && ` · ${DIFFICULTIES[career.difficulty].label.toLowerCase()}`}
        </div>
        <ContractLink career={career} onContract={onContract} className="sidebar__contract" />
        {career.kind !== "nation" && (
          <button type="button" className="link-button sidebar__guide" onClick={resetGuide}>
            Revoir le guide
          </button>
        )}
        <LeaveButton className="sidebar__leave" />
      </div>
    </nav>
  );
}

// Téléphone : barre d'onglets en bas de l'écran, pictogramme et libellé. Les entrées
// secondaires et « Quitter la partie » sont dans le volet ouvert par « Plus ».
function TabBar({ career, items, onContract }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const { pathname } = useLocation();
  const primary = items.filter((item) => item.primary);
  const secondary = items.filter((item) => !item.primary);
  // « Plus » est l'onglet actif quand la page courante est l'une des siennes.
  const moreActive = secondary.some((item) => item.to === pathname);

  // Le volet se ferme au changement de page et par Échap.
  useEffect(() => setMoreOpen(false), [pathname]);
  useEffect(() => {
    if (!moreOpen) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setMoreOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [moreOpen]);

  return (
    <>
      {moreOpen && (
        <div className="sheet" onClick={() => setMoreOpen(false)}>
          <div className="sheet__panel card" role="dialog" aria-label="Autres pages" onClick={(event) => event.stopPropagation()}>
            <ul className="sheet__grid">
              {secondary.map((item) => (
                <li key={item.label}>
                  <NavLink to={item.to} end className="sheet__link">
                    <NavIcon name={item.icon} size={24} />
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
            <div className="sheet__footer">
              <div className="muted">
                {career.kind === "nation" ? "Sélectionneur" : "Manager"} : {career.manager_name} · Partie{" "}
                {chosenSlot()} · sauvegarde auto
              </div>
              <ContractLink career={career} onContract={onContract} />
              {career.kind !== "nation" && (
                <button type="button" className="link-button" onClick={resetGuide}>
                  Revoir le guide
                </button>
              )}
              <LeaveButton />
            </div>
          </div>
        </div>
      )}

      <nav className="tabbar" aria-label="Navigation principale">
        {primary.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            end
            className={({ isActive }) => `tabbar__link${isActive && !moreOpen ? " active" : ""}`}
            onClick={() => setMoreOpen(false)}
          >
            <span className="tabbar__icon">
              <NavIcon name={item.icon} />
            </span>
            <span className="tabbar__label">{item.label}</span>
          </NavLink>
        ))}
        <button
          type="button"
          className={`tabbar__link${moreOpen || moreActive ? " active" : ""}`}
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((open) => !open)}
        >
          <span className="tabbar__icon">
            <NavIcon name="plus" />
          </span>
          <span className="tabbar__label">Plus</span>
        </button>
      </nav>
    </>
  );
}
