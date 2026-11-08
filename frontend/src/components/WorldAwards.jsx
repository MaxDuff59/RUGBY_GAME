import { useCallback, useMemo, useRef } from "react";

import { api } from "../api.js";
import { formatNote, formatRankingChange, formatRankingPoints } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { usePitchWidth } from "../hooks/usePitchWidth.js";
import { SLOTS } from "../lineup.js";
import ClubCrest from "./ClubCrest.jsx";
import Pitch from "./Pitch.jsx";
import PlayerAvatar from "./PlayerAvatar.jsx";

// Les trophées mondiaux (backend/engine/world_awards.py), dans l'ordre de la page.
const KINDS = {
  player: { label: "Meilleur joueur du monde", format: (a) => `${formatNote(a.value)} de moyenne` },
  revelation: { label: "Meilleur espoir du monde", format: (a) => `${formatNote(a.value)} de moyenne · ${a.age} ans` },
  international: { label: "Meilleur joueur en sélection", format: (a) => `${formatNote(a.value)} en ${a.tests} tests` },
  tries: { label: "Meilleur marqueur d'essais", format: (a) => `${a.value} essai${a.value > 1 ? "s" : ""}` },
  points: { label: "Meilleur réalisateur", format: (a) => `${a.value} pts` },
  tackles: { label: "Meilleur plaqueur", format: (a) => `${a.value} plaquages` },
};
// Les trois premiers en grand, les records de la saison en dessous.
const HEADLINE = ["player", "revelation", "international"];

// Les trophées mondiaux de la saison, au bilan de fin de saison : le meilleur joueur du
// monde, le meilleur espoir, le meilleur en sélection, les records de la saison, les
// sélections de l'année, puis le XV mondial sur le terrain. `isOurs` : un lauréat à
// mettre en avant (de notre club, de notre sélection, ou nous-même).
export default function WorldAwards({ isOurs = () => false }) {
  const world = useApi(useCallback(api.getWorldAwards, []));
  if (world.loading) return <p className="status">Chargement…</p>;
  if (world.error) return <p className="status status--error">{world.error.message}</p>;
  const { awards, best_nation: best, climber } = world.data;
  const singles = Object.keys(KINDS)
    .map((kind) => awards.find((a) => a.kind === kind))
    .filter(Boolean);
  if (singles.length === 0) {
    return <p className="muted">Pas assez de matchs joués cette saison pour remettre les trophées.</p>;
  }
  const headline = singles.filter((a) => HEADLINE.includes(a.kind));
  const records = singles.filter((a) => !HEADLINE.includes(a.kind));
  return (
    <div className="world-awards">
      <div className="world-awards__list">
        <ul className="world-awards__headline">
          {headline.map((award) => (
            <li key={award.kind} className={isOurs(award) ? "world-awards__ours" : undefined}>
              <span className="eyebrow">{KINDS[award.kind].label}</span>
              <span className="world-awards__winner">
                <PlayerAvatar src={award.photo} size={44} />
                <span>
                  <strong className="world-awards__name">{award.name}</strong>
                  <Origin award={award} />
                </span>
              </span>
              <span className="num world-awards__value">{KINDS[award.kind].format(award)}</span>
            </li>
          ))}
        </ul>
        <ul className="honours__awards-list">
          {records.map((award) => (
            <li key={award.kind} className={isOurs(award) ? "world-awards__ours" : undefined}>
              <span className="eyebrow">{KINDS[award.kind].label}</span>
              <span className="honours__winner">
                <span>
                  {award.name}
                  <Origin award={award} />
                </span>
              </span>
              <span className="num honours__value">{KINDS[award.kind].format(award)}</span>
            </li>
          ))}
          {best && (
            <li>
              <span className="eyebrow">Sélection de l'année</span>
              <span className="honours__winner">
                <ClubCrest name={best.nation.name} size={18} />
                <span>
                  {best.nation.name}
                  <span className="muted"> · n° 1 mondial</span>
                </span>
              </span>
              <span className="num honours__value">{formatRankingPoints(best.points)} pts</span>
            </li>
          )}
          {climber && climber.change > 0 && (
            <li>
              <span className="eyebrow">Plus forte progression</span>
              <span className="honours__winner">
                <ClubCrest name={climber.nation.name} size={18} />
                <span>
                  {climber.nation.name}
                  <span className="muted"> · n° {climber.rank} mondial</span>
                </span>
              </span>
              <span className="num honours__value">{formatRankingChange(climber.change)} pts</span>
            </li>
          )}
        </ul>
      </div>
      <WorldTeam awards={awards} />
    </div>
  );
}

// Son club (ou « hors championnats ») et sa sélection.
function Origin({ award }) {
  return (
    <span className="muted world-awards__origin">
      {award.club && <ClubCrest name={award.club.name} size={16} />}
      {award.club ? award.club.name : "Hors championnats"}
      {award.nation && ` · ${award.nation.name}`}
    </span>
  );
}

// Le XV mondial de l'année, sur le terrain.
function WorldTeam({ awards }) {
  const ref = useRef(null);
  const team = useMemo(() => teamMarkers(awards), [awards]);
  const width = usePitchWidth(ref, team.length > 0);
  return (
    <section ref={ref} className="card card--padded world-awards__team">
      <span className="eyebrow">XV mondial de l'année</span>
      {team.length > 0 ? (
        <Pitch markers={team} style={{ width: width ?? "100%", maxWidth: "100%", margin: "0 auto" }} />
      ) : (
        <p className="table__note">Pas assez de matchs joués pour le composer.</p>
      )}
    </section>
  );
}

// Les lauréats du XV, place par place, dans l'ordre des numéros.
function teamMarkers(awards) {
  const byPosition = {};
  for (const award of awards.filter((a) => a.kind === "team")) {
    (byPosition[award.slot] ??= []).push(award);
  }
  return [...SLOTS]
    .sort((a, b) => a.number - b.number)
    .map((slot) => {
      const award = byPosition[slot.position]?.shift();
      if (!award) return null;
      const where = [award.club?.name, award.nation?.name].filter(Boolean).join(" · ");
      return {
        key: slot.number,
        x: slot.x,
        y: slot.y,
        number: slot.number,
        label: award.name.split(" ").slice(1).join(" ") || award.name,
        title: `${award.name} · ${where} · note ${formatNote(award.value)}`,
      };
    })
    .filter(Boolean);
}
