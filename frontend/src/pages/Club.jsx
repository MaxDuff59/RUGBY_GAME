import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import Affairs from "../components/Affairs.jsx";
import ClubCrest from "../components/ClubCrest.jsx";
import FormPills, { recentForm } from "../components/FormPills.jsx";
import MatchList from "../components/MatchList.jsx";
import { NOTE_LINES, NoteLine } from "../components/NoteLine.jsx";
import SeasonReview from "../components/SeasonReview.jsx";
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
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { useSort } from "../hooks/useSort.js";

// Les 5 notes collectives calculées par le moteur sur le XV de départ.
const STRENGTH_LINES = [
  { key: "set_piece", label: "Conquête" },
  { key: "pack", label: "Paquet" },
  { key: "attack", label: "Attaque" },
  { key: "defense", label: "Défense" },
  { key: "kicking", label: "Buteur" },
];

// Onglets de la page sur téléphone : prochain match et classement, puis le reste à part.
const PHONE_TABS = [
  { key: "board", label: "Club" },
  { key: "notes", label: "Vie du club" },
  { key: "last", label: "Dernière journée" },
  { key: "strength", label: "Rapport de force" },
];

// Tableau de bord : prochain match (avec la vie du club), puis classement, rapport de
// force et derniers résultats. Sur téléphone, la vue de base garde le prochain match et
// le classement ; vie du club, dernière journée et rapport de force ont chacun leur onglet.
export default function Club() {
  const { career } = useOutletContext();
  const navigate = useNavigate();
  const location = useLocation();
  const phone = useMediaQuery(PHONE_QUERY);
  const [phoneTab, setPhoneTab] = useState("board");
  // Sur ordinateur tout se voit ; sur téléphone, seulement l'onglet choisi.
  const shown = (tab) => !phone || phoneTab === tab;
  const myId = career.club_id;
  const season = useApi(useCallback(api.getCurrentSeason, []));
  // Match en direct en cours (404 sinon) : « Jouer le match » le reprend.
  const liveMatch = useApi(useCallback(api.getLive, []));
  const [lastPlayed, setLastPlayed] = useState(null); // la journée qu'on vient de simuler
  const [newInjuries, setNewInjuries] = useState([]); // nos blessés de cette journée
  const [signings, setSignings] = useState([]); // nos joueurs signés ailleurs cette journée
  const [callUps, setCallUps] = useState([]); // nos joueurs dans les listes des sélections annoncées depuis
  const [showReview, setShowReview] = useState(false); // bilan de fin de saison
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  // Affaires entre deux matchs : à régler avant de jouer la journée suivante.
  const affairs = useApi(useCallback(api.getAffairs, []));
  const pending = affairs.data?.pending ?? [];
  const [showAffairs, setShowAffairs] = useState(false);
  const [notesVersion, setNotesVersion] = useState(0); // recharge la vie du club après une réponse

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

  // Après une journée jouée (simulée ici, ou finie depuis la page Match) : la suite.
  const applyResult = useCallback(
    (result) => {
      // Limogé par la direction : la carrière est terminée, on choisit un autre club.
      if (result.dismissal) {
        navigate("/start", { replace: true });
        return;
      }
      setLastPlayed(result.played);
      setNewInjuries(result.injuries);
      setSignings(result.signings);
      setCallUps(result.call_ups ?? []);
      season.setData(result.season);
      // La finale vient d'être jouée : place au bilan (les affaires passent devant).
      setShowReview(result.season.phase === "finished" && result.affairs.length === 0);
      affairs.setData({ pending: result.affairs, recent: affairs.data?.recent ?? [] });
      setShowAffairs(result.affairs.length > 0);
    },
    [navigate, season.setData, affairs.setData, affairs.data],
  );

  // La page Match renvoie ici avec le résultat de la journée qu'elle vient de finir
  // (une seule fois : l'état de navigation est effacé aussitôt).
  const applied = useRef(null);
  useEffect(() => {
    const played = location.state?.played;
    if (!played || applied.current === played) return;
    applied.current = played;
    applyResult(played);
    liveMatch.setData(null);
    navigate(location.pathname, { replace: true, state: null });
  }, [location, applyResult, navigate, liveMatch.setData]);

  const simulate = () => {
    if (pending.length > 0) {
      setShowAffairs(true);
      return;
    }
    act(api.playMatchday, applyResult);
  };

  const playLive = () => {
    if (pending.length > 0) {
      setShowAffairs(true);
      return;
    }
    if (liveMatch.data) {
      navigate("/match");
      return;
    }
    act(api.startLive, () => navigate("/match"));
  };

  const affairAnswered = (done) => {
    const left = pending.filter((affair) => affair.id !== done.id);
    affairs.setData({ pending: left, recent: [done, ...(affairs.data?.recent ?? [])] });
    setNotesVersion((version) => version + 1);
    if (left.length === 0) {
      setShowAffairs(false);
      setShowReview(season.data?.phase === "finished");
    }
  };

  const nextSeason = () =>
    act(api.startNextSeason, (data) => {
      setLastPlayed(null);
      setNewInjuries([]);
      setSignings([]);
      setCallUps([]);
      setShowReview(false);
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
      {showReview && (
        <SeasonReview
          clubId={myId}
          onClose={() => setShowReview(false)}
          onNextSeason={nextSeason}
          busy={busy}
          error={actionError}
        />
      )}
      {showAffairs && pending.length > 0 && (
        <Affairs affairs={pending} onAnswered={affairAnswered} onClose={() => setShowAffairs(false)} />
      )}

      {phone && (
        <div className="chips" role="group" aria-label="Onglet">
          {PHONE_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className="chip"
              aria-pressed={phoneTab === tab.key}
              onClick={() => setPhoneTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {phone && shown("notes") && <ClubNotes clubId={myId} season={data} version={notesVersion} />}

      {shown("board") && (
        <div className="hero-row">
          {data.phase === "finished" ? (
            <section className="hero">
              <p className="eyebrow">Saison {data.year} terminée</p>
              <div className="hero__club">
                <ClubCrest name={data.champion.name} size={56} />
                <h1 className="hero__title">{data.champion.name}</h1>
              </div>
              <p className="hero__sub">Champion {data.year}</p>
              <div className="hero__actions">
                <button type="button" className="button" onClick={() => setShowReview(true)}>
                  Bilan de la saison
                </button>
                <button type="button" className="button button--primary" disabled={busy} onClick={nextSeason}>
                  {busy ? "Intersaison…" : `Lancer la saison ${data.year + 1}`}
                </button>
              </div>
              <p className="muted" style={{ margin: 0 }}>
                Les joueurs en fin de contrat non prolongés partent libres, ceux de 36 ans et plus arrêtent, le centre de
                formation apporte des jeunes, et un nouveau calendrier est tiré.
              </p>
            </section>
          ) : (
            <section className="hero">
              <p className="eyebrow">
                {next.stage === "regular" ? `Journée ${next.matchday} sur ${data.regular_matchdays}` : STAGES[next.stage]} ·{" "}
                {formatLongDate(next.date)}
              </p>
              {myNextMatch ? (
                <>
                  <NextMatch match={myNextMatch} myId={myId} rankOf={rankOf} matches={data.matches} />
                  <Doublon clubId={myId} season={data} />
                </>
              ) : (
                <>
                  <h1 className="hero__title">Tu ne joues pas</h1>
                  <p className="hero__sub">Ton club n'est pas concerné par cette journée.</p>
                </>
              )}
              <div className="hero__actions">
                <button type="button" className="button" disabled={busy} onClick={simulate}>
                  {busy
                    ? "Simulation…"
                    : pending.length > 0
                      ? `${pending.length} affaire${pending.length > 1 ? "s" : ""} à régler`
                      : "Simuler la journée"}
                </button>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={busy || !myNextMatch}
                  title={myNextMatch ? "Le match en direct, minute par minute" : "Ton club ne joue pas cette journée"}
                  onClick={playLive}
                >
                  {liveMatch.data ? `Reprendre le match (${liveMatch.data.minute}')` : "Jouer le match"}
                </button>
                <Link to="/calendrier" className="muted">
                  Voir le calendrier
                </Link>
              </div>
            </section>
          )}
          {!phone && <ClubNotes clubId={myId} season={data} version={notesVersion} />}
        </div>
      )}

      {(shown("board") || shown("strength") || shown("last")) && (
        <div className="club-grid club-grid--three fill">
          {shown("board") && <Leagues key={data.league.code} season={data} myId={myId} />}

          {shown("strength") &&
            (myNextMatch ? (
              <Strength myId={myId} opponentId={myNextMatch.home.id === myId ? myNextMatch.away.id : myNextMatch.home.id} />
            ) : (
              phone && <p className="muted">Ton club ne joue pas la prochaine journée.</p>
            ))}

          {shown("last") && !lastMatchday && phone && <p className="muted">Aucune journée jouée cette saison.</p>}
          {shown("last") && lastMatchday && (
            <section className="section">
              <div className="section__head">
                <h2 className="eyebrow">
                  {lastPlayed ? "Journée simulée" : "Dernière journée"} · {matchdayLabel(lastMatchday)}
                </h2>
                <span className="muted">{formatLongDate(lastMatchday.date)}</span>
              </div>
              <div className="card">
                {/* Rare et lourd de conséquences : avant les résultats, pour ne pas le manquer. */}
                {lastPlayed && callUps.length > 0 && <NewCallUps notices={callUps} />}
                <MatchList matches={lastMatchday.matches} myClubId={myId} />
                {lastPlayed && newInjuries.length > 0 && <NewInjuries cases={newInjuries} />}
                {lastPlayed && signings.length > 0 && <NewSignings signings={signings} />}
              </div>
            </section>
          )}
        </div>
      )}
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

// Nos joueurs en fin de contrat qu'un concurrent vient de signer : ils partiront à l'intersaison.
function NewSignings({ signings }) {
  return (
    <>
      <div className="matches__stage">Signés ailleurs · {signings.length}</div>
      <ul className="injury-list">
        {signings.map(({ player, new_club }) => (
          <li key={player.id}>
            <span className="tag tag--fragile">Fin de contrat</span>
            <span style={{ fontWeight: 600 }}>{player.name}</span>
            <span className="muted">rejoindra {new_club.name} à l'intersaison</span>
          </li>
        ))}
      </ul>
    </>
  );
}

// Les listes des sélections annoncées depuis la journée précédente : nos joueurs retenus,
// sélection par sélection, et les jours où ils nous manqueront. Compact : une liste de 42
// peut prendre une vingtaine de joueurs au même club.
function NewCallUps({ notices }) {
  return notices.map((notice) => {
    const byNation = new Map();
    for (const { player, nation } of notice.players) {
      if (!byNation.has(nation.name)) byNation.set(nation.name, []);
      byNation.get(nation.name).push(player.name.split(" ").slice(1).join(" ") || player.name);
    }
    const days = notice.doublons;
    return (
      <div key={notice.competition}>
        <div className="matches__stage">
          Sélections · {notice.competition} · {notice.players.length} retenu{notice.players.length > 1 ? "s" : ""}
        </div>
        <p className="call-ups">
          {[...byNation].map(([nation, names]) => (
            <span key={nation}>
              <strong>{nation}</strong> : {names.join(", ")}.{" "}
            </span>
          ))}
          <span className="muted">
            {days.length > 0
              ? `Doublon${days.length > 1 ? "s" : ""} : ils manqueront le${days.length > 1 ? "s" : ""} ${days.map(formatShortDate).join(", ")}`
              : "Aucun doublon : nous ne jouons pas ces jours-là."}
          </span>
        </p>
      </div>
    );
  });
}

// Sous l'affiche : nos joueurs retenus par une sélection qui joue le même jour que nous.
function Doublon({ clubId, season }) {
  // Rechargé à chaque journée jouée (la saison change d'objet).
  const club = useApi(useCallback(() => api.getClub(clubId), [clubId, season]));
  const away = club.data?.players.filter((player) => player.duty?.away) ?? [];
  if (away.length === 0) return null;
  const names = away.map((player) => player.last_name);
  return (
    <p className="muted doublon">
      <span className="tag tag--fragile">Doublon</span>{" "}
      {away.length} joueur{away.length > 1 ? "s" : ""} en sélection : {names.slice(0, 6).join(", ")}
      {names.length > 6 ? ` et ${names.length - 6} autre${names.length - 6 > 1 ? "s" : ""}` : ""}.{" "}
      <Link to="/effectif">Voir le XV</Link>
    </p>
  );
}

function NextMatch({ match, myId, rankOf, matches }) {
  const home = match.home.id === myId;
  const opponent = home ? match.away : match.home;
  const venue = match.neutral ? "Terrain neutre" : home ? "À domicile" : "À l'extérieur";
  return (
    <>
      <div className="hero__club">
        <ClubCrest name={opponent.name} size={56} />
        <h1 className="hero__title">{opponent.name}</h1>
      </div>
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
  const myNotes = useApi(useCallback(() => api.getClubNotes(myId), [myId]));
  const theirNotes = useApi(useCallback(() => api.getClubNotes(opponentId), [opponentId]));

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
          <span className="with-crest">
            <ClubCrest name={mine.data.name} size={18} />
            {mine.data.name}
          </span>
          <span className="with-crest">
            {theirs.data.name}
            <ClubCrest name={theirs.data.name} size={18} />
          </span>
        </div>
        {STRENGTH_LINES.map((line) => {
          const us = mine.data.strength[line.key];
          const them = theirs.data.strength[line.key];
          const usWins = us >= them;
          return (
            <div key={line.key} className="versus">
              <span className={`versus__value num ${usWins ? "versus__value--wins" : ""}`}>{formatNote(us)}</span>
              <div className="meter meter--reverse">
                <div
                  className={`meter__fill ${usWins ? "meter__fill--accent" : "meter__fill--muted"}`}
                  style={{ width: `${(us / 20) * 100}%` }}
                />
              </div>
              <span className="versus__label">{line.label}</span>
              <div className="meter">
                <div className={`meter__fill ${usWins ? "meter__fill--muted" : ""}`} style={{ width: `${(them / 20) * 100}%` }} />
              </div>
              <span className={`versus__value num ${usWins ? "" : "versus__value--wins"}`}>{formatNote(them)}</span>
            </div>
          );
        })}
        {myNotes.data && theirNotes.data && <FormLine us={myNotes.data.form} them={theirNotes.data.form} />}
      </div>
    </section>
  );
}

// Vie du club : une ligne par note, avec une barre par match joué de la saison.
function ClubNotes({ clubId, season, version }) {
  // Rechargé à chaque journée simulée (la saison change d'objet) et après chaque affaire réglée.
  const notes = useApi(useCallback(() => api.getClubNotes(clubId), [clubId, season, version]));
  if (notes.loading && !notes.data) return <p className="status">Chargement…</p>;
  if (notes.error) return null;
  const { objective } = notes.data;

  return (
    <section className="card card--padded club-notes">
      <div className="section__head">
        <h2 className="eyebrow">Vie du club</h2>
        {objective && (
          <span className="muted" title={`Rang attendu en début de saison : ${formatRank(objective.expected_rank)}`}>
            Objectif : {objective.label.toLowerCase()} ({formatRank(objective.target_rank)})
          </span>
        )}
      </div>
      {NOTE_LINES.map((line) => (
        <NoteLine
          key={line.key}
          line={line}
          note={notes.data[line.key]}
          warning={
            line.key === "board" && notes.data.board.value < notes.data.sack_warning
              ? `Poste menacé : limogeage sous ${formatNote(notes.data.sack_threshold)}`
              : null
          }
        />
      ))}
    </section>
  );
}

// Forme du jour : de combien moral, cohésion et fraîcheur font varier les notes ci-dessus.
function FormLine({ us, them }) {
  const percent = (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatNote(Math.abs(value) * 100)} %`;
  const detail = (form) =>
    `Moral ${percent(form.morale)} · cohésion ${percent(form.cohesion)} · fraîcheur ${percent(form.freshness)}`;
  const usWins = us.total >= them.total;
  return (
    <div className="versus versus--form">
      <span className={`versus__value num ${usWins ? "versus__value--wins" : ""}`} title={detail(us)}>
        {percent(us.total)}
      </span>
      <span />
      <span className="versus__label" title="Moral, cohésion et fraîcheur du XV multiplient les notes du match">
        Forme du jour
      </span>
      <span />
      <span className={`versus__value num ${usWins ? "" : "versus__value--wins"}`} title={detail(them)}>
        {percent(them.total)}
      </span>
    </div>
  );
}

// Une cellule de la grille : phases finales (le cas échéant) puis classement de notre
// championnat, ou d'un autre au choix.
function Leagues({ season, myId }) {
  const [code, setCode] = useState(season.league.code);
  const other = useApi(
    // Rechargé à chaque journée jouée (`season` change).
    useCallback(() => (code === season.league.code ? Promise.resolve(null) : api.getCurrentSeason(code)), [
      code,
      season,
    ]),
  );
  const shown = code === season.league.code ? season : other.data;
  const picker = season.leagues.length > 1 && (
    <select
      className="input tactics__select"
      aria-label="Championnat"
      value={code}
      onChange={(event) => setCode(event.target.value)}
    >
      {season.leagues.map((league) => (
        <option key={league.code} value={league.code}>
          {league.short_name}
        </option>
      ))}
    </select>
  );
  if (!shown) {
    return (
      <div className="club-grid__stack">
        <section className="section">
          {picker}
          <p className="status">{other.error ? other.error.message : "Chargement…"}</p>
        </section>
      </div>
    );
  }
  return (
    <div className="club-grid__stack">
      {shown.phase !== "regular" && <Playoffs season={shown} myId={myId} />}
      <Standings season={shown} myId={myId} picker={picker} />
    </div>
  );
}

function Playoffs({ season, myId }) {
  const rounds = season.league.playoff_stages
    .map((stage) => ({ stage, matches: season.matches.filter((m) => m.stage === stage) }))
    .filter((round) => round.matches.length > 0);
  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Phases finales · {season.league.short_name}</h2>
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

function Standings({ season, myId, picker }) {
  const { rows, sort, toggle } = useSort(season.standings, { key: "rank", dir: "asc" });
  const header = (key, label, first = "desc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={sort} onToggle={toggle} first={first} left={left} />
  );
  return (
    // Toutes les équipes tiennent dans la carte, quel que soit leur nombre : la taille
    // des lignes suit la hauteur disponible (`--rows`, voir `.standings` dans styles.css).
    <section className="section standings" style={{ "--rows": rows.length }}>
      <div className="section__head">
        <h2 className="eyebrow">Classement</h2>
        {picker}
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
                <td className="left">
                  <span className="with-crest" title={row.club_name}>
                    <ClubCrest name={row.club_name} size={20} />
                    <span className="standings__name">{row.club_name}</span>
                  </span>
                </td>
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
