import { useCallback, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import MatchList from "../components/MatchList.jsx";
import Pitch from "../components/Pitch.jsx";
import { AWARDS, STAGES, formatNote, formatRank } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { usePitchWidth } from "../hooks/usePitchWidth.js";
import { SLOTS } from "../lineup.js";

const RECORDS = [
  { key: "tries", label: "Essais", unit: "essais" },
  { key: "points", label: "Points", unit: "pts" },
  { key: "season_tries", label: "Essais en une saison", unit: "essais" },
  { key: "season_points", label: "Points en une saison", unit: "pts" },
  { key: "biggest_wins", label: "Larges victoires" },
];

const PLAYOFFS = { ...STAGES, none: "Pas de phases finales", champion: "Champion", running: "En cours" };

// Le palmarès : à gauche les saisons d'un championnat (champion, finale), ses clubs
// titrés et l'histoire de notre club ; au centre les trophées de la saison choisie et
// les records depuis la première saison ; à droite l'équipe type de la saison.
export default function Honours() {
  const { data, error, loading } = useApi(useCallback(api.getHonours, []));
  const [code, setCode] = useState(null);
  const [year, setYear] = useState(null);

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const league = data.leagues.find((lg) => lg.code === (code ?? data.league)) ?? data.leagues[0];
  const season = league?.seasons.find((s) => s.year === year) ?? league?.seasons[0];

  return (
    <>
      <header className="page-head">
        <h1 className="title">Palmarès</h1>
        <select
          className="input tactics__select"
          aria-label="Championnat"
          value={league?.code ?? ""}
          onChange={(event) => {
            setCode(event.target.value);
            setYear(null);
          }}
        >
          {data.leagues.map((lg) => (
            <option key={lg.code} value={lg.code}>
              {lg.name}
            </option>
          ))}
        </select>
      </header>

      {league && (
        <div className="honours fill">
          <div className="honours__column">
            <Seasons league={league} season={season} myId={data.club?.id} onPick={setYear} />
            {data.club && <ClubHistory club={data.club} history={data.club_history} />}
          </div>
          <div className="honours__column">
            <Awards season={season} myId={data.club?.id} />
            <Records records={data.records} myId={data.club?.id} />
          </div>
          <Team season={season} />
        </div>
      )}
    </>
  );
}

function Seasons({ league, season, myId, onPick }) {
  return (
    <section className="card panel honours__seasons">
      <div className="panel__head">
        <span className="eyebrow">{league.short_name} · champions</span>
      </div>
      <div className="panel__body">
        {league.titles.length > 0 && (
          <p className="honours__titles">
            {league.titles.map((t) => (
              <span key={t.club.id} className={`honours__title${t.club.id === myId ? " honours__title--mine" : ""}`} title={t.years.join(", ")}>
                <ClubCrest name={t.club.name} size={18} />
                {t.club.name}
                <span className="num">×{t.titles}</span>
              </span>
            ))}
          </p>
        )}
        <ul className="honours__list">
          {league.seasons.map((s) => (
            <li key={s.year}>
              <button
                type="button"
                className={`honours__season${s.year === season?.year ? " honours__season--active" : ""}`}
                onClick={() => onPick(s.year)}
              >
                <span className="num honours__year">{s.year}</span>
                {s.champion ? (
                  <span className={`with-crest${s.champion.id === myId ? " honours__mine" : ""}`}>
                    <ClubCrest name={s.champion.name} size={20} />
                    {s.champion.name}
                  </span>
                ) : (
                  <span className="muted">Saison en cours</span>
                )}
              </button>
            </li>
          ))}
        </ul>
        {season?.final && (
          <>
            <p className="matches__stage">Finale {season.year}</p>
            <MatchList matches={[season.final]} myClubId={myId} />
          </>
        )}
      </div>
    </section>
  );
}

// Les trophées de la saison choisie.
function Awards({ season, myId }) {
  const singles = (season?.awards ?? []).filter((a) => a.kind !== "team");
  return (
    <section className="card panel">
      <div className="panel__head">
        <span className="eyebrow">Trophées {season?.year ?? ""}</span>
      </div>
      <div className="panel__body">
        {singles.length === 0 ? (
          <p className="table__note">Les trophées se remettent à la fin de la saison, après la finale.</p>
        ) : (
          <ul className="honours__awards-list">
            {singles.map((award) => (
              <li key={award.kind}>
                <span className="eyebrow">{AWARDS[award.kind].label}</span>
                <span className={`honours__winner${award.club.id === myId ? " honours__mine" : ""}`}>
                  <ClubCrest name={award.club.name} size={18} />
                  <span>
                    {award.active ? <Link to={`/joueurs/${award.player_id}`}>{award.name}</Link> : award.name}
                    <span className="muted"> · {award.club.name}</span>
                  </span>
                </span>
                <span className="num honours__value">{AWARDS[award.kind].format(award.value)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

// L'équipe type de la saison choisie, sur le terrain, à la hauteur de la colonne.
function Team({ season }) {
  const ref = useRef(null);
  const team = useMemo(() => teamMarkers(season?.awards ?? []), [season]);
  const width = usePitchWidth(ref, team.length > 0);
  return (
    <section ref={ref} className="card card--padded honours__team">
      <span className="eyebrow">Équipe type {season?.year ?? ""}</span>
      {team.length > 0 ? (
        <Pitch markers={team} style={{ width: width ?? "100%", maxWidth: "100%", margin: "0 auto" }} />
      ) : (
        <p className="table__note">Elle se compose à la fin de la saison.</p>
      )}
    </section>
  );
}

// L'équipe type sur les places du XV, poste par poste, dans l'ordre des numéros.
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
      return {
        key: slot.number,
        x: slot.x,
        y: slot.y,
        number: slot.number,
        label: award.name.split(" ").slice(1).join(" ") || award.name,
        title: `${award.name} · ${award.club.name} · note ${formatNote(award.value)}`,
      };
    })
    .filter(Boolean);
}

// L'histoire du club dirigé, ou celle du manager (ses clubs, sa réputation).
function ClubHistory({ club, history }) {
  const [view, setView] = useState("club");
  const career = useApi(useCallback(api.getCareerHistory, []));
  return (
    <section className="card panel honours__history">
      <div className="panel__head">
        <span className="eyebrow with-crest">
          <ClubCrest name={club.name} size={18} />
          Notre histoire
        </span>
        <div className="chips" role="group" aria-label="Histoire">
          {[
            ["club", "Le club"],
            ["manager", "Ma carrière"],
          ].map(([key, label]) => (
            <button key={key} type="button" className="chip chip--small" aria-pressed={view === key} onClick={() => setView(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="panel__body">
        {view === "manager" ? (
          <ManagerCareer career={career} />
        ) : (
          <table className="table">
          <thead>
            <tr>
              <th scope="col" className="left">Saison</th>
              <th scope="col" className="left">Championnat</th>
              <th scope="col">Rang</th>
              <th scope="col" className="left">Phases finales</th>
            </tr>
          </thead>
          <tbody>
            {history.map((s) => (
              <tr key={s.year}>
                <td className="left num">{s.year}</td>
                <td className="left muted">{s.league_name}</td>
                <td className="num">{s.rank ? `${formatRank(s.rank)} / ${s.club_count}` : "–"}</td>
                <td className={`left${s.playoffs === "champion" ? " honours__mine" : " muted"}`}>
                  {s.playoffs === "champion" ? "Champion" : PLAYOFFS[s.playoffs]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        )}
      </div>
    </section>
  );
}

function ManagerCareer({ career }) {
  if (career.loading) return <p className="status">Chargement…</p>;
  if (career.error) return <p className="table__note">{career.error.message}</p>;
  const data = career.data;
  return (
    <>
      <p className="honours__reputation">
        <span className="num">{Math.round(data.reputation)}</span>
        <span>
          <strong>{data.label}</strong>
          <span className="muted"> · réputation sur 100</span>
        </span>
      </p>
      <table className="table">
        <thead>
          <tr>
            <th scope="col" className="left">Saison</th>
            <th scope="col" className="left">Club</th>
            <th scope="col" title="Rang final / rang attendu par la direction">Rang</th>
            <th scope="col" className="left">Bilan</th>
          </tr>
        </thead>
        <tbody>
          {data.seasons.map((s) => (
            <tr key={`${s.year}-${s.club.id}`}>
              <td className="left num">{s.year}</td>
              <td className="left">
                <span className="with-crest">
                  <ClubCrest name={s.club.name} size={18} />
                  {s.club.name}
                </span>
              </td>
              <td className="num">{s.rank ? `${formatRank(s.rank)} (${formatRank(s.expected)} attendu)` : "–"}</td>
              <td className={`left${s.champion ? " honours__mine" : " muted"}`}>
                {s.champion ? "Champion" : s.rank === null ? "En cours" : s.playoffs ? "Phases finales" : "–"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Records({ records, myId }) {
  const [key, setKey] = useState(RECORDS[0].key);
  const record = RECORDS.find((r) => r.key === key);
  return (
    <section className="card panel honours__records">
      <div className="panel__head">
        <span className="eyebrow">Records</span>
        <span className="muted">
          {records.seasons} saison{records.seasons > 1 ? "s" : ""}
        </span>
      </div>
      <div className="chips chips--scroll honours__chips" role="group" aria-label="Record">
        {RECORDS.map((r) => (
          <button key={r.key} type="button" className="chip chip--small" aria-pressed={key === r.key} onClick={() => setKey(r.key)}>
            {r.label}
          </button>
        ))}
      </div>
      <div className="panel__body">
        {key === "biggest_wins" ? (
          <MatchList matches={records.biggest_wins.map((w) => w.match)} myClubId={myId} />
        ) : (
          <ol className="honours__records-list">
            {records[key].map((line, index) => (
              <li key={`${line.player_id}-${line.year ?? ""}`}>
                <span className="num muted">{index + 1}</span>
                <span className={line.club?.id === myId ? "honours__mine" : undefined}>
                  {line.active ? <Link to={`/joueurs/${line.player_id}`}>{line.name}</Link> : line.name}
                  <span className="muted">
                    {line.club && ` · ${line.club.name}`}
                    {line.year && ` · ${line.year}`}
                  </span>
                </span>
                <span className="num">
                  {line.value} {record.unit}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
