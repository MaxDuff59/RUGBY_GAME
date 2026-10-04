import { useCallback, useState } from "react";

import { api } from "../api.js";
import Level from "../components/Level.jsx";
import { FACILITIES, formatInteger, formatMoney } from "../format.js";
import { useApi } from "../hooks/useApi.js";

export default function Facilities() {
  const { data, error, loading, setData } = useApi(useCallback(api.getFacilities, []));
  const [actionError, setActionError] = useState(null);

  async function upgrade(kind, cost) {
    const { label } = FACILITIES[kind];
    if (!window.confirm(`Améliorer ${label.toLowerCase()} pour ${formatMoney(cost)} ?`)) return;
    setActionError(null);
    try {
      setData(await api.upgradeFacility(kind));
    } catch (err) {
      setActionError(err);
    }
  }

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  return (
    <>
      <header className="page-head">
        <h1 className="title">Infrastructures</h1>
        <div className="stat">
          <span className="big-num">{formatMoney(data.balance)}</span>
          <span className="muted">trésorerie</span>
        </div>
      </header>

      {actionError && <p className="status--error">{actionError.message}</p>}

      <div className="tiles tiles--wide">
        {data.upgrades.map((upgrade) => {
          const info = FACILITIES[upgrade.kind];
          const isStadium = upgrade.kind === "stadium";
          return (
            <section key={upgrade.kind} className="card card--padded facility">
              <div>
                <h2 className="eyebrow">{info.label}</h2>
                <p className="muted" style={{ margin: "4px 0 0" }}>{info.scope}</p>
              </div>

              {isStadium ? (
                <div className="stat">
                  <span className="big-num">{formatInteger(upgrade.current)}</span>
                  <span className="muted">places</span>
                </div>
              ) : (
                <div className="stat">
                  <Level value={upgrade.current} label={`niveau ${upgrade.current} sur 5`} />
                  <span className="muted">niveau {upgrade.current} sur 5</span>
                </div>
              )}

              {upgrade.next === null ? (
                <p className="muted" style={{ margin: 0 }}>Niveau maximum atteint.</p>
              ) : (
                <div className="facility__upgrade">
                  <div>
                    <div style={{ fontWeight: 600 }}>
                      {isStadium ? `Agrandir à ${formatInteger(upgrade.next)} places` : `Passer au niveau ${upgrade.next}`}
                    </div>
                    <div className="muted">Coût : {formatMoney(upgrade.cost)}</div>
                  </div>
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={!upgrade.affordable}
                    title={upgrade.affordable ? undefined : "Trésorerie insuffisante"}
                    onClick={() => upgrade(upgrade.kind, upgrade.cost)}
                  >
                    {isStadium ? "Agrandir" : "Améliorer"}
                  </button>
                </div>
              )}
            </section>
          );
        })}
      </div>

      <p className="muted">
        Les effets sur le jeu (billetterie, progression des joueurs, jeunes issus de la formation)
        arriveront avec la saison journée par journée. Les travaux sont immédiats pour l'instant.
      </p>
    </>
  );
}
