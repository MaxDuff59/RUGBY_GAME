import { useCallback } from "react";
import { Navigate, NavLink, Outlet } from "react-router-dom";

import { api } from "../api.js";
import { useApi } from "../hooks/useApi.js";

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
  // Page à venir : affichée pour donner la forme du menu, mais inactive.
  { label: "Match" },
];

// Cadre commun à toutes les pages : navigation à gauche, en-tête avec le club.
// Les pages reçoivent la carrière via useOutletContext().
export default function Layout() {
  const { data: career, error, loading } = useApi(useCallback(api.getCareer, []));

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
          {NAV_ITEMS.map((item) =>
            item.to ? (
              <li key={item.label}>
                <NavLink to={item.to} end className="nav__link">
                  {item.label}
                </NavLink>
              </li>
            ) : (
              <li key={item.label}>
                <span className="nav__link nav__link--disabled" aria-disabled="true">
                  {item.label}
                </span>
              </li>
            ),
          )}
        </ul>
        <div className="sidebar__footer">Manager : {career.manager_name}</div>
      </nav>

      <main className="main">
        <header className="header">
          <div className="header__club">
            <span className="crest">{initials(career.club_name)}</span>
            <div>
              <div className="header__name">{career.club_name}</div>
              <div className="muted">Championnat</div>
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
