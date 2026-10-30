import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { ActionError } from "../components/FullGame.jsx";
import HeroSeasonEnd, { CareerSummary } from "../components/HeroSeasonEnd.jsx";
import {
  ATTRIBUTES,
  COACH_NOTES,
  HERO_STATUS,
  formatContractEnd,
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

const plural = (n, word) => `${n} ${word}${n > 1 ? "s" : ""}`;

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
  const { career } = useOutletContext();
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
  const [showCareer, setShowCareer] = useState(false); // toute la carrière, saison par saison
  const [seasonEnd, setSeasonEnd] = useState(false); // la fenêtre du bilan et du mercato

  const { setData: setSeason } = season;
  const { reload: reloadHero } = hero;

  // La page Match renvoie ici avec la journée qu'elle vient de finir (une seule fois).
  const applied = useRef(null);
  useEffect(() => {
    const played = location.state?.played;
    if (!played || applied.current === played) return;
    applied.current = played;
    setLastDay(played);
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

  // Simuler : son match se joue quand même avec lui (le moteur du direct, joué d'une
  // traite : la voie sûre à chaque action) ; sans lui (blessé, club au repos), la journée.
  const simulate = (withHero) =>
    run(async () => {
      if (withHero && !liveMatch.data) await api.startLive();
      const result = withHero ? await api.finishLive() : await api.playMatchday();
      setLastDay(result);
      setSeason(result.season);
      liveMatch.setData(null);
      reloadHero();
    });

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
  const myMatch = next?.matches.find((m) => m.home.id === career.club_id || m.away.id === career.club_id);
  const available = me.status === "starter" || me.status === "bench";
  const finished = state.phase === "finished";
  const standing = state.standings.find((row) => row.club_id === career.club_id);
  const rank = standing?.played ? standing.rank : null;
  const reward = lastDay?.hero ?? me.last_reward;
  // Son match en sélection passe avant celui de son club s'il tombe avant.
  const test = me.called_up && (!myMatch || me.called_up.date <= next.date) ? me.called_up : null;
  const played = me.matches.filter((m) => m.minutes > 0);
  const average = played.length ? played.reduce((sum, m) => sum + (m.rating ?? 6), 0) / played.length : null;
  const tries = me.matches.reduce((sum, m) => sum + m.tries, 0);

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
            <button type="button" className="button" disabled={busy} onClick={() => simulate(false)}>
              {busy ? "Journée en cours…" : "Simuler"}
            </button>
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
                ? "L'entraîneur te titularise."
                : `Tu commences sur le banc : l'entraîneur te fait entrer à la ${me.entry}e minute.`
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
            <button
              type="button"
              className={available ? "button" : "button button--primary"}
              disabled={busy}
              onClick={() => simulate(available)}
            >
              {busy
                ? "Journée en cours…"
                : available
                  ? "Simuler"
                  : me.status === "injured"
                    ? "Se soigner"
                    : "Jouer la journée"}
            </button>
            {available && (
              <span className="muted">En direct, le match s'arrête sur tes actions : à toi de choisir.</span>
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
            <button type="button" className="button button--primary" disabled={busy} onClick={() => simulate(false)}>
              {busy ? "Journée en cours…" : "Jouer la journée"}
            </button>
          </div>
        </>
      )}
      {lastDay?.played && <LastDay played={lastDay.played} clubId={career.club_id} />}
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
            ? `+${reward.xp} XP${reward.points ? `, ${plural(reward.points, "point")}` : ""}${
                reward.match ? ` · note ${formatNote(reward.match.rating ?? 6)}` : " · pas joué"
              }`
            : "—"}
        </dd>
      </dl>
      <XpBar xp={me.xp} perPoint={me.xp_per_point} />
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
      <div className="section__head">
        <div className="chips" role="group" aria-label="Période">
          <button type="button" className="chip" aria-pressed={!showCareer} onClick={() => setShowCareer(false)}>
            Cette saison
          </button>
          <button type="button" className="chip" aria-pressed={showCareer} onClick={() => setShowCareer(true)}>
            Ta carrière
          </button>
        </div>
        <span className="muted">
          {plural(played.length, "match")}, {plural(tries, "essai")}
          {average !== null && ` · ${formatNote(average)} de moyenne`}
        </span>
      </div>
      {showCareer ? (
        <div className="card card--padded hero-career">
          <HeroCareer />
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="table table--nowrap">
            <thead>
              <tr>
                <th scope="col" className="left">
                  Date
                </th>
                <th scope="col" className="left">
                  Adversaire
                </th>
                <th scope="col">Score</th>
                <th scope="col">Min.</th>
                <th scope="col">Essais</th>
                <th scope="col">Note</th>
              </tr>
            </thead>
            <tbody>
              {me.matches.map((match) => (
                <tr key={match.match_id}>
                  <td className="left muted">{formatShortDate(match.date)}</td>
                  <td className="left">
                    <span className="with-crest">
                      <ClubCrest name={match.opponent.name} size={20} />
                      {match.opponent.name}
                      <span className="muted">{match.home ? "dom." : "ext."}</span>
                    </span>
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

  const endWindow = seasonEnd && finished && (
    <HeroSeasonEnd
      name={`${me.first_name} ${me.last_name}`}
      onClose={() => setSeasonEnd(false)}
      onNextSeason={nextSeason}
      busy={busy}
      error={error}
    />
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

// Le palmarès de toute la carrière (chargé quand on l'ouvre).
function HeroCareer() {
  const career = useApi(useCallback(api.getHeroCareer, []));
  if (career.loading) return <p className="status">Chargement…</p>;
  if (career.error) return <p className="status status--error">{career.error.message}</p>;
  return <CareerSummary career={career.data} />;
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
