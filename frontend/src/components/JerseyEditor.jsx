import { lazy, Suspense, useState } from "react";

import { clubInfo } from "../clubs.js";
import { formatMoney } from "../format.js";
import { KITS, PALETTE, PATTERNS, defaultJersey, distance, sameJersey } from "../jersey.js";
import { PLACEMENTS } from "../sponsors.js";
import JerseyFlat from "./JerseyFlat.jsx";
import Modal from "./Modal.jsx";
import SponsorLogo from "./SponsorLogo.jsx";

// three.js n'est chargé qu'à l'ouverture de l'éditeur.
const JerseyStudio = lazy(() => import("./JerseyStudio.jsx"));

const COLOR_ROLES = [
  { key: "base", label: "Fond" },
  { key: "motif", label: "Motif" },
  { key: "trim", label: "Col" },
];

// Éditeur d'un maillot (carte « Maillots » des infrastructures), pour une tenue `kind`
// (home, away, third) : le maillot en 3D à gauche, à droite le motif, les trois couleurs
// et les sponsors (`sponsors` : contrats, bibliothèque et barèmes de l'API ; les mêmes
// sur les trois tenues). Rien n'est enregistré avant « Enregistrer » ; revenir aux
// couleurs du club efface le maillot enregistré.
export default function JerseyEditor({ clubName, kind, saved, sponsors, onSave, onClose }) {
  const clubJersey = defaultJersey(clubName, kind);
  const [draft, setDraft] = useState(saved ?? clubJersey);
  const [deals, setDeals] = useState(sponsors.deals.map(({ sponsor, placement }) => ({ sponsor, placement })));
  const [choosing, setChoosing] = useState(null); // emplacement dont on choisit le sponsor
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [role, setRole] = useState("base"); // couleur en cours de choix
  const current = saved ?? clubJersey;
  const dealsChanged = !sameDeals(deals, sponsors.deals);
  const changed = !sameJersey(draft, current) || dealsChanged;
  const library = new Map(sponsors.library.map((s) => [s.id, s]));

  const swatches = unique([...clubInfo(clubName).colors, ...PALETTE]);
  const value = draft[role].toUpperCase();
  const set = (patch) => setDraft((previous) => ({ ...previous, ...patch }));

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave(sameJersey(draft, clubJersey) ? null : draft, dealsChanged ? deals : null);
    } catch (exception) {
      setError(exception.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="review__head">
        <div>
          <p className="eyebrow">Infrastructures</p>
          <h2 className="affair__title">Maillot {KITS.find((k) => k.kind === kind).label.toLowerCase()}</h2>
        </div>
        <div className="viewer__head-right">
          <button type="button" className="button" onClick={onClose}>
            Fermer
          </button>
        </div>
      </div>

      <div className="viewer">
        <div className="viewer__scene card">
          <Suspense fallback={<p className="status">Chargement du maillot…</p>}>
            <JerseyStudio jersey={draft} clubName={clubName} deals={deals} library={sponsors.library} />
          </Suspense>
        </div>

        <aside className="viewer__panel jersey-panel">
          <p className="eyebrow">Motif</p>
          <div className="jersey-patterns">
            {PATTERNS.map((pattern) => (
              <button
                key={pattern.kind}
                type="button"
                className="jersey-pattern"
                aria-pressed={draft.pattern === pattern.kind}
                onClick={() => set({ pattern: pattern.kind })}
              >
                <JerseyFlat
                  jersey={{ ...draft, pattern: pattern.kind }}
                  clubName={clubName}
                  size={56}
                  details={false}
                  title={pattern.label}
                />
                <span>{pattern.label}</span>
              </button>
            ))}
          </div>

          <div className="jersey-colors">
            <p className="eyebrow">Couleurs</p>
            <div className="jersey-roles">
              {COLOR_ROLES.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  className="jersey-role"
                  aria-pressed={role === r.key}
                  onClick={() => setRole(r.key)}
                >
                  <span className="jersey-role__dot" style={{ background: draft[r.key] }} />
                  {r.label}
                </button>
              ))}
            </div>
            {role === "motif" && draft.pattern === "plain" && (
              <p className="muted jersey-colors__note">Sans effet sur un maillot uni.</p>
            )}
            <div className="jersey-swatches">
              {swatches.map((color) => (
                <button
                  key={color}
                  type="button"
                  className="jersey-swatch"
                  style={{ background: color }}
                  aria-pressed={value === color}
                  aria-label={color}
                  title={color}
                  onClick={() => set({ [role]: color })}
                />
              ))}
              <label
                className="jersey-swatch jersey-swatch--custom"
                title="Autre couleur"
                aria-pressed={!swatches.includes(value)}
                style={swatches.includes(value) ? undefined : { background: value }}
              >
                <input
                  type="color"
                  value={value.toLowerCase()}
                  aria-label="Autre couleur"
                  onChange={(event) => set({ [role]: event.target.value.toUpperCase() })}
                />
              </label>
            </div>
          </div>

          {choosing ? (
            <SponsorPicker
              placement={choosing}
              sponsors={sponsors}
              deals={deals}
              onPick={(id) => {
                setDeals((previous) => [
                  ...previous.filter((d) => d.placement !== choosing),
                  ...(id ? [{ sponsor: id, placement: choosing }] : []),
                ]);
                setChoosing(null);
              }}
              onBack={() => setChoosing(null)}
            />
          ) : (
            <DealList sponsors={sponsors} deals={deals} library={library} onChoose={setChoosing} />
          )}

          {error && <p className="status status--error">{error}</p>}
          <div className="jersey-actions">
            <button
              type="button"
              className="button"
              disabled={sameJersey(draft, clubJersey)}
              onClick={() => setDraft(clubJersey)}
            >
              Couleurs du club
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={!changed || saving}
              onClick={save}
            >
              {changed ? "Enregistrer" : "Enregistré"}
            </button>
          </div>
        </aside>
      </div>
    </Modal>
  );
}

