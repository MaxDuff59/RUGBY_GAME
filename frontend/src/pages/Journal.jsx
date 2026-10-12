import { useCallback, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import MatchList from "../components/MatchList.jsx";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import { POSITIONS, formatLongDate, formatMoney, formatNote, formatShortDate, matchResult, scoreNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";

// Largeurs de la mise en page (les mêmes que les règles `@media` de `.journal`) : cinq
// colonnes sur grand écran, quatre en dessous, puis deux.
const WIDE_QUERY = "(min-width: 1700px)";
const MEDIUM_QUERY = "(min-width: 1280px)";

// Genre d'un article, tel que l'API le donne.
const KINDS = {
  result: "Résultat",
  preview: "À venir",
  standing: "Classement",
  transfer: "Transfert",
  market: "Mercato",
  injury: "Infirmerie",
  selection: "Sélections",
  club: "Coulisses",
};

// Rubriques, en pastilles. `scores` et `moves` : sur téléphone, la carte qui accompagne
// la rubrique (ordinateur : les deux sont toujours à l'écran).
const SECTIONS = [
  { key: "all", label: "À la une", keep: () => true },
  { key: "mine", keep: (article) => article.mine },
  { key: "results", label: "Résultats", keep: (article) => ["result", "standing"].includes(article.kind), scores: "last" },
  { key: "fixtures", label: "À venir", keep: (article) => article.kind === "preview", scores: "next" },
  { key: "transfers", label: "Transferts", keep: (article) => ["transfer", "market"].includes(article.kind), moves: true },
  { key: "medical", label: "Infirmerie", keep: (article) => article.kind === "injury" },
  { key: "nations", label: "Sélections", keep: (article) => article.international },
];

// Le journal : les nouvelles du monde, des clubs comme des sélections. La une et les
// articles mis en avant, le fil des brèves, les matchs de chaque compétition (joués et à
// venir) et les derniers mouvements de joueurs. Le même pour un manager de club et pour
// un sélectionneur : ce qui touche son équipe passe devant.
export default function Journal() {
  const { career } = useOutletContext();
  const journal = useApi(useCallback(api.getJournal, []));
  const phone = useMediaQuery(PHONE_QUERY);
  const wide = useMediaQuery(WIDE_QUERY);
  const medium = useMediaQuery(MEDIUM_QUERY);
  const [sectionKey, setSectionKey] = useState("all");

  if (journal.loading) return <p className="status">Chargement…</p>;
  if (journal.error) return <p className="status status--error">{journal.error.message}</p>;

  const { articles, competitions, moves, prospects, today, year, focus } = journal.data;
  const selector = career.kind === "nation";
  const section = SECTIONS.find((entry) => entry.key === sectionKey);
  const labelOf = (entry) => entry.label ?? (selector ? "Ma sélection" : "Mon club");
  const [lead, ...others] = articles.filter(section.keep);
  // Articles mis en avant autour de la une, selon la place ; le reste part dans le fil.
  const slots = phone ? 2 : wide ? 5 : medium ? 2 : 0;
  const featured = others.slice(0, slots);
  const feed = others.slice(slots);

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Journal</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Édition du {formatLongDate(today)} · saison {year}-{String(year + 1).slice(2)}
          </p>
        </div>
        <div className={`chips${phone ? " chips--scroll" : ""}`} role="group" aria-label="Rubrique">
          {SECTIONS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              className="chip"
              aria-pressed={entry.key === sectionKey}
              onClick={() => setSectionKey(entry.key)}
            >
              {labelOf(entry)}
            </button>
          ))}
        </div>
      </header>

      <div className="journal fill">
        {phone && section.scores && (
          <Scores key={section.scores} competitions={competitions} focus={focus} myId={career.club_id} forced={section.scores} />
        )}
        {phone && section.moves && <Moves moves={moves} prospects={prospects} market={!selector} />}

        {lead ? (
          <Story article={lead} variant="lead" area="lead" />
        ) : (
          <div className="card story story--empty" style={{ gridArea: "lead" }}>
            <div className="story__frame">
              <p className="eyebrow">{labelOf(section)}</p>
              <p className="muted">Rien à signaler dans cette rubrique pour l'instant.</p>
            </div>
          </div>
        )}
        {featured.slice(0, 3).map((article, index) => (
          <Story key={article.id} article={article} area={`s${index + 1}`} />
        ))}
        {featured.length > 3 && (
          <div className="journal__pair">
            {featured.slice(3).map((article) => (
              <Story key={article.id} article={article} variant="brief" />
            ))}
          </div>
        )}

        <Feed articles={feed} />
        {!phone && <Scores competitions={competitions} focus={focus} myId={career.club_id} />}
        {!phone && <Moves moves={moves} prospects={prospects} market={!selector} />}
      </div>
    </>
  );
}

