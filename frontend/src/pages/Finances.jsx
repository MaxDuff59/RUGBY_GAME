import { useCallback } from "react";

import { api } from "../api.js";
import SortHeader from "../components/SortHeader.jsx";
import { CATEGORIES, formatMoney, formatNumericDate, formatSignedMoney } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";

export default function Finances() {
  const { data, error, loading } = useApi(useCallback(api.getFinances, []));

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const totalWages = data.player_wages + data.staff_wages;

  return (
    <>
      <h1 className="title">Finances</h1>

      <div className="tiles">
        <Tile label="Trésorerie" value={formatMoney(data.balance)} />
        <Tile label="Salaires des joueurs" value={formatMoney(data.player_wages)} note="par saison" />
        <Tile label="Salaires du staff" value={formatMoney(data.staff_wages)} note="par saison" />
        <Tile label="Masse salariale" value={formatMoney(totalWages)} note="par saison" />
        <Tile label="Valeur de l'effectif" value={formatMoney(data.squad_value)} note={`${data.squad_size} joueurs`} />
      </div>

      <Ledger transactions={data.transactions} />
    </>
  );
}

function Tile({ label, value, note }) {
  return (
    <div className="card tile">
      <span className="eyebrow">{label}</span>
      <span className="tile__value">{value}</span>
      {note && <span className="muted">{note}</span>}
    </div>
  );
}

// Toutes les opérations, de la plus récente à la plus ancienne par défaut.
function Ledger({ transactions }) {
  const { rows, sort, toggle } = useSort(transactions, { key: "id", dir: "desc" });
  const header = (key, label, first = "asc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={sort} onToggle={toggle} first={first} left={left} />
  );

  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Opérations · {transactions.length}</h2>
        <span className="muted">Billetterie et sponsors à chaque journée, salaires en saison régulière</span>
      </div>
      <div className="card table-wrap">
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
                <td className="left">{CATEGORIES[t.category] ?? t.category}</td>
                <td className="left">{t.label}</td>
                <td className={t.amount >= 0 ? "amount amount--in" : "amount"}>{formatSignedMoney(t.amount)}</td>
                <td className="muted">{formatMoney(t.balance_after)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="left muted">Aucune opération pour l'instant : joue une journée.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
