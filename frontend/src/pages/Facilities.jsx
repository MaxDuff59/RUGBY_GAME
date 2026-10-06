import { useCallback, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import FacilityViewer from "../components/FacilityViewer.jsx";
import JerseyEditor from "../components/JerseyEditor.jsx";
import JerseyFlat from "../components/JerseyFlat.jsx";
import SponsorLogo from "../components/SponsorLogo.jsx";
import Level from "../components/Level.jsx";
import { FACILITIES, formatInteger, formatMoney } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { KITS, PATTERNS, defaultJersey } from "../jersey.js";

// Ce que les travaux changent, en une phrase, pour la fenêtre de confirmation.
const EFFECTS = {
  stadium: "Plus de places : davantage de billetterie les jours de match, et des sponsors plus généreux.",
  training: "Les pros progressent plus vite à chaque intersaison.",
  academy: "Les espoirs progressent plus vite, et davantage de jeunes entrent au centre chaque intersaison.",
};

export default function Facilities() {
  const { data, error, loading, setData } = useApi(useCallback(api.getFacilities, []));
  const confirm = useConfirm();
  const [viewing, setViewing] = useState(null); // infrastructure ouverte dans la fenêtre « Voir »
  const [designing, setDesigning] = useState(null); // tenue ouverte dans l'éditeur de maillot
  const { career } = useOutletContext();

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

  // Installer un aménagement du catalogue dans une tribune (fenêtre « Voir » du stade).
  function install(stand, amenity) {
    confirm.ask({
      eyebrow: `Stade · ${stand.label}`,
      title: amenity.label,
      text: `${amenity.effect}, dès le prochain match.`,
      rows: [
        { label: "Emplacements", from: stand.amenities.length, to: stand.amenities.length + 1, hint: `sur ${stand.slots}` },
        { label: "Coût", value: formatMoney(amenity.cost) },
        { label: "Trésorerie", from: formatMoney(data.balance), to: formatMoney(data.balance - amenity.cost) },
      ],
      warning: "L'installation est immédiate et la dépense n'est pas remboursable.",
      confirmLabel: `Installer pour ${formatMoney(amenity.cost)}`,
      onConfirm: async () => setData(await api.installAmenity(stand.side, amenity.kind)),
    });
  }

  // Acheter le maillot third, qu'on peut ensuite dessiner comme les autres.
  function buyThirdKit() {
    const cost = data.jerseys.third_kit_cost;
    confirm.ask({
      eyebrow: "Maillots · Third",
      title: "Déverrouiller le maillot third",
      text: "Une troisième tenue, à dessiner comme les autres : motif et couleurs.",
      rows: [
        { label: "Coût", value: formatMoney(cost) },
        { label: "Trésorerie", from: formatMoney(data.balance), to: formatMoney(data.balance - cost) },
      ],
      warning: "La dépense est immédiate et n'est pas remboursable.",
      confirmLabel: `Déverrouiller pour ${formatMoney(cost)}`,
      onConfirm: async () => setData(await api.buyThirdKit()),
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

      <div className="tiles tiles--wide">
        {data.upgrades.map((upgrade) => {
          const info = FACILITIES[upgrade.kind];
          const isStadium = upgrade.kind === "stadium";
          return (
            <section key={upgrade.kind} className="card card--padded facility">
              <div className="facility__head">
                <div>
                  <h2 className="eyebrow">{info.label}</h2>
                  <p className="muted" style={{ margin: "4px 0 0" }}>{info.scope}</p>
                </div>
                <button type="button" className="button button--small" onClick={() => setViewing(upgrade.kind)}>
                  Voir
                </button>
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

      <JerseyCard
        clubName={career.club_name}
        jerseys={data.jerseys}
        sponsors={data.sponsors}
        onDesign={setDesigning}
        onBuy={buyThirdKit}
      />

      <p className="muted">
        Le stade fixe la billetterie et les sponsors ; « Voir » ouvre ses tribunes pour y installer
        panneaux, buvettes ou loges. Le centre d'entraînement accélère la progression des pros, le
        centre de formation celle des espoirs et le nombre de jeunes qui entrent chaque intersaison.
        Les travaux sont immédiats. Les maillots domicile et extérieur se dessinent gratuitement,
        autant de fois qu'on veut ; le third se déverrouille une fois, contre paiement. Les
        sponsors du maillot paient à chaque match, mais les supporters jugent le résultat.
      </p>

      {viewing && (
        <FacilityViewer
          kind={viewing}
          data={data}
          onClose={() => setViewing(null)}
          onInstall={install}
          onUpgrade={improve}
        />
      )}
      {designing && (
        <JerseyEditor
          clubName={career.club_name}
          kind={designing}
          saved={data.jerseys[designing]}
          sponsors={data.sponsors}
          onSave={async (jersey, deals) => {
            // Le maillot si son dessin a changé, puis les sponsors s'ils ont changé.
            let next = data;
            if (jersey !== null || data.jerseys[designing] !== null) {
              next = await (jersey ? api.saveJersey(designing, jersey) : api.resetJersey(designing));
            }
            if (deals) next = await api.setSponsors(deals);
            setData(next);
          }}
          onClose={() => setDesigning(null)}
        />
      )}
      {/* Après la fenêtre « Voir » dans le DOM : la confirmation passe au-dessus. */}
      {confirm.dialog}
    </>
  );
}

// Les trois tenues du club, de face et de dos, chacune avec l'accès à son éditeur ;
// le third est à déverrouiller (payant) tant qu'il ne l'est pas.
function JerseyCard({ clubName, jerseys, sponsors, onDesign, onBuy }) {
  const byId = new Map(sponsors.library.map((s) => [s.id, s]));
  return (
    <section className="card card--padded jersey-card">
      <h2 className="eyebrow" style={{ margin: 0 }}>Maillots</h2>
      <div className="jersey-kits">
        {KITS.map(({ kind, label }) => {
          const locked = kind === "third" && !jerseys.third_kit;
          const jersey = jerseys[kind] ?? defaultJersey(clubName, kind);
          const pattern = PATTERNS.find((p) => p.kind === jersey.pattern)?.label;
          return (
            <div key={kind} className={`jersey-kit${locked ? " jersey-kit--locked" : ""}`}>
              <div className="jersey-card__views">
                <JerseyFlat jersey={jersey} clubName={clubName} size={84} sponsors={sponsors} />
                <JerseyFlat jersey={jersey} clubName={clubName} size={84} sponsors={sponsors} back />
              </div>
              <div className="jersey-card__text">
                <div style={{ fontWeight: 600 }}>{label}</div>
                {locked ? (
                  <div className="muted">Coût : {formatMoney(jerseys.third_kit_cost)}</div>
                ) : (
                  <div className="muted">
                    {pattern}
                    {jerseys[kind] ? "" : " · couleurs du club"}
                  </div>
                )}
              </div>
              {locked ? (
                <button
                  type="button"
                  className="button button--primary"
                  disabled={!jerseys.third_kit_affordable}
                  title={jerseys.third_kit_affordable ? undefined : "Trésorerie insuffisante"}
                  onClick={onBuy}
                >
                  Déverrouiller
                </button>
              ) : (
                <button type="button" className="button" onClick={() => onDesign(kind)}>
                  Personnaliser
                </button>
              )}
            </div>
          );
        })}
      </div>
      <div className="jersey-sponsors">
        <span className="eyebrow">Sponsors</span>
        {sponsors.deals.length ? (
          <>
            {sponsors.deals.map((deal) => (
              <span key={deal.placement} className="jersey-sponsors__deal">
                <SponsorLogo sponsor={byId.get(deal.sponsor)} height={20} />
                <span className="muted">{sponsors.placements[deal.placement].toLowerCase()}</span>
              </span>
            ))}
            <span className="num">+{formatMoney(sponsors.revenue)} par match</span>
            {sponsors.mood !== 0 && (
              <span className="muted">
                · ferveur {sponsors.mood > 0 ? "+" : "−"}
                {Math.abs(sponsors.mood).toLocaleString("fr-FR")}
              </span>
            )}
          </>
        ) : (
          <span className="muted">Aucun : choisis-les dans « Personnaliser », ils paient à chaque match.</span>
        )}
      </div>
    </section>
  );
}
