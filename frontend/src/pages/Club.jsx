import { useCallback, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import FormPills, { recentForm } from "../components/FormPills.jsx";
import MatchList from "../components/MatchList.jsx";
import SortHeader from "../components/SortHeader.jsx";
import {
  INJURY_SOURCES,
  SEVERITIES,
  STAGES,
  formatDiff,
  formatLongDate,
  formatNote,
  formatRank,
  formatShortDate,
  matchdayLabel,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";

// Les 5 notes collectives calculées par le moteur sur le XV de départ.
const STRENGTH_LINES = [
  { key: "set_piece", label: "Conquête" },
  { key: "pack", label: "Paquet" },
  { key: "attack", label: "Attaque" },
  { key: "defense", label: "Défense" },
  { key: "kicking", label: "Buteur" },
];

// Tableau de bord : prochain match, rapport de force, classement, derniers résultats.
export default function Club() {
  const { career } = useOutletContext();
  const myId = career.club_id;
  const season = useApi(useCallback(api.getCurrentSeason, []));
  const [lastPlayed, setLastPlayed] = useState(null); // la journée qu'on vient de simuler
  const [newInjuries, setNewInjuries] = useState([]); // nos blessés de cette journée
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  async function act(call, onDone) {
    setBusy(true);
    setActionError(null);
    try {
      onDone(await call());
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  const simulate = () =>
    act(api.playMatchday, (result) => {
      setLastPlayed(result.played);
      setNewInjuries(result.injuries);
      season.setData(result.season);
    });

  const nextSeason = () =>
    act(api.startNextSeason, (data) => {
      setLastPlayed(null);
      setNewInjuries([]);
      season.setData(data);
    });

  if (season.loading) return <p className="status">Chargement…</p>;
  if (season.error) return <p className="status status--error">{season.error.message}</p>;

  const data = season.data;
  const next = data.next_matchday;
  const myNextMatch = next?.matches.find((m) => m.home.id === myId || m.away.id === myId) ?? null;
  const rankOf = (clubId) => data.standings.find((row) => row.club_id === clubId)?.rank;

  // Derniers résultats : la journée qu'on vient de jouer, sinon la dernière jouée.
  const playedMatches = data.matches.filter((m) => m.home_score !== null);
  const lastMatchday = lastPlayed ?? lastPlayedMatchday(playedMatches);

  return (
    <>
      {actionError && <p className="status--error">{actionError.message}</p>}

      {data.phase === "finished" ? (
        <section className="hero">
          <p className="eyebrow">Saison {data.year} terminée</p>
          <h1 className="hero__title">{data.champion.name}</h1>
          <p className="hero__sub">Champion {data.year}</p>
          <div className="hero__actions">
            <button type="button" className="button button--primary" disabled={busy} onClick={nextSeason}>
              {busy ? "Intersaison…" : `Lancer la saison ${data.year + 1}`}
            </button>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            Les joueurs prennent un an, ceux de 36 ans et plus arrêtent, le centre de formation
            apporte des jeunes, et un nouveau calendrier est tiré.
          </p>
        </section>
      ) : (
        <section className="hero">
          <p className="eyebrow">
            {next.stage === "regular" ? `Journée ${next.matchday} sur ${data.regular_matchdays}` : STAGES[next.stage]} ·{" "}
            {formatLongDate(next.date)}
          </p>
          {myNextMatch ? (
            <NextMatch match={myNextMatch} myId={myId} rankOf={rankOf} matches={data.matches} />
          ) : (
            <>
              <h1 className="hero__title">Tu ne joues pas</h1>
              <p className="hero__sub">Ton club n'est pas concerné par cette journée.</p>
            </>
          )}
          <div className="hero__actions">
            <button type="button" className="button" disabled={busy} onClick={simulate}>
              {busy ? "Simulation…" : "Simuler la journée"}
            </button>
            <button type="button" className="button button--primary" disabled title="Bientôt : le match en direct">
              Jouer le match
            </button>
            <Link to="/calendrier" className="muted">
              Voir le calendrier
            </Link>
          </div>
        </section>
      )}

      <div className="club-grid">
        {myNextMatch && (
          <Strength myId={myId} opponentId={myNextMatch.home.id === myId ? myNextMatch.away.id : myNextMatch.home.id} />
        )}

        {lastMatchday && (
          <section className="section">
            <div className="section__head">
              <h2 className="eyebrow">
                {lastPlayed ? "Journée simulée" : "Dernière journée"} · {matchdayLabel(lastMatchday)}
              </h2>
              <span className="muted">{formatLongDate(lastMatchday.date)}</span>
            </div>
            <div className="card">
              <MatchList matches={lastMatchday.matches} myClubId={myId} />
              {lastPlayed && newInjuries.length > 0 && <NewInjuries cases={newInjuries} />}
            </div>
          </section>
        )}

        {data.phase !== "regular" && <Playoffs season={data} myId={myId} />}

        <Standings season={data} myId={myId} />
      </div>
    </>
  );
}

// Nos blessés de la journée qu'on vient de simuler (entraînement et match).
function NewInjuries({ cases }) {
  return (
    <>
      <div className="matches__stage">Blessés · {cases.length}</div>
      <ul className="injury-list">
        {cases.map(({ player, injury }) => (
          <li key={injury.id}>
            <span className={`tag tag--${injury.severity}`}>{SEVERITIES[injury.severity].label}</span>
            <span style={{ fontWeight: 600 }}>{player.name}</span>
            <span className="muted">
              {injury.kind} {INJURY_SOURCES[injury.source]} · retour le {formatShortDate(injury.return_date)}
            </span>
            {!injury.protocol_chosen && (
              <Link to="/medical" style={{ fontWeight: 600 }}>
                Choisir le protocole
              </Link>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

function NextMatch({ match, myId, rankOf, matches }) {
  const home = match.home.id === myId;
  const opponent = home ? match.away : match.home;
  const venue = match.neutral ? "Terrain neutre" : home ? "À domicile" : "À l'extérieur";
  return (
    <>
      <h1 className="hero__title">{opponent.name}</h1>
      <p className="hero__sub">
        {venue} · {rankOf(opponent.id) ? `${formatRank(rankOf(opponent.id))} du championnat` : ""}
      </p>
      <div className="hero__forms">
        <div>
          <span className="muted">Notre forme</span>
          <FormPills results={recentForm(matches, myId)} />
        </div>
        <div>
          <span className="muted">Leur forme</span>
          <FormPills results={recentForm(matches, opponent.id)} />
        </div>
      </div>
    </>
  );
}

// Les 5 notes du moteur, mon club contre l'adversaire du prochain match.
function Strength({ myId, opponentId }) {
  const mine = useApi(useCallback(() => api.getClub(myId), [myId]));
  const theirs = useApi(useCallback(() => api.getClub(opponentId), [opponentId]));

  if (mine.loading || theirs.loading) return <p className="status">Chargement…</p>;
  if (mine.error || theirs.error) return null;

  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Rapport de force</h2>
        <span className="muted">Notes sur 20, XV de départ</span>
      </div>
      <div className="card card--padded">
        <div className="versus__names">
          <span>{mine.data.name}</span>
          <span>{theirs.data.name}</span>
        </div>
        {STRENGTH_LINES.map((line) => {
          const us = mine.data.strength[line.key];
          const them = theirs.data.strength[line.key];
          const usWins = us >= them;
          return (
            <div key={line.key} className="versus">
              <span className={`versus__value num ${usWins ? "versus__value--wins" : ""}`}>{formatNote(us)}</span>
              <div className="meter meter--reverse">
                <div className={`meter__fill ${usWins ? "meter__fill--accent" : "meter__fill--muted"}`} style={{ width: `${(us / 20) * 100}%` }} />
              </div>
              <span className="versus__label">{line.label}</span>
              <div className="meter">
                <div className={`meter__fill ${usWins ? "meter__fill--muted" : ""}`} style={{ width: `${(them / 20) * 100}%` }} />
              </div>
              <span className={`versus__value num ${usWins ? "" : "versus__value--wins"}`}>{formatNote(them)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Playoffs({ season, myId }) {
  const rounds = ["barrage", "semi", "final"]
    .map((stage) => ({ stage, matches: season.matches.filter((m) => m.stage === stage) }))
    .filter((round) => round.matches.length > 0);
  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Phases finales</h2>
        <span className="muted">Égalité : le mieux classé passe</span>
      </div>
      <div className="card">
        {rounds.map((round) => (
          <div key={round.stage}>
            <div className="matches__stage">{STAGES[round.stage]} · {formatLongDate(round.matches[0].date)}</div>
            <MatchList matches={round.matches} myClubId={myId} />
          </div>
        ))}
      </div>
    </section>
  );
}

function Standings({ season, myId }) {
  const { rows, sort, toggle } = useSort(season.standings, { key: "rank", dir: "asc" });
  const header = (key, label, first = "desc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={sort} onToggle={toggle} first={first} left={left} />
  );
  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Classement</h2>
        <span className="muted">Les {season.playoff_qualifiers} premiers jouent les phases finales</span>
      </div>
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              {header("rank", "#", "asc", true)}
              {header("club_name", "Club", "asc", true)}
              {header("played", "J")}
              {header("won", "G")}
              {header("drawn", "N")}
              {header("lost", "P")}
              {header("points_difference", "Diff")}
              {header("tries_for", "Ess")}
              {header("offensive_bonus", "BO")}
              {header("defensive_bonus", "BD")}
              {header("league_points", "Pts")}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.club_id}
                className={[
                  row.club_id === myId ? "table__row--mine" : "",
                  row.rank === season.playoff_qualifiers && sort?.key === "rank" ? "table__row--cut" : "",
                ].join(" ")}
              >
                <td className="left muted">{row.rank}</td>
                <td className="left">{row.club_name}</td>
                <td>{row.played}</td>
                <td>{row.won}</td>
                <td>{row.drawn}</td>
                <td>{row.lost}</td>
                <td>{formatDiff(row.points_difference)}</td>
                <td>{row.tries_for}</td>
                <td>{row.offensive_bonus}</td>
                <td>{row.defensive_bonus}</td>
                <td style={{ fontWeight: 600 }}>{row.league_points}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="table__note">Diff : différence de points · Ess : essais · BO/BD : bonus offensif/défensif</p>
      </div>
    </section>
  );
}

// La dernière journée jouée, au format { matchday, stage, date, matches }.
function lastPlayedMatchday(playedMatches) {
  if (playedMatches.length === 0) return null;
  const last = playedMatches[playedMatches.length - 1];
  return {
    matchday: last.matchday,
    stage: last.stage,
    date: last.date,
    matches: playedMatches.filter((m) => m.matchday === last.matchday),
  };
}
