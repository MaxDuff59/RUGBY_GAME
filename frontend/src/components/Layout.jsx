import { useCallback } from "react";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useApi } from "../hooks/useApi.js";
import { chosenSlot, leaveSlot } from "../save.js";

const NAV_ITEMS = [
  { to: "/", label: "Club" },
  { to: "/calendrier", label: "Calendrier" },
  { to: "/effectif", label: "Effectif" },
  { to: "/medical", label: "Médical" },
  { to: "/formation", label: "Formation" },
  { to: "/staff", label: "Staff" },
  { to: "/transferts", label: "Transferts" },
  { to: "/infrastructures", label: "Infrastructures" },
  { to: "/finances", label: "Finances" },
  // La page Match (/match) n'a pas d'entrée ici : on y va par « Jouer le match », page Club.
];

// Cadre commun à toutes les pages : navigation à gauche, en-tête avec le club.
// Les pages reçoivent la carrière via useOutletContext().
export default function Layout() {
  const { data: career, error, loading } = useApi(useCallback(api.getCareer, []));
  const navigate = useNavigate();

  // Chaque ouverture du jeu passe par l'écran des parties.
  if (chosenSlot() === null || error?.status === 409) return <Navigate to="/parties" replace />;
  if (loading) return <p className="status">Chargement…</p>;
  // Pas de carrière : on commence par choisir un club.
  if (error?.status === 404) return <Navigate to="/start" replace />;
  if (error) return <p className="status status--error">{error.message}</p>;

  return (
    <div className="app">
      <nav className="sidebar" aria-label="Navigation principale">
        <div className="brand">
          <span className="brand__mark">XV</span>
          <span className="brand__name">Rugby Manager</span>
        </div>
        <ul className="nav">
          {NAV_ITEMS.map((item) => (
            <li key={item.label}>
              <NavLink to={item.to} end className="nav__link">
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="sidebar__footer">
          <div>Manager : {career.manager_name}</div>
          <div>Partie {chosenSlot()} · sauvegarde auto</div>
          <button
            type="button"
            className="button button--small sidebar__leave"
            onClick={() => {
              leaveSlot();
              navigate("/parties");
            }}
          >
            Quitter la partie
          </button>
        </div>
      </nav>

      <main className="main">
        <header className="header">
          <div className="header__club">
            <span className="crest">{initials(career.club_name)}</span>
            <div>
              <div className="header__name">{career.club_name}</div>
              <div className="muted">{career.league_name}</div>
            </div>
          </div>
        </header>
        <Outlet context={{ career }} />
      </main>
    </div>
  );
}

// "Entente Port-Miremire" -> "EPM" (pour l'écusson)
function initials(name) {
  return name
    .split(/[\s-]+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}