// Rubrique et compétition d'un article, en libellé ; un point d'accent s'il nous concerne.
function Kicker({ article, flag = null, date = false }) {
  return (
    <p className={`story__kicker${article.mine ? " story__kicker--mine" : ""}`}>
      {flag && <span className="story__flag">{flag}</span>}
      <span>
        {KINDS[article.kind]}
        {article.competition ? ` · ${article.competition}` : ""}
      </span>
      {date && <span className="story__date">{formatShortDate(article.date)}</span>}
    </p>
  );
}

// Le titre mène à la fiche du joueur quand l'article en a une.
function Headline({ article }) {
  const playerId = article.player?.id ?? null;
  return playerId !== null ? <Link to={`/joueurs/${playerId}`}>{article.title}</Link> : article.title;
}

// Un article : la une (`lead`, illustration à droite), une carte (illustration en tête)
// ou une brève (`brief`, sans illustration).
function Story({ article, variant = "card", area }) {
  return (
    // La carte sert de repère de taille : son cadre s'adapte à la place qu'elle reçoit.
    <article className={`card story story--${variant}`} style={area ? { gridArea: area } : undefined}>
      <div className="story__frame">
        {variant !== "brief" && <Visual article={article} large={variant === "lead"} />}
        <div className="story__text">
          <Kicker article={article} flag={variant === "lead" ? "À la une" : null} />
          <h2 className="story__title">
            <Headline article={article} />
          </h2>
          <p className="story__body">{article.body}</p>
          <p className="story__meta">{formatShortDate(article.date)}</p>
        </div>
      </div>
    </article>
  );
}

// Ce qui illustre un article : la feuille de score d'un match, le portrait d'un joueur
// (et son trajet pour un mouvement), ou les blasons.
function Visual({ article, large }) {
  const { match, move, player, teams } = article;
  if (match) {
    return (
      <div className="story__visual">
        <ScoreBox match={match} large={large} />
      </div>
    );
  }
  if (player) {
    const crest = move ? null : teams[0]?.name;
    return (
      <div className="story__visual story__visual--portrait">
        <span className="portrait">
          <PlayerAvatar src={player.photo} size={large ? 112 : 64} />
          {crest && <ClubCrest name={crest} size={large ? 40 : 26} className="portrait__crest" />}
        </span>
        {move && (
          <span className="story__route">
            <Route move={move} size={large ? 36 : 24} />
            <span className="muted">{moveLabel(move)}</span>
          </span>
        )}
      </div>
    );
  }
  if (teams.length === 0) return null;
  return (
    <div className="story__visual story__visual--portrait">
      {teams.map((team) => (
        <ClubCrest key={team.id} name={team.name} size={large ? 104 : 60} />
      ))}
    </div>
  );
}

// Feuille de score : une ligne par équipe, le score à droite, le battu en gris. Avant le
// match : les deux équipes et le jour.
function ScoreBox({ match, large }) {
  const played = match.home_score !== null;
  const note = played ? scoreNote(match) : `${formatLongDate(match.date)}${match.neutral ? " · terrain neutre" : ""}`;
  const sides = [
    { team: match.home, score: match.home_score },
    { team: match.away, score: match.away_score },
  ];
  return (
    <div className={`scorebox${large ? " scorebox--large" : ""}`}>
      {sides.map(({ team, score }) => (
        <div key={team.id} className={`scorebox__row${played && matchResult(match, team.id) === "D" ? " scorebox__row--lost" : ""}`}>
          <ClubCrest name={team.name} size={large ? 44 : 26} />
          <span className="scorebox__name">{team.name}</span>
          {played && <span className="scorebox__score num">{score}</span>}
        </div>
      ))}
      {note && <p className="scorebox__note">{note}</p>}
    </div>
  );
}

// Le trajet d'un joueur : d'où il vient, où il va ; un rond en pointillé s'il est sans club.
function Route({ move, size = 20 }) {
  const end = (club, label) =>
    club ? (
      <span title={club.name}>
        <ClubCrest name={club.name} size={size} />
      </span>
    ) : (
      <span className="route__none" style={{ width: size, height: size }} title={label} />
    );
  return (
    <span className="route">
      {end(move.origin, "Sans club")}
      <svg width="16" height="10" viewBox="0 0 16 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M1 5h13m-3.5-3.5L14 5l-3.5 3.5" />
      </svg>
      {end(move.destination, move.kind === "retirement" ? "Retraite" : "Sans club")}
    </span>
  );
}

// Ce qu'on retient d'un mouvement en deux mots : l'indemnité, ou sa nature.
function moveLabel(move) {
  if (move.pending) return "À l'intersaison";
  if (move.kind === "transfer") return move.fee ? formatMoney(move.fee) : "Transfert";
  return { loan: "Prêt", free: "Libre", precontract: "Fin de contrat", joker: "Joker médical", release: "Fin de contrat", retirement: "Retraite" }[
    move.kind
  ];
}

