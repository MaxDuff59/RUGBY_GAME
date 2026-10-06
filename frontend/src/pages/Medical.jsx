import { useCallback } from "react";
import { Link } from "react-router-dom";

import { api } from "../api.js";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import Level from "../components/Level.jsx";
import {
  INJURY_SOURCES,
  POSITIONS,
  PROTOCOLS,
  SEVERITIES,
  formatMoney,
  formatNumericDate,
  formatPercent,
  formatShortDate,
  formatWeeks,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";

// Infirmerie : les blessés (avec le protocole à choisir), les joueurs revenus
// sous surveillance, et le dossier médical du club.
export default function Medical() {
  const { data, error, loading, setData } = useApi(useCallback(api.getMedical, []));
  const confirm = useConfirm();

  function choose(injuryCase, option) {
    const { player, injury } = injuryCase;
    const protocol = PROTOCOLS[option.protocol];
    confirm.ask({
      eyebrow: `Protocole · ${player.name} · ${POSITIONS[player.position].label}`,
      title: protocol.label,
      text: `${injury.kind}, ${INJURY_SOURCES[injury.source]} le ${formatShortDate(injury.occurred_on)}. ${protocol.scope}.`,
      rows: [
        { label: "Retour à la compétition", value: formatNumericDate(option.return_date), hint: formatWeeks(option.weeks) },
        { label: "Risque de rechute", value: formatPercent(option.relapse_risk), hint: "par match, le temps de la reprise" },
        option.cost > 0
          ? { label: "Trésorerie", from: formatMoney(data.balance), to: formatMoney(data.balance - option.cost), hint: `soins : ${formatMoney(option.cost)}` }
          : { label: "Coût des soins", value: "Gratuit" },
      ],
      warning: "Ce choix est définitif : on ne change plus de protocole en cours de convalescence.",
      confirmLabel: "Choisir ce protocole",
      onConfirm: async () => setData(await api.chooseProtocol(injury.id, option.protocol)),
    });
  }

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const undecided = data.injured.filter((c) => !c.injury.protocol_chosen).length;

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Médical</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Au {formatNumericDate(data.today)}. Un blessé manque les matchs jusqu'à sa date de retour,
            puis reste fragile {formatWeeks(data.fragile_weeks)} : chaque match joué peut provoquer une rechute.
          </p>
        </div>
        <div className="page-head__stats">
          <Stat value={data.injured.length} label={undecided ? `blessés · ${undecided} protocole${undecided > 1 ? "s" : ""} à choisir` : "blessés"} />
          <Stat value={`${data.available}/${data.squad_size}`} label="joueurs aptes" />
          <Stat value={formatMoney(data.balance)} label="trésorerie" />
        </div>
      </header>

      {confirm.dialog}

      <section className="section fill">
        <div className="section__head">
          <h2 className="eyebrow">Infirmerie · {data.injured.length}</h2>
          <span className="muted">Du retour le plus proche au plus lointain</span>
        </div>
        <div className="card">
          {data.injured.length === 0 && <p className="table__note">Personne à l'infirmerie : tout l'effectif est apte.</p>}
          {data.injured.map((injuryCase) => (
            <InjuredPlayer key={injuryCase.injury.id} injuryCase={injuryCase} onChoose={choose} />
          ))}
        </div>
      </section>

      <div className="two-col">
        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Sous surveillance · {data.fragile.length}</h2>
            <span className="muted">Revenus de blessure, risque de rechute</span>
          </div>
          <div className="card">
            {data.fragile.length === 0 ? (
              <p className="table__note">Aucun joueur en reprise.</p>
            ) : (
              <ul className="injury-list">
                {data.fragile.map(({ player, injury }) => (
                  <li key={injury.id}>
                    <span className="tag tag--fragile">Fragile</span>
                    <span style={{ fontWeight: 600 }}>{player.name}</span>
                    <span className="muted">{POSITIONS[player.position].label}</span>
                    <span className="muted">
                      {injury.kind} · rechute {formatPercent(injury.relapse_risk)} par match jusqu'au{" "}
                      {formatShortDate(injury.fragile_until)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Staff médical</h2>
            <Link to="/staff" className="muted">Gérer le staff</Link>
          </div>
          <div className="card card--padded" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <StaffLine label="Kinésithérapeute" level={data.physio_level} scope="Raccourcit la convalescence (jusqu'à −20 %)" />
            <StaffLine label="Médecin" level={data.doctor_level} scope="Réduit le risque de rechute (jusqu'à −40 %)" />
          </div>
        </section>
      </div>

      <History cases={data.history} />
    </>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="big-num">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}

function StaffLine({ label, level, scope }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "4px 12px" }}>
      <span style={{ fontWeight: 600, minWidth: 140 }}>{label}</span>
      {level > 0 ? <Level value={level} label={`niveau ${level} sur 5`} /> : <span className="muted">Poste vacant</span>}
      <span className="muted">{scope}</span>
    </div>
  );
}

function SeverityTag({ severity }) {
  return <span className={`tag tag--${severity}`}>{SEVERITIES[severity].label}</span>;
}

// Un blessé : son état, et les trois protocoles tant que le manager n'a pas tranché.
function InjuredPlayer({ injuryCase, onChoose }) {
  const { player, injury, options } = injuryCase;
  return (
    <div>
      <ul className="injury-list">
        <li>
          <SeverityTag severity={injury.severity} />
          {injury.relapse && <span className="tag tag--injured">Rechute</span>}
          <span style={{ fontWeight: 600 }}>{player.name}</span>
          <span className="muted">
            {POSITIONS[player.position].label} · {player.age} ans
          </span>
          <span>
            {injury.kind}, {INJURY_SOURCES[injury.source]} le {formatShortDate(injury.occurred_on)}
          </span>
          <span className="muted">
            {injury.protocol_chosen ? PROTOCOLS[injury.protocol].label : "Protocole à choisir"} · retour le{" "}
            <strong>{formatShortDate(injury.return_date)}</strong> ({formatWeeks(injury.weeks_left)}
            {injury.weeks_left !== injury.weeks_total ? ` sur ${injury.weeks_total}` : ""})
            {injury.protocol_chosen && ` · rechute ${formatPercent(injury.relapse_risk)} par match`}
          </span>
          {injuryCase.joker && (
            <span>
              <span className="tag tag--light">Joker</span>{" "}
              <Link to={`/joueurs/${injuryCase.joker.id}`}>{injuryCase.joker.name}</Link>
            </span>
          )}
          {injuryCase.joker_allowed && (
            <Link to="/transferts" state={{ way: "free" }} className="button button--small">
              Recruter un joker médical
            </Link>
          )}
        </li>
      </ul>
      {options.length > 0 && (
        <div className="protocols">
          {options.map((option) => (
            <button
              key={option.protocol}
              type="button"
              className="protocol"
              disabled={!option.affordable}
              title={option.affordable ? undefined : "Trésorerie insuffisante"}
              onClick={() => onChoose(injuryCase, option)}
            >
              <span className="protocol__name">{PROTOCOLS[option.protocol].label}</span>
              <span className="protocol__line">
                Retour le <strong>{formatShortDate(option.return_date)}</strong> · {formatWeeks(option.weeks)}
              </span>
              <span className="protocol__line">
                Rechute <strong>{formatPercent(option.relapse_risk)}</strong> par match
                {option.cost > 0 ? <> · <strong>{formatMoney(option.cost)}</strong></> : " · gratuit"}
              </span>
              <span className="protocol__line">{PROTOCOLS[option.protocol].scope}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function History({ cases }) {
  return (
    <section className="section fill">
      <div className="section__head">
        <h2 className="eyebrow">Dossier médical · {cases.length}</h2>
        <span className="muted">Blessures guéries, de la plus récente à la plus ancienne</span>
      </div>
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col" className="left">Joueur</th>
              <th scope="col" className="left">Blessure</th>
              <th scope="col" className="left">Gravité</th>
              <th scope="col" className="left">Origine</th>
              <th scope="col">Du</th>
              <th scope="col">Au</th>
              <th scope="col">Durée</th>
              <th scope="col" className="left">Protocole</th>
            </tr>
          </thead>
          <tbody>
            {cases.map(({ player, injury }) => (
              <tr key={injury.id}>
                <td className="left">
                  <div className="person">
                    <PlayerAvatar size={32} />
                    <div>
                      <div style={{ fontWeight: 600 }}>{player.name}</div>
                      <div className="muted">{POSITIONS[player.position].label}</div>
                    </div>
                  </div>
                </td>
                <td className="left">
                  {injury.kind}
                  {injury.relapse && <span className="muted"> · rechute</span>}
                </td>
                <td className="left"><SeverityTag severity={injury.severity} /></td>
                <td className="left muted">{INJURY_SOURCES[injury.source]}</td>
                <td className="muted">{formatNumericDate(injury.occurred_on)}</td>
                <td className="muted">{formatNumericDate(injury.return_date)}</td>
                <td>{formatWeeks(injury.weeks_total)}</td>
                <td className="left muted">{PROTOCOLS[injury.protocol].label}</td>
              </tr>
            ))}
            {cases.length === 0 && (
              <tr>
                <td colSpan={8} className="left muted">Aucune blessure guérie pour l'instant.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
