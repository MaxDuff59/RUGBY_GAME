import { useCallback } from "react";

import { api } from "../api.js";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import Level from "../components/Level.jsx";
import { FACILITIES, formatInteger, formatMoney } from "../format.js";
import { useApi } from "../hooks/useApi.js";

// Ce que les travaux changent, en une phrase, pour la fenêtre de confirmation.
const EFFECTS = {
  stadium: "Plus de places : davantage de billetterie les jours de match, et des sponsors plus généreux.",
  training: "Les pros progressent plus vite à chaque intersaison.",
  academy: "Les espoirs progressent plus vite, et davantage de jeunes entrent au centre chaque intersaison.",
};

export default function Facilities() {
  const { data, error, loading, setData } = useApi(useCallback(api.getFacilities, []));
  const confirm = useConfirm();

  function improve(upgrade) {
    const info = FACILITIES[upgrade.kind];
    const isStadium = upgrade.kind === "stadium";
    const verb = isStadium ? "Agrandir" : "Améliorer";
    confirm.ask({
      eyebrow: `Infrastructures · ${info.label}`,
      title: isStadium ? `Agrandir à ${formatInteger(upgrade.next)} places` : `Passer au niveau ${upgrade.next}`,
      text: EFFECTS[upgrade.kind],
      rows: [
        isStadium
          ? { label: "Capacité", from: formatInteger(upgrade.current), to: formatInteger(upgrade.next), hint: "places" }
          : { label: "Niveau", from: upgrade.current, to: upgrade.next, hint: "sur 5" },
        { label: "Coût des travaux", value: formatMoney(upgrade.cost) },
        { label: "Trésorerie", from: formatMoney(data.balance), to: formatMoney(data.balance - upgrade.cost) },
      ],
      warning: "Les travaux sont immédiats et la dépense n'est pas remboursable.",
      confirmLabel: `${verb} pour ${formatMoney(upgrade.cost)}`,
      onConfirm: async () => setData(await api.upgradeFacility(upgrade.kind)),
    });
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

      {confirm.dialog}

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
                    onClick={() => improve(upgrade)}
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
        Le stade fixe la billetterie et les sponsors. Le centre d'entraînement accélère la progression des
        pros, le centre de formation celle des espoirs et le nombre de jeunes qui entrent chaque
        intersaison. Les travaux sont immédiats.
      </p>
    </>
  );
}
