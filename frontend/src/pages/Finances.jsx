import { useCallback, useMemo, useState } from "react";

import { api } from "../api.js";
import SortHeader from "../components/SortHeader.jsx";
import { CATEGORIES, formatMoney, formatNumericDate, formatSignedMoney } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { useSort } from "../hooks/useSort.js";

// Les finances : la trésorerie en vedette, la masse salariale décomposée (et le
// plafond des pros), puis toutes les opérations, filtrables par sens.
export default function Finances() {
  const { data, error, loading } = useApi(useCallback(api.getFinances, []));

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  return (
    <>
      <h1 className="title">Finances</h1>

      <div className="finance-top">
        <Treasury data={data} />
        <Payroll data={data} />
      </div>

      <Ledger transactions={data.transactions} />
    </>
  );
}

// La trésorerie, ce que les opérations ont rapporté et coûté, la valeur de l'effectif.
function Treasury({ data }) {
  const income = data.transactions.reduce((sum, t) => sum + Math.max(t.amount, 0), 0);
  const spent = data.transactions.reduce((sum, t) => sum + Math.min(t.amount, 0), 0);
  return (
    <div className="card finance-card">
      <span className="eyebrow">Trésorerie</span>
      <span className={`finance-balance${data.balance < 0 ? " finance-balance--neg" : ""}`}>
        {formatMoney(data.balance)}
      </span>
      <dl className="finance-facts">
        <div>
          <dt>Recettes cumulées</dt>
          <dd className="finance-in">{formatSignedMoney(income)}</dd>
        </div>
        <div>
          <dt>Dépenses cumulées</dt>
          <dd className="finance-out">{formatSignedMoney(spent)}</dd>
        </div>
        <div>
          <dt>Valeur de l'effectif</dt>
          <dd>
            {formatMoney(data.squad_value)} <span className="muted">· {data.squad_size} joueurs</span>
          </dd>
        </div>
      </dl>
    </div>
  );
}

// La masse salariale par saison : une barre en trois parts, puis la jauge du plafond.
function Payroll({ data }) {
  const parts = [
    { key: "pros", label: "Pros", value: data.player_wages },
    { key: "youth", label: "Espoirs", value: data.youth_wages },
    { key: "staff", label: "Staff", value: data.staff_wages },
  ];
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  const cap = data.salary_cap;
  const capShare = cap ? data.player_wages / cap : 0;
  return (
    <div className="card finance-card">
      <div className="finance-card__head">
        <span className="eyebrow">Masse salariale</span>
        <span className="muted">par saison</span>
      </div>
      <span className="finance-total">{formatMoney(total)}</span>
      <div className="payroll-bar" role="img" aria-label="Répartition de la masse salariale">
        {parts.map((part) => (
          <span
            key={part.key}
            className={`payroll-bar__part payroll-bar__part--${part.key}`}
            style={{ flexGrow: part.value }}
          />
        ))}
      </div>
      <ul className="payroll-legend">
        {parts.map((part) => (
          <li key={part.key}>
            <span className={`payroll-dot payroll-bar__part--${part.key}`} aria-hidden="true" />
            <span className="payroll-legend__label">{part.label}</span>
            <span className="num">{formatMoney(part.value)}</span>
            <span className="muted num">{total ? Math.round((part.value / total) * 100) : 0} %</span>
          </li>
        ))}
      </ul>
      {cap ? (
        <div className="cap-gauge">
          <div className="cap-gauge__head">
            <span>Plafond des pros</span>
            <span className="num">
              {formatMoney(data.player_wages)} / {formatMoney(cap)}
              <span className="muted">
                {" · "}
                {capShare >= 1 ? "plafond atteint" : `marge ${formatMoney(cap - data.player_wages)}`}
              </span>
            </span>
          </div>
          <div className={`cap-gauge__track${capShare > 0.95 ? " cap-gauge__track--tight" : ""}`}>
            <span style={{ width: `${Math.min(capShare, 1) * 100}%` }} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

const FLOWS = [
  { key: "all", label: "Tout" },
  { key: "in", label: "Recettes" },
  { key: "out", label: "Dépenses" },
];

// Toutes les opérations, de la plus récente à la plus ancienne par défaut.
function Ledger({ transactions }) {
  const [flow, setFlow] = useState("all");
  const phone = useMediaQuery(PHONE_QUERY);
  const filtered = useMemo(
    () =>
      flow === "all" ? transactions : transactions.filter((t) => (flow === "in" ? t.amount >= 0 : t.amount < 0)),
    [transactions, flow],
  );
  const { rows, sort, toggle } = useSort(filtered, { key: "id", dir: "desc" });
  const header = (key, label, first = "asc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={sort} onToggle={toggle} first={first} left={left} />
  );
  const empty = transactions.length === 0 ? "Aucune opération pour l'instant : joue une journée." : "Aucune opération de ce type.";

  return (
    <section className="section fill">
      <div className="ledger-head">
        <h2 className="eyebrow">Opérations · {filtered.length}</h2>
        <div className="segmented segmented--sm" role="group" aria-label="Filtrer les opérations">
          {FLOWS.map((item) => (
            <button key={item.key} type="button" aria-pressed={flow === item.key} onClick={() => setFlow(item.key)}>
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div className="card table-wrap">
        {phone ? (
          <ul className="ledger-list">
            {rows.map((t) => (
              <li key={t.id} className="ledger-item">
                <span className="ledger-item__main">
                  <span className="ledger-item__label">{t.label}</span>
                  <span className="muted">
                    {CATEGORIES[t.category] ?? t.category} · {formatNumericDate(t.date)}
                    {t.matchday ? ` · J${t.matchday}` : ""}
                  </span>
                </span>
                <span className="ledger-item__amounts">
                  <span className={t.amount >= 0 ? "amount finance-in" : "amount"}>{formatSignedMoney(t.amount)}</span>
                  <span className="muted num">{formatMoney(t.balance_after)}</span>
                </span>
              </li>
            ))}
            {rows.length === 0 && <li className="ledger-item muted">{empty}</li>}
          </ul>
        ) : (
          <table className="table">
            <thead>
              <tr>
                {header("id", "Date", "desc", true)}
                {header("matchday", "Journée", "desc")}
                {header("category", "Domaine", "asc", true)}
                {header("label", "Libellé", "asc", true)}
                {header("amount", "Montant", "desc")}
                {header("balance_after", "Solde", "desc")}
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td className="left muted">{formatNumericDate(t.date)}</td>
                  <td>{t.matchday ?? ""}</td>
                  <td className="left">
                    <span className="ledger-tag">{CATEGORIES[t.category] ?? t.category}</span>
                  </td>
                  <td className="left">{t.label}</td>
                  <td className={t.amount >= 0 ? "amount finance-in" : "amount"}>{formatSignedMoney(t.amount)}</td>
                  <td className="muted">{formatMoney(t.balance_after)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="left muted">
                    {empty}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
      <p className="muted ledger-note">Billetterie et sponsors à chaque journée, salaires en saison régulière.</p>
    </section>
  );
}
