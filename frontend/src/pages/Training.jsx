import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api.js";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import SortHeader from "../components/SortHeader.jsx";
import {
  ATTRIBUTES,
  POSITIONS,
  TRAINING_INTENSITIES,
  TRAINING_THEMES,
  formatGain,
  formatNote,
  formatPotential,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";

const ATTRIBUTE_LABELS = Object.fromEntries(ATTRIBUTES.map((attr) => [attr.key, attr.label.toLowerCase()]));

// « +25 % », « −40 % » : un multiplicateur lu comme un écart.
const percent = (factor) => {
  const value = Math.round((factor - 1) * 100);
  return value === 0 ? "=" : `${value > 0 ? "+" : "−"}${Math.abs(value)} %`;
};
const signed = (value) => (value === 0 ? "=" : `${value > 0 ? "+" : "−"}${String(Math.abs(value)).replace(".", ",")}`);

// L'entraînement : le rythme de la semaine et son thème, à gauche ; à droite, qui
// progresse cette saison (pros et espoirs), avec le potentiel estimé de chacun.
export default function Training() {
  const { data, error, loading, setData } = useApi(useCallback(api.getTraining, []));
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  async function choose(change) {
    setBusy(true);
    setActionError(null);
    try {
      setData(await api.setTraining(change));
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Entraînement</h1>
          <p className="muted page-head__sub">
            Le rythme et le thème valent pour chaque semaine, jusqu'à ce que tu les changes. Les joueurs
            progressent match après match vers leur potentiel.
          </p>
        </div>
      </header>
      {actionError && <p className="status--error">{actionError.message}</p>}

      <div className="two-col fill training">
        <section className="section training__plan">
          <h2 className="eyebrow">Rythme de la semaine</h2>
          <div className="training__options">
            {data.intensities.map((option) => (
              <button
                key={option.key}
                type="button"
                className="training__option card"
                aria-pressed={data.intensity === option.key}
                disabled={busy}
                onClick={() => choose({ intensity: option.key })}
              >
                <span className="training__name">{TRAINING_INTENSITIES[option.key].label}</span>
                <span className="muted training__scope">{TRAINING_INTENSITIES[option.key].scope}</span>
                <span className="training__effects">
                  <Effect label="Progression" value={percent(option.pace)} />
                  <Effect label="Fraîcheur" value={signed(option.freshness)} />
                  <Effect label="Blessures" value={percent(option.injuries)} invert />
                </span>
              </button>
            ))}
          </div>

          <h2 className="eyebrow">Thème</h2>
          <div className="training__options training__options--themes">
            {data.themes.map((option) => (
              <button
                key={option.key}
                type="button"
                className="training__option card"
                aria-pressed={data.theme === option.key}
                disabled={busy}
                onClick={() => choose({ theme: option.key })}
              >
                <span className="training__name">{TRAINING_THEMES[option.key].label}</span>
                <span className="muted training__scope">
                  {option.focus.length > 0
                    ? `Progrès en priorité : ${option.focus.map((key) => ATTRIBUTE_LABELS[key]).join(", ")}.`
                    : "Chacun progresse là où son poste le demande."}
                </span>
                <span className="training__scope">{TRAINING_THEMES[option.key].match}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Qui progresse</h2>
            <span className="muted">
              centre d'entraînement niveau {data.training_level} · formation niveau {data.academy_level}
            </span>
          </div>
          <Progress players={data.players} />
        </section>
      </div>
    </>
  );
}

function Effect({ label, value, invert = false }) {
  const good = value.startsWith("+") !== invert && value !== "=";
  const bad = value !== "=" && !good;
  return (
    <span className="training__effect">
      <span className="muted">{label}</span>
      <span className={`num${good ? " training__effect--good" : bad ? " training__effect--bad" : ""}`}>{value}</span>
    </span>
  );
}

function Progress({ players }) {
  const navigate = useNavigate();
  const { rows, sort, toggle } = useSort(players, { key: "season_gain", dir: "desc" });
  const header = (key, label, first = "desc", left = false, title) => (
    <SortHeader sortKey={key} label={label} sort={sort} onToggle={toggle} first={first} left={left} title={title} />
  );
  return (
    <div className="card table-wrap">
      <table className="table">
        <thead>
          <tr>
            {header("name", "Joueur", "asc", true)}
            {header("age", "Âge", "asc")}
            {header("overall", "Note")}
            {header("potential_high", "Pot.", "desc", false, "Potentiel estimé par le staff")}
            {header("season_gain", "Prog.", "desc", false, "Points d'attributs gagnés cette saison")}
          </tr>
        </thead>
        <tbody>
          {rows.map((player) => (
            <tr key={player.id} className="table__row--clickable" tabIndex={0} onClick={() => navigate(`/joueurs/${player.id}`)}>
              <td className="left">
                <div className="squad__name">
                  <PlayerAvatar src={player.photo} size={26} />
                  <span>
                    {player.name}
                    <span className="muted">
                      {" · "}
                      {POSITIONS[player.position].label}
                      {player.squad === "youth" && " · espoir"}
                    </span>
                  </span>
                </div>
              </td>
              <td className="muted">{player.age}</td>
              <td className="note">{formatNote(player.overall)}</td>
              <td>{formatPotential(player)}</td>
              <td className={player.season_gain > 0 ? "cell--strong" : "muted"}>{formatGain(player.season_gain)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
