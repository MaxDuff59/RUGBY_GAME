import { useCallback, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import MatchList from "../components/MatchList.jsx";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import Story, { Headline, Kicker, Route, Who, moveLabel } from "../components/Story.jsx";
import { formatLongDate, formatNote, formatShortDate } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";

// Largeurs de la mise en page (les mêmes que les règles `@media` de `.journal`) : cinq
// colonnes sur grand écran, quatre en dessous, puis deux.
const WIDE_QUERY = "(min-width: 1700px)";
const MEDIUM_QUERY = "(min-width: 1280px)";

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