// Les sponsors en place, emplacement par emplacement, puis ce qu'ils rapportent et ce
// qu'en pensent les supporters.
function DealList({ sponsors, deals, library, onChoose }) {
  const revenue = deals.reduce((sum, d) => sum + dealRevenue(d, sponsors), 0);
  const mood = dealsMood(deals, sponsors);
  const full = deals.length >= sponsors.max_deals;
  return (
    <div className="jersey-colors">
      <p className="eyebrow">Sponsors</p>
      <ul className="deals">
        {PLACEMENTS.map((placement) => {
          const deal = deals.find((d) => d.placement === placement);
          const sponsor = deal && library.get(deal.sponsor);
          const blocked = !deal && full;
          return (
            <li key={placement} className={deal ? "deal" : "deal deal--empty"}>
              <span className="deal__place">
                {sponsors.placements[placement]}
                <span className="muted"> · ×{sponsors.shares[placement].toLocaleString("fr-FR")}</span>
              </span>
              {sponsor ? (
                <span className="deal__who">
                  <SponsorLogo sponsor={sponsor} height={20} />
                  <span className="muted num">+{formatMoney(dealRevenue(deal, sponsors))}</span>
                </span>
              ) : (
                <span className="muted">{blocked ? `${sponsors.max_deals} logos au plus` : "Libre"}</span>
              )}
              <button
                type="button"
                className="button button--small"
                disabled={blocked}
                onClick={() => onChoose(placement)}
              >
                {deal ? "Changer" : "Choisir"}
              </button>
            </li>
          );
        })}
      </ul>
      <ul className="viewer__facts deals__facts">
        <li>
          <span className="muted">Par match</span>
          <strong className="num">{revenue ? `+${formatMoney(revenue)}` : "—"}</strong>
        </li>
        <li>
          <span className="muted">Ferveur des supporters</span>
          <strong className="num">{moodLabel(mood)}</strong>
        </li>
      </ul>
      <p className="muted jersey-colors__note" style={{ marginTop: 8 }}>
        Les supporters jugent le maillot : une marque mal vue pèse sur leur ferveur, et
        trois logos font un maillot sapin de Noël ({moodLabel(sponsors.crowded_mood)}). La
        ferveur règle l'affluence au stade.
      </p>
    </div>
  );
}

// La bibliothèque, pour choisir le sponsor d'un emplacement.
function SponsorPicker({ placement, sponsors, deals, onPick, onBack }) {
  const current = deals.find((d) => d.placement === placement)?.sponsor;
  const share = sponsors.shares[placement];
  return (
    <div className="jersey-colors">
      <div className="deals__head">
        <p className="eyebrow">{sponsors.placements[placement]}</p>
        <button type="button" className="button button--small" onClick={onBack}>
          Retour
        </button>
      </div>
      <ul className="sponsor-list">
        {current && (
          <li>
            <button type="button" className="sponsor-row" onClick={() => onPick(null)}>
              <span className="sponsor-row__name muted">Retirer le sponsor</span>
            </button>
          </li>
        )}
        {sponsors.library.map((sponsor) => {
          const elsewhere = deals.find((d) => d.sponsor === sponsor.id && d.placement !== placement);
          const taken = sponsor.id === current;
          return (
            <li key={sponsor.id}>
              <button
                type="button"
                className="sponsor-row"
                aria-pressed={taken}
                disabled={Boolean(elsewhere) || taken}
                title={elsewhere ? `Déjà sur le maillot (${sponsors.placements[elsewhere.placement].toLowerCase()})` : undefined}
                onClick={() => onPick(sponsor.id)}
              >
                <SponsorLogo sponsor={sponsor} height={26} plate />
                <span className="sponsor-row__text">
                  <span className="sponsor-row__name">
                    {sponsor.name}
                    {taken && <span className="muted"> · en place</span>}
                    {elsewhere && <span className="muted"> · déjà sur le maillot</span>}
                  </span>
                  <span className="muted">
                    {sponsor.sector} · {sponsor.image_label}
                    {sponsor.mood !== 0 && ` (${moodLabel(sponsor.mood)})`}
                  </span>
                </span>
                <span className="num sponsor-row__money">+{formatMoney(Math.round(sponsor.budget * share))}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function dealRevenue(deal, sponsors) {
  const sponsor = sponsors.library.find((s) => s.id === deal.sponsor);
  return sponsor ? Math.round(sponsor.budget * sponsors.shares[deal.placement]) : 0;
}

function dealsMood(deals, sponsors) {
  const mood = deals.reduce((sum, d) => sum + (sponsors.library.find((s) => s.id === d.sponsor)?.mood ?? 0), 0);
  return mood + (deals.length >= sponsors.max_deals ? sponsors.crowded_mood : 0);
}

// "+0,3", "−1,5" ou "—".
function moodLabel(mood) {
  if (!mood) return "—";
  const text = Math.abs(mood).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
  return mood > 0 ? `+${text}` : `−${text}`;
}

function sameDeals(a, b) {
  const key = (deals) => deals.map((d) => `${d.placement}:${d.sponsor}`).sort().join("|");
  return key(a) === key(b);
}

// Les couleurs du club d'abord, puis celles de la palette qui ne leur ressemblent pas trop.
function unique(colors) {
  const kept = [];
  for (const color of colors.map((c) => c.toUpperCase())) {
    if (!kept.some((other) => distance(other, color) < 40)) kept.push(color);
  }
  return kept;
}
