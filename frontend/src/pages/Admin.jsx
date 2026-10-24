import { useCallback, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import "../admin.css";
import { adminApi } from "../adminApi.js";
import { byLeague, formatDay } from "../adminFormat.js";
import AdminAccounts, { PlanBadge } from "../components/AdminAccounts.jsx";
import AdminClubs from "../components/AdminClubs.jsx";
import AdminLeagues from "../components/AdminLeagues.jsx";
import AdminPlayers from "../components/AdminPlayers.jsx";
import ClubCrest from "../components/ClubCrest.jsx";
import { useApi } from "../hooks/useApi.js";

// Backoffice (/backoffice) : vue d'ensemble, comptes et formule, clubs (fiche, championnat,
// couleurs, blason, effectif ; création), joueurs (fiche, club, photo, notes ; création,
// suppression) et championnats (création, archivage). Réservé au compte de l'administrateur
// (l'API répond 403 aux autres).
const TABS = [
  { key: "overview", label: "Vue d'ensemble" },
  { key: "accounts", label: "Comptes" },
  { key: "clubs", label: "Clubs" },
  { key: "players", label: "Joueurs" },
  { key: "leagues", label: "Championnats" },
];

export default function Admin() {
  const me = useApi(useCallback(adminApi.me, []));
  const [tab, setTab] = useState("overview");

  if (me.error?.status === 401) return <Navigate to="/connexion" replace />;
  if (me.loading) return <p className="status">Chargement…</p>;
  if (me.error) {
    return (
      <div className="admin">
        <p className="status status--error">
          {me.error.status === 403
            ? "Ce compte n'a pas accès au backoffice."
            : `Impossible de joindre l'API (${me.error.message}).`}
        </p>
        <Link className="button admin__back" to="/parties">
          Retour aux parties
        </Link>
      </div>
    );
  }

  return (
    <div className="admin">
      <header className="page-head admin__head">
        <div>
          <p className="eyebrow">Rugby Manager</p>
          <h1 className="title">Backoffice</h1>
        </div>
        <div className="admin__account">
          <span className="muted">{me.data.email}</span>
          <Link className="button" to="/parties">
            Retour aux parties
          </Link>
        </div>
      </header>

      <nav className="chips" aria-label="Rubriques">
        {TABS.map((t) => (
          <button key={t.key} type="button" className="chip" aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>

      <div className="admin__body">
        {tab === "overview" && <Overview onOpen={setTab} />}
        {tab === "accounts" && <AdminAccounts />}
        {tab === "clubs" && <AdminClubs />}
        {tab === "players" && <AdminPlayers />}
        {tab === "leagues" && <AdminLeagues />}
      </div>
    </div>
  );
}

function Overview({ onOpen }) {
  const overview = useApi(useCallback(adminApi.overview, []));
  const users = useApi(useCallback(adminApi.users, []));
  const clubs = useApi(useCallback(adminApi.clubs, []));

  if (overview.loading) return <p className="status">Chargement…</p>;
  if (overview.error) return <p className="status status--error">{overview.error.message}</p>;
  const o = overview.data;
  const share = o.accounts ? Math.round((o.premium / o.accounts) * 100) : 0;

  return (
    <div className="admin__overview">
      <div className="admin__tiles">
        <Tile label="Comptes" value={o.accounts} hint={`+${o.new_7_days} en 7 jours · +${o.new_30_days} en 30 jours`} />
        <Tile
          label="Version complète"
          value={o.premium}
          hint={`${share} % des comptes · ${o.premium_paid} payée${o.premium_paid > 1 ? "s" : ""} · ${o.premium_offered} offerte${o.premium_offered > 1 ? "s" : ""}`}
        />
        <Tile
          label="Gratuits au bout"
          value={o.free_exhausted}
          hint={`Ont joué leurs ${o.free_seasons} saisons gratuites`}
        />
        <Tile label="Parties" value={o.saves} hint={`${o.active_sessions} session${o.active_sessions > 1 ? "s" : ""} ouverte${o.active_sessions > 1 ? "s" : ""}`} />
        <Tile label="Clubs retouchés" value={o.clubs_edited} hint={`sur ${o.clubs} vrais clubs · ${o.logos} blason${o.logos > 1 ? "s" : ""} envoyé${o.logos > 1 ? "s" : ""}`} />
      </div>

      <div className="admin__split admin__split--even">
        <section className="card admin__panel">
          <div className="admin__panel-head">
            <h2 className="eyebrow">Derniers inscrits</h2>
            <button type="button" className="admin__link" onClick={() => onOpen("accounts")}>
              Tous les comptes
            </button>
          </div>
          <div className="admin__scroll">
            <table className="table">
              <thead>
                <tr>
                  <th className="left">Compte</th>
                  <th>Inscrit</th>
                  <th>Formule</th>
                </tr>
              </thead>
              <tbody>
                {(users.data ?? []).slice(0, 12).map((u) => (
                  <tr key={u.id}>
                    <td className="left admin__email">{u.email}</td>
                    <td>{formatDay(u.created_at)}</td>
                    <td>
                      <PlanBadge account={u} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card admin__panel">
          <div className="admin__panel-head">
            <h2 className="eyebrow">Clubs par championnat</h2>
            <button type="button" className="admin__link" onClick={() => onOpen("clubs")}>
              Gérer les clubs
            </button>
          </div>
          <div className="admin__scroll">
            <table className="table">
              <thead>
                <tr>
                  <th className="left">Championnat</th>
                  <th>Clubs</th>
                  <th>Vrais effectifs</th>
                  <th>Retouchés</th>
                </tr>
              </thead>
              <tbody>
                {byLeague(clubs.data ?? []).map(([league, list]) => (
                  <tr key={league}>
                    <td className="left">
                      <span className="admin__crests">
                        {list.slice(0, 4).map((c) => (
                          <ClubCrest key={c.name} name={c.name} size={18} />
                        ))}
                      </span>
                      {league}
                    </td>
                    <td>{list.length}</td>
                    <td>{list.filter((c) => c.roster_source !== "inventé").length}</td>
                    <td>{list.filter((c) => c.edited.length).length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}

function Tile({ label, value, hint }) {
  return (
    <div className="card tile">
      <span className="eyebrow">{label}</span>
      <span className="tile__value">{value}</span>
      <span className="muted">{hint}</span>
    </div>
  );
}