// Le fil : toutes les autres nouvelles, les plus lourdes d'abord.
function Feed({ articles }) {
  return (
    <section className="card panel" style={{ gridArea: "feed" }}>
      <div className="panel__head">
        <h2 className="eyebrow">Le fil</h2>
        <span className="muted">
          {articles.length} brève{articles.length > 1 ? "s" : ""}
        </span>
      </div>
      <div className="panel__body">
        {articles.length === 0 && <p className="table__note">Rien d'autre pour l'instant.</p>}
        <ul className="feed">
          {articles.map((article) => (
            <li key={article.id} className="feed__item">
              <span className="feed__icon">
                {article.player ? (
                  <PlayerAvatar src={article.player.photo} size={34} />
                ) : (
                  article.teams.slice(0, 2).map((team) => <ClubCrest key={team.id} name={team.name} size={article.teams.length > 1 ? 20 : 30} />)
                )}
              </span>
              <div className="feed__text">
                <Kicker article={article} date />
                <h3 className="feed__title">
                  <Headline article={article} />
                </h3>
                <p className="feed__body">{article.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// Les matchs d'une compétition au choix : sa dernière journée jouée, ou la prochaine.
// `forced` (téléphone) : la rubrique impose l'une des deux.
function Scores({ competitions, focus, myId, forced = null }) {
  const [code, setCode] = useState(focus ?? competitions[0]?.code);
  const [choice, setChoice] = useState(null);
  const competition = competitions.find((entry) => entry.code === code) ?? competitions[0];
  if (!competition) return null;
  // Sans choix : les résultats s'il y en a, sinon les affiches à venir.
  const wanted = forced ?? choice ?? "last";
  const mode = competition[wanted] ? wanted : wanted === "last" ? "next" : "last";
  const round = competition[mode];

  return (
    <section className="card panel" style={{ gridArea: "scores" }}>
      <div className="panel__head">
        <h2 className="eyebrow">Matchs</h2>
        <select className="input tactics__select" aria-label="Compétition" value={competition.code} onChange={(event) => setCode(event.target.value)}>
          {competitions.map((entry) => (
            <option key={entry.code} value={entry.code}>
              {entry.name}
            </option>
          ))}
        </select>
      </div>
      <div className="panel__bar">
        {!forced && (
          <div className="chips" role="group" aria-label="Matchs joués ou à venir">
            {[
              ["last", "Résultats"],
              ["next", "À venir"],
            ].map(([key, label]) => (
              <button key={key} type="button" className="chip chip--small" aria-pressed={mode === key} disabled={!competition[key]} onClick={() => setChoice(key)}>
                {label}
              </button>
            ))}
          </div>
        )}
        {round && (
          <span className="muted">
            {round.label} · {formatShortDate(round.date)}
          </span>
        )}
      </div>
      <div className="panel__body">
        {round ? (
          <MatchList matches={round.matches} myClubId={myId} />
        ) : (
          <p className="table__note">Aucun match dans cette compétition pour l'instant.</p>
        )}
      </div>
    </section>
  );
}

// Un joueur dans la carte des transferts : photo, nom (vers sa fiche s'il en a une), poste et âge.
function Who({ player }) {
  return (
    <>
      <PlayerAvatar src={player.photo} size={32} />
      <span className="move__who">
        <span className="move__name">{player.id !== null ? <Link to={`/joueurs/${player.id}`}>{player.name}</Link> : player.name}</span>
        <span className="muted">
          {POSITIONS[player.position].label} · {player.age} ans
        </span>
      </span>
    </>
  );
}

// Les derniers mouvements de joueurs, les plus récents (et les mieux notés) d'abord, puis
// les joueurs à suivre : en fin de contrat (à signer en pré-contrat) ou sans club.
function Moves({ moves, prospects, market }) {
  return (
    <section className="card panel" style={{ gridArea: "moves" }}>
      <div className="panel__head">
        <h2 className="eyebrow">Transferts</h2>
        {market && (
          <Link to="/transferts" className="muted">
            Voir le marché
          </Link>
        )}
      </div>
      <div className="panel__body">
        {moves.length === 0 && (
          <p className="table__note">Aucun mouvement pour l'instant.</p>
        )}
        <ul className="moves">
          {moves.map((move) => (
            <li key={move.id} className={`move${move.mine ? " move--mine" : ""}`} title={formatLongDate(move.date)}>
              <Who player={move.player} />
              <span className="move__deal">
                <Route move={move} />
                <span className="muted">{moveLabel(move)}</span>
              </span>
            </li>
          ))}
        </ul>
        {prospects.length > 0 && (
          <>
            <div className="matches__stage">À suivre sur le marché</div>
            <ul className="moves">
              {prospects.map(({ player, club, mine }) => (
                <li key={player.id} className={`move${mine ? " move--mine" : ""}`}>
                  <Who player={player} />
                  <span className="move__deal">
                    {club ? (
                      <span title={club.name}>
                        <ClubCrest name={club.name} size={20} />
                      </span>
                    ) : (
                      <span className="route__none" style={{ width: 20, height: 20 }} title="Sans club" />
                    )}
                    <span className="muted">
                      {club ? "Fin de contrat" : "Libre"} · {formatNote(player.overall)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
