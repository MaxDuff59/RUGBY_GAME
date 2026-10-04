import { useCallback } from "react";

import { api } from "../api.js";
import { formatMoney } from "../format.js";
import { useApi } from "../hooks/useApi.js";

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

      <section className="section">
        <h2 className="eyebrow">À venir</h2>
        <div className="card card--padded">
          <p style={{ margin: 0 }}>
            Les recettes (billetterie selon le stade, sponsors) et les dépenses (salaires) seront
            comptées à chaque journée de championnat, quand la saison se jouera journée par journée.
            Pour l'instant, la trésorerie ne bouge qu'avec tes décisions : transferts, staff,
            infrastructures.
          </p>
        </div>
      </section>
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
