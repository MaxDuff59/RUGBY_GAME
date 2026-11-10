import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { ActionError } from "../components/FullGame.jsx";
import HeroSeasonEnd, { CareerSummary } from "../components/HeroSeasonEnd.jsx";
import Simulation, { simulationTargets } from "../components/Simulation.jsx";
import TitleCelebration from "../components/TitleCelebration.jsx";
import SplitButton from "../components/SplitButton.jsx";
import WindowBoard from "../components/WindowBoard.jsx";
import { RankingTable } from "../components/WorldRanking.jsx";
import {
  ATTRIBUTES,
  COACH_NOTES,
  HERO_STATUS,
  formatContractEnd,
  formatDiff,
  formatMoney,
  POSITIONS,
  formatLongDate,
  formatNote,
  formatRank,
  formatShortDate,
  matchdayTitle,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";

// Note de meneur à partir de laquelle il parle à son équipe en match (engine/team_talk.py).
const LEADER = 17;

const plural = (n, word) => `${n} ${word}${n > 1 ? "s" : ""}`;

// Sous ses attributs : ses matchs de la saison (club et sélection), toute sa carrière,
// les classements, et dès qu'il a été appelé, le calendrier international.
const PERIODS = [
  { key: "season", label: "Cette saison" },
  { key: "career", label: "Ta carrière" },
  { key: "standings", label: "Classement" },
  { key: "internationals", label: "Sélections" },
];

// Téléphone : les sous-onglets de la page.
const PHONE_TABS = [
  { key: "match", label: "Match" },
  { key: "progress", label: "Progression" },
  { key: "matches", label: "Tes matchs" },
];

// Carrière de joueur : le tableau de bord du joueur incarné. En haut, le prochain match
// de son club (le jouer en direct, ou laisser la journée se jouer) et sa fiche ; dessous,
// ses attributs, où placer les points gagnés, et ses matchs de la saison. Sur téléphone,
// un sous-onglet à la fois.
export default function Hero() {
  const { career, refreshCareer } = useOutletContext();
  const navigate = useNavigate();
  const location = useLocation();
  const hero = useApi(useCallback(api.getHero, []));
  const season = useApi(useCallback(api.getCurrentSeason, []));
  // Match en direct en cours (404 sinon) : « Jouer le match » le reprend.
  const liveMatch = useApi(useCallback(api.getLive, []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [lastDay, setLastDay] = useState(null); // la journée qui vient d'être jouée
  const phone = useMediaQuery(PHONE_QUERY);
  const [view, setView] = useState("match"); // téléphone : le sous-onglet ouvert
  const [period, setPeriod] = useState("season"); // ses matchs, toute sa carrière ou les classements
  const [seasonEnd, setSeasonEnd] = useState(false); // la fenêtre du bilan et du mercato
  const [simulation, setSimulation] = useState(null); // « Simuler jusqu'à… » : { until }
  const [titles, setTitles] = useState([]); // titres tout juste gagnés, à fêter

  const { setData: setSeason } = season;
  const { reload: reloadHero } = hero;

  // Transfert, prêt, retour de prêt : l'en-tête et les autres pages suivent son club.
  const heroClubId = hero.data?.club?.id;
  useEffect(() => {
    if (heroClubId && heroClubId !== career.club_id) refreshCareer();
  }, [heroClubId, career.club_id, refreshCareer]);

  // La page Match renvoie ici avec la journée qu'elle vient de finir (une seule fois).
  const applied = useRef(null);
  useEffect(() => {
    const played = location.state?.played;
    if (!played || applied.current === played) return;
    applied.current = played;
    setLastDay(played);
    if (played.titles?.length) setTitles((queue) => [...queue, ...played.titles]);
    setSeason(played.season);
    liveMatch.setData(null);
    reloadHero();
    navigate(location.pathname, { replace: true, state: null });
  }, [location, navigate, setSeason, liveMatch.setData, reloadHero]);

  async function run(call) {
    setBusy(true);
    setError(null);
    try {
      await call();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  // Blessé : il joue quand même, diminué (le choix vaut pour le prochain match).
  const playHurt = () =>
    run(async () => {
      await api.setPlayHurt(true);
      if (!liveMatch.data) await api.startLive();
      navigate("/match");
    });

  const playLive = () =>
    run(async () => {
      if (!liveMatch.data) await api.startLive();
      navigate("/match");
    });

  // Les titres que la journée vient de donner : la fenêtre de célébration.
  const celebrate = (fresh) => {
    if (fresh?.length) setTitles((queue) => [...queue, ...fresh]);
  };

  // Simuler : son match se joue quand même avec lui (le moteur du direct, joué d'une
  // traite : la voie sûre à chaque action) ; sans lui (blessé, club au repos), la journée.
  const simulate = (withHero) =>
    run(async () => {
      if (withHero && !liveMatch.data) await api.startLive();
      const result = withHero ? await api.finishLive() : await api.playMatchday();
      setLastDay(result);
      celebrate(result.titles);
      setSeason(result.season);
      liveMatch.setData(null);
      reloadHero();
    });

  // Plusieurs journées d'un coup : chacune comme « Simuler », la page suit derrière.
  const dayPlayed = (result) => {
    setLastDay(result);
    celebrate(result.titles);
    setSeason(result.season);
    liveMatch.setData(null);
    reloadHero();
  };

  const closeSimulation = (played) => {
    setSimulation(null);
    if (played && season.data?.phase === "finished") setSeasonEnd(true);
  };

  const nextSeason = () =>
    run(async () => {
      setSeason(await api.startNextSeason());
      setLastDay(null);
      setSeasonEnd(false);
      reloadHero();
    });

  const train = (key) =>
    run(async () => {
      hero.setData(await api.trainHero(key));
    });

  if ((hero.loading && !hero.data) || (season.loading && !season.data)) return <p className="status">Chargement…</p>;
  if (hero.error) return <p className="status status--error">{hero.error.message}</p>;
  if (season.error) return <p className="status status--error">{season.error.message}</p>;

  const me = hero.data;
  const state = season.data;
  const next = state.next_match;
  const clubId = me.club?.id;
  const myMatch = next?.matches.find((m) => m.home.id === clubId || m.away.id === clubId);
  const available = me.status === "starter" || me.status === "bench";
  const finished = state.phase === "finished";
  const standing = state.standings.find((row) => row.club_id === clubId);
  const rank = standing?.played ? standing.rank : null;
  const reward = lastDay?.hero ?? me.last_reward;
  // Son match en sélection passe avant celui de son club s'il tombe avant.
  const test = me.called_up && (!myMatch || me.called_up.date <= next.date) ? me.called_up : null;
  const played = me.matches.filter((m) => m.minutes > 0);
  const average = played.length ? played.reduce((sum, m) => sum + (m.rating ?? 6), 0) / played.length : null;
  const tries = me.matches.reduce((sum, m) => sum + m.tries, 0);
  // L'onglet des sélections arrive avec sa première convocation.
  const capped = me.caps > 0 || me.called_up !== null || me.matches.some((m) => m.international);
  const periods = PERIODS.filter((p) => p.key !== "internationals" || capped);

  // « Simuler », et sa flèche : jusqu'à une date, la fin de la phase aller, de la saison.
  // Pas pendant un match en direct commencé : on le reprend, ou on le simule seul.
  const simulateOptions =
    (state.next_match ?? state.next_matchday) && !liveMatch.data
      ? [
          { key: "date", label: "Une date à choisir…", onSelect: () => setSimulation({ until: null }) },
          ...simulationTargets(state).map((target) => ({
            key: target.key,
            label: target.label,
            hint: target.hint,
            onSelect: () => setSimulation({ until: target.date }),
          })),
        ]
      : [];
  const simulateButton = (label, onClick, primary = false) => (
    <SplitButton
      primary={primary}
      disabled={busy}
      onClick={onClick}
      menuLabel="Autres simulations"
      menuTitle="Simuler jusqu'à…"
      options={simulateOptions}
    >
      {busy ? "Journée en cours…" : label}
    </SplitButton>
  );

  const matchCard = (
    <section className="hero">
      {finished ? (
        <>
          <p className="eyebrow">Saison {state.year} terminée</p>
          <h1 className="hero__title">{state.champion ? `${state.champion.name} champion` : "Fin de saison"}</h1>
          <p className="hero__sub">
            {plural(played.length, "match")} joué{played.length > 1 ? "s" : ""}, {plural(tries, "essai")}
            {average !== null && `, ${formatNote(average)} de moyenne`}
          </p>
          <div className="hero__actions">
            <button type="button" className="button button--primary" onClick={() => setSeasonEnd(true)}>
              Bilan et avenir
            </button>
            <span className="muted">Prolonger, partir, être prêté, ou raccrocher : c'est le moment.</span>
          </div>
        </>
      ) : test ? (
        <>
          <p className="eyebrow">
            {test.nation} · {test.competition} · {formatLongDate(test.date)}
          </p>
          <div className="hero__club">
            <ClubCrest name={test.home ? test.nation : test.opponent} size={48} />
            <h1 className="hero__title">
              {test.home ? `${test.nation} – ${test.opponent}` : `${test.opponent} – ${test.nation}`}
            </h1>
            <ClubCrest name={test.home ? test.opponent : test.nation} size={48} />
          </div>
          <p className="hero__sub">Tu es appelé en sélection.</p>
          <div className="hero__actions">
            <button type="button" className="button button--primary" disabled={busy} onClick={playLive}>
              {liveMatch.data ? "Reprendre le match" : "Jouer le match international"}
            </button>
            {simulateButton("Simuler", () => simulate(false))}
          </div>
        </>
      ) : myMatch ? (
        <>
          <p className="eyebrow">
            {matchdayTitle(next)} · {formatLongDate(next.date)}
          </p>
          <div className="hero__club">
            <ClubCrest name={myMatch.home.name} size={48} />
            <h1 className="hero__title">
              {myMatch.home.name} – {myMatch.away.name}
            </h1>
            <ClubCrest name={myMatch.away.name} size={48} />
          </div>
          <p className="hero__sub">
            {available
              ? me.status === "starter"
                ? me.first_choice
                  ? "L'entraîneur te titularise."
                  : "L'entraîneur fait tourner : tu es titularisé."
                : me.first_choice
                  ? `L'entraîneur te fait souffler : tu commences sur le banc, il pourrait te faire entrer vers la ${me.entry}e minute.`
                  : me.dropped
                    ? `Après tes derniers matchs, l'entraîneur te met sur le banc : il pourrait te faire entrer vers la ${me.entry}e minute.`
                    : `Tu commences sur le banc : l'entraîneur pourrait te faire entrer vers la ${me.entry}e minute.`
              : me.status === "out"
                ? me.rested
                  ? "L'entraîneur te laisse au repos pour ce match : ton club joue sans toi."
                  : "L'entraîneur ne te retient pas dans le groupe : continue de t'entraîner, ta chance viendra."
                : me.status === "injured"
                  ? `Tu es blessé (${plural(me.injury_weeks, "semaine")}) : soigne-toi, ou serre les dents.`
                  : "Tu es suspendu : ton club joue sans toi."}
          </p>
          <div className="hero__actions">
            {me.status === "injured" && (
              <button type="button" className="button button--primary" disabled={busy} onClick={playHurt}>
                Jouer diminué
              </button>
            )}
            {available && (
              <button type="button" className="button button--primary" disabled={busy} onClick={playLive}>
                {liveMatch.data ? "Reprendre le match" : "Jouer le match"}
              </button>
            )}
            {simulateButton(
              available ? "Simuler" : me.status === "injured" ? "Se soigner" : "Jouer la journée",
              () => simulate(available),
              !available,
            )}
            {available && (
              <span className="muted">En direct, le match s'arrête sur tes actions : à toi de choisir. Simulé, il ne te fait pas progresser.</span>
            )}
            {me.status === "injured" && (
              <span className="muted">Diminué, tes actions réussissent moins, et ta blessure peut s'aggraver.</span>
            )}
          </div>
        </>
      ) : (
        <>
          <p className="eyebrow">Saison {state.year}</p>
          <h1 className="hero__title">Ton club ne joue pas</h1>
          <p className="hero__sub">Les autres finissent leur saison.</p>
          <div className="hero__actions">
            {simulateButton("Jouer la journée", () => simulate(false), true)}
          </div>
        </>
      )}
      {lastDay?.played && <LastDay played={lastDay.played} clubId={clubId} />}
      {me.coach_notes[0] && (
        <p className="hero-coach">
          <span className="eyebrow">L'entraîneur · {formatShortDate(me.coach_notes[0].date)}</span>
          {COACH_NOTES[me.coach_notes[0].kind]}
        </p>
      )}
    </section>
  );
  const fiche = (
    <aside className="card card--padded club-notes facts">
      <div className="section__head">
        <h2 className="eyebrow">
          {me.first_name} {me.last_name}
        </h2>
        <span className="muted">{HERO_STATUS[me.status]}</span>
      </div>
      <div className="hero-card__overall">
        <span className="hero-card__value num">{formatNote(me.overall)}</span>
        <span className="muted">
          note générale
          <br />
          {POSITIONS[me.position].label.toLowerCase()} · {me.age} ans
          <br />
          <span
            className={me.leadership >= LEADER ? "hero-card__leader" : undefined}
            title={me.leadership >= LEADER ? "Tu prends la parole en match" : `À ${LEADER}, tu prendras la parole en match`}
          >
            meneur {formatNote(me.leadership)}
          </span>
        </span>
      </div>
      <dl className="facts__list">
        <dt>Club</dt>
        <dd>{me.club ? `${me.club.name}${rank ? `, ${formatRank(rank)}` : ""}` : "Sans club"}</dd>
        {me.loaned_from && (
          <>
            <dt>Prêté par</dt>
            <dd>{me.loaned_from.name}</dd>
          </>
        )}
        <dt>Au poste</dt>
        <dd>
          {formatRank(me.rank)} sur {me.at_position} dans l'effectif
        </dd>
        <dt>Contrat</dt>
        <dd>
          {formatMoney(me.wage)} par an, jusqu'en {formatContractEnd(me.contract_until)}
        </dd>
        {(me.caps > 0 || me.called_up) && (
          <>
            <dt>Sélection</dt>
            <dd>
              {plural(me.caps, "sélection")}
              {me.called_up && ` · appelé avec ${me.called_up.nation}`}
            </dd>
          </>
        )}
        <dt>Dernière journée</dt>
        <dd>
          {reward
            ? `${reward.xp > 0 ? `+${reward.xp} XP` : "Simulé, pas d'XP"}${reward.points ? `, ${plural(reward.points, "point")}` : ""}${
                reward.match ? ` · note ${formatNote(reward.match.rating ?? 6)}` : " · pas joué"
              }`
            : "—"}
        </dd>
      </dl>
      <XpBar xp={me.xp} perPoint={me.xp_per_point} />
      {me.nation && (
        <Gauge
          label="Chances d'être sélectionné"
          value={me.call_up_chance}
          text={me.eligible ? `${Math.round(me.call_up_chance * 100)} % · ${me.nation}` : `${me.nation} ne retient que ses clubs`}
        />
      )}
      <Gauge label="Ta confiance" value={(me.confidence + 1) / 2} text={confidenceLabel(me.confidence)} />
      <Gauge label="L'entraîneur" value={me.trust / 100} text={trustLabel(me.trust)} />
    </aside>
  );
  const attributes = (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Tes attributs</h2>
        <span className={me.points > 0 ? "hero-points" : "muted"}>
          {me.points > 0 ? `${plural(me.points, "point")} à placer` : "Joue pour gagner des points"}
        </span>
      </div>
      <div className="card">
        <ul className="hero-attributes">
          {[...me.attributes]
            .sort((a, b) => b.weight - a.weight)
            .map((attribute) => {
              const meta = ATTRIBUTES.find((a) => a.key === attribute.key);
              const affordable = attribute.cost !== null && attribute.cost <= me.points;
              return (
                <li key={attribute.key} className={attribute.weight ? "" : "hero-attribute--minor"}>
                  <span className="hero-attribute__label">
                    {meta.label}
                    <span className="muted">
                      {attribute.weight ? ` · ${Math.round(attribute.weight * 100)} % de ta note` : " · hors poste"}
                    </span>
                  </span>
                  <span className="hero-attribute__bar" aria-hidden="true">
                    <span style={{ width: `${(attribute.value / 20) * 100}%` }} />
                  </span>
                  <span className="num hero-attribute__value">{attribute.value}</span>
                  <button
                    type="button"
                    className="button button--small"
                    disabled={busy || !affordable}
                    title={
                      attribute.cost === null
                        ? "Au maximum"
                        : `${plural(attribute.cost, "point")} pour passer à ${attribute.value + 1}`
                    }
                    onClick={() => train(attribute.key)}
                  >
                    +1 <span className="muted">({attribute.cost ?? "max"})</span>
                  </button>
                </li>
              );
            })}
        </ul>
      </div>
    </section>
  );
  const matches = (
    <section className="section">
      <div className="section__head hero-matches__head">
        <div className="chips" role="group" aria-label="Période">
          {periods.map((p) => (
            <button key={p.key} type="button" className={phone || periods.length > 3 ? "chip chip--small" : "chip"} aria-pressed={period === p.key} onClick={() => setPeriod(p.key)}>
              {p.label}
            </button>
          ))}
        </div>
        {(period === "season" || period === "career") && (
          <span className="muted">
            {plural(played.length, "match")}, {plural(tries, "essai")}
            {average !== null && ` · ${formatNote(average)} de moyenne`}
          </span>
        )}
      </div>
      {period === "standings" ? (
        <HeroStandings season={state} clubId={clubId} nationId={me.nation_id} />
      ) : period === "internationals" && capped ? (
        <HeroInternationals nationId={me.nation_id} />
      ) : period === "career" ? (
        <div className="card card--padded hero-career">
          <HeroCareer />
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="table table--nowrap hero-matches">
            <thead>
              <tr>
                {!phone && (
                  <th scope="col" className="left">
                    Date
                  </th>
                )}
                <th scope="col" className="left">
                  Adversaire
                </th>
                <th scope="col">Score</th>
                <th scope="col">Min.</th>
                <th scope="col" title="Essais">{phone ? "Ess." : "Essais"}</th>
                <th scope="col">Note</th>
              </tr>
            </thead>
            <tbody>
              {me.matches.map((match) => (
                <tr key={`${match.international ? "test" : "club"}-${match.match_id}`}>
                  {!phone && <td className="left muted">{formatShortDate(match.date)}</td>}
                  <td className="left">
                    {/* Téléphone : la date passe sous l'adversaire, pour que tout tienne en largeur. */}
                    {phone ? (
                      <span className="with-crest" title={match.opponent.name}>
                        <ClubCrest name={match.opponent.name} size={24} />
                        <span className="hero-matches__who">
                          <span className="standings__name">{match.opponent.name}</span>
                          <span className="muted">
                            {formatShortDate(match.date)} · {venue(match)}
                          </span>
                        </span>
                      </span>
                    ) : (
                      <span className="with-crest">
                        <ClubCrest name={match.opponent.name} size={20} />
                        {match.opponent.name}
                        <span className="muted">{venue(match)}</span>
                      </span>
                    )}
                  </td>
                  <td className="num">
                    {match.score_for} – {match.score_against}
                  </td>
                  <td className="num">{match.minutes || <span className="muted">–</span>}</td>
                  <td className="num">{match.tries || <span className="muted">–</span>}</td>
                  <td className={`note${match.rating >= 7.5 ? " cell--strong" : ""}`}>
                    {match.minutes > 0 && match.rating !== null ? (
                      formatNote(match.rating)
                    ) : (
                      <span className="muted">–</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {me.matches.length === 0 && (
            <p className="table__note">
              Aucun match joué cette saison. <Link to="/calendrier">Voir le calendrier</Link>
            </p>
          )}
        </div>
      )}
    </section>
  );

  const endWindow = (
    <>
      {/* Un titre se fête d'abord, après la fenêtre de simulation, avant le bilan. */}
      {titles.length > 0 && !simulation && <TitleCelebration titles={titles} onDone={() => setTitles([])} />}
      {seasonEnd && finished && titles.length === 0 && (
        <HeroSeasonEnd
          name={`${me.first_name} ${me.last_name}`}
          playerId={me.player_id}
          onClose={() => setSeasonEnd(false)}
          onNextSeason={nextSeason}
          busy={busy}
          error={error}
        />
      )}
      {simulation && (
        <Simulation
          season={state}
          clubId={clubId}
          initialUntil={simulation.until}
          play={api.simulateHero}
          hero
          onPlayed={dayPlayed}
          onClose={closeSimulation}
        />
      )}
    </>
  );

  // Téléphone : un sous-onglet à la fois, comme la page Club.
  if (phone) {
    return (
      <>
        <ActionError error={error} />
        {endWindow}
        <div className="chips" role="group" aria-label="Vue">
          {PHONE_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className="chip"
              aria-pressed={view === tab.key}
              onClick={() => setView(tab.key)}
            >
              {tab.label}
              {tab.key === "progress" && me.points > 0 && ` (${me.points})`}
            </button>
          ))}
        </div>
        {view === "match" && <div className="hero-row">{matchCard}</div>}
        {view === "progress" && (
          <div className="hero-progress fill">
            {fiche}
            {attributes}
          </div>
        )}
        {view === "matches" && <div className="club-grid hero-grid fill">{matches}</div>}
      </>
    );
  }

  return (
    <>
      <ActionError error={error} />
      {endWindow}

      <div className="hero-row">
        {matchCard}
        {fiche}
      </div>

      <div className="club-grid hero-grid fill">
        {attributes}
        {matches}
      </div>
    </>
  );
}

// Domicile ou extérieur ; en sélection, la compétition d'abord.
const venue = (match) =>
  `${match.international ? `${match.competition} · ` : ""}${match.home ? "dom." : "ext."}`;

// Le calendrier international de la saison : matchs et classement de chaque fenêtre,
// sa sélection en accent (chargé quand on l'ouvre).
function HeroInternationals({ nationId }) {
  const calendar = useApi(useCallback(api.getInternationals, []));
  if (calendar.loading) return <p className="status">Chargement…</p>;
  if (calendar.error) return <p className="status status--error">{calendar.error.message}</p>;
  const { windows } = calendar.data;
  // D'abord la fenêtre où joue sa sélection, si elle n'est pas finie.
  const mine = windows.find((w) => !w.finished && w.nations.some((n) => n.id === nationId));
  return (
    <div className="hero-internationals">
      <WindowBoard windows={windows} initial={mine?.code} myId={nationId} />
    </div>
  );
}

// Le palmarès de toute la carrière (chargé quand on l'ouvre).
function HeroCareer() {
  const career = useApi(useCallback(api.getHeroCareer, []));
  if (career.loading) return <p className="status">Chargement…</p>;
  if (career.error) return <p className="status status--error">{career.error.message}</p>;
  return <CareerSummary career={career.data} />;
}

// Les classements des compétitions de son club : son championnat, et sa poule de chaque
// coupe d'Europe qu'il dispute. Son club en accent. Puis, s'il a un pays qui joue dans ce
// monde, le classement mondial des sélections, la sienne en accent.
function HeroStandings({ season, clubId, nationId }) {
  const competitions = [
    { key: season.league.code, label: season.league.short_name, league: true, rows: season.standings },
    ...season.cups.flatMap((cup) =>
      cup.pools
        .filter((pool) => pool.table.some((row) => row.club.id === clubId))
        .map((pool) => ({ key: cup.code, label: `${cup.name} · poule ${pool.pool}`, rows: pool.table })),
    ),
    ...(nationId ? [{ key: "world", label: "Classement mondial", world: true }] : []),
  ];
  const [code, setCode] = useState(competitions[0].key);
  const shown = competitions.find((c) => c.key === code) ?? competitions[0];
  return (
    <div className="card table-wrap hero-standings">
      {competitions.length > 1 && (
        <div className="chips hero-standings__picker" role="group" aria-label="Compétition">
          {competitions.map((c) => (
            <button key={c.key} type="button" className="chip chip--small" aria-pressed={c.key === shown.key} onClick={() => setCode(c.key)}>
              {c.label}
            </button>
          ))}
        </div>
      )}
      {shown.world ? (
        <HeroWorldRanking nationId={nationId} />
      ) : (
      <table className="table">
        <thead>
          <tr>
            <th scope="col" className="left">#</th>
            <th scope="col" className="left">Club</th>
            <th scope="col">J</th>
            <th scope="col">G</th>
            {shown.league && <th scope="col" className="hero-standings__detail">N</th>}
            {shown.league && <th scope="col" className="hero-standings__detail">P</th>}
            <th scope="col">Diff</th>
            <th scope="col">Pts</th>
          </tr>
        </thead>
        <tbody>
          {shown.rows.map((row, index) => {
            const club = shown.league ? { id: row.club_id, name: row.club_name } : row.club;
            const rank = shown.league ? row.rank : index + 1;
            const cut = shown.league ? rank === season.playoff_qualifiers : index === 1;
            return (
              <tr
                key={club.id}
                className={[club.id === clubId ? "table__row--mine" : "", cut ? "table__row--cut" : ""].join(" ")}
              >
                <td className="left muted">{rank}</td>
                <td className="left">
                  <span className="with-crest" title={club.name}>
                    <ClubCrest name={club.name} size={20} />
                    <span className="standings__name">{club.name}</span>
                  </span>
                </td>
                <td className="num">{row.played}</td>
                <td className="num">{row.won}</td>
                {shown.league && <td className="num hero-standings__detail">{row.drawn}</td>}
                {shown.league && <td className="num hero-standings__detail">{row.lost}</td>}
                <td className="num">{formatDiff(row.points_difference)}</td>
                <td className="num" style={{ fontWeight: 700 }}>
                  {row.league_points}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      )}
    </div>
  );
}

// Le classement mondial des sélections, son pays en accent (chargé quand on l'ouvre).
function HeroWorldRanking({ nationId }) {
  const ranking = useApi(useCallback(api.getRanking, []));
  if (ranking.loading) return <p className="table__note">Chargement…</p>;
  if (ranking.error) return <p className="table__note">{ranking.error.message}</p>;
  return <RankingTable nations={ranking.data.nations} highlight={[nationId]} />;
}

// Ce que disent les deux jauges de la fiche (engine/hero.py).
const confidenceLabel = (value) =>
  value <= -0.6
    ? "Au plus bas"
    : value <= -0.2
      ? "Fragile"
      : value < 0.2
        ? "Normale"
        : value < 0.6
          ? "En confiance"
          : "Euphorique";
const trustLabel = (value) =>
  value >= 70 ? "Totale : titulaire" : value >= 50 ? "Bonne" : value >= 30 ? "À gagner" : "Distante";

// Une jauge de la fiche, de 0 à 1.
function Gauge({ label, value, text }) {
  return (
    <div className="hero-xp">
      <span className="muted">
        {label} : <strong>{text}</strong>
      </span>
      <span className="hero-attribute__bar hero-xp__bar" aria-hidden="true">
        <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </span>
    </div>
  );
}

// L'expérience vers le prochain point d'attribut.
function XpBar({ xp, perPoint }) {
  return (
    <div className="hero-xp">
      <span className="muted">
        Prochain point : {xp} / {perPoint} XP
      </span>
      <span className="hero-attribute__bar hero-xp__bar" aria-hidden="true">
        <span style={{ width: `${(xp / perPoint) * 100}%` }} />
      </span>
    </div>
  );
}

// Le résultat du match de son club, dans la journée qui vient d'être jouée.
function LastDay({ played, clubId }) {
  const match = played.matches.find((m) => m.home.id === clubId || m.away.id === clubId);
  if (!match) return null;
  return (
    <p className="muted" style={{ margin: 0 }}>
      Dernier résultat : {match.home.name} {match.home_score} – {match.away_score} {match.away.name}
    </p>
  );
}
