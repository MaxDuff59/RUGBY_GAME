import { Link } from "react-router-dom";

import { POSITIONS, formatLongDate, formatMoney, formatShortDate, matchResult, scoreNote } from "../format.js";
import ClubCrest from "./ClubCrest.jsx";
import PlayerAvatar from "./PlayerAvatar.jsx";

// Les articles du journal et ce qui les illustre : la page Journal, et l'extrait du
// tableau de bord.

// Genre d'un article, tel que l'API le donne.
const KINDS = {
  result: "Résultat",
  preview: "À venir",
  standing: "Classement",
  transfer: "Transfert",
  market: "Mercato",
  injury: "Infirmerie",
  discipline: "Discipline",
  selection: "Sélections",
  club: "Coulisses",
};

// Rubrique et compétition d'un article, en libellé ; un point d'accent s'il nous concerne.
export function Kicker({ article, flag = null, date = false }) {
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
export function Headline({ article }) {
  const playerId = article.player?.id ?? null;
  return playerId !== null ? <Link to={`/joueurs/${playerId}`}>{article.title}</Link> : article.title;
}

// Un article : la une (`lead`, illustration à droite), une carte (illustration en tête)
// ou une brève (`brief`, sans illustration).
export default function Story({ article, variant = "card", area }) {
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
export function Route({ move, size = 20 }) {
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
export function moveLabel(move) {
  if (move.pending) return "À l'intersaison";
  if (move.kind === "transfer") return move.fee ? formatMoney(move.fee) : "Transfert";
  return { loan: "Prêt", free: "Libre", precontract: "Fin de contrat", joker: "Joker médical", release: "Fin de contrat", retirement: "Retraite" }[
    move.kind
  ];
}

// Un joueur dans une liste de mouvements : photo, nom (vers sa fiche s'il en a une), poste et âge.
export function Who({ player }) {
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
