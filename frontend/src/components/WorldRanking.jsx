import { formatRankingChange, formatRankingPoints, formatShortDate } from "../format.js";
import ClubCrest from "./ClubCrest.jsx";

// Le classement mondial des sélections (backend/engine/ranking.py) : rang, mouvement depuis
// la dernière journée de tests, points. `highlight` : les identifiants des sélections à
// mettre en avant (la sienne, celle de ses joueurs). `limit` : n'afficher que les premières,
// plus celles mises en avant si elles sont plus bas.
export function RankingTable({ nations, highlight = [], limit = null }) {
  const mine = new Set(highlight);
  const rows = limit === null ? nations : nations.filter((n) => n.rank <= limit || mine.has(n.nation.id));
  return (
    <table className="table table--nowrap ranking">
      <thead>
        <tr>
          <th scope="col" className="left">#</th>
          <th scope="col" className="left">Sélection</th>
          <th scope="col">Points</th>
          <th scope="col" title="Depuis la dernière journée de tests">Évol.</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => {
          const gap = index > 0 && row.rank - rows[index - 1].rank > 1;
          return (
            <tr
              key={row.nation.id}
              className={[mine.has(row.nation.id) ? "table__row--mine" : "", gap ? "ranking__gap" : ""].join(" ")}
            >
              <td className="left">
                <span className="ranking__rank">{row.rank}</span>
                <Movement row={row} />
              </td>
              <td className="left">
                <span className="with-crest" title={row.nation.name}>
                  <ClubCrest name={row.nation.name} size={20} />
                  <span className="standings__name">{row.nation.name}</span>
                </span>
              </td>
              <td className="num" style={{ fontWeight: 700 }}>
                {formatRankingPoints(row.points)}
              </td>
              <td className="num">
                <PointsChange change={row.points - row.previous_points} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// Places gagnées ou perdues depuis la dernière journée de tests.
function Movement({ row }) {
  const places = row.previous_rank - row.rank;
  if (places === 0) return null;
  const up = places > 0;
  return (
    <span
      className={`delta ranking__move ${up ? "delta--up" : "delta--down"}`}
      title={`${up ? "Gagne" : "Perd"} ${Math.abs(places)} place${Math.abs(places) > 1 ? "s" : ""}`}
    >
      {up ? "▲" : "▼"}
      {Math.abs(places)}
    </span>
  );
}

function PointsChange({ change }) {
  const rounded = Math.round(change * 100) / 100;
  if (rounded === 0) return <span className="delta delta--flat">–</span>;
  return <span className={`delta ${rounded > 0 ? "delta--up" : "delta--down"}`}>{formatRankingChange(rounded)}</span>;
}

// Les derniers tests et les points qu'ils ont fait passer d'une sélection à l'autre.
export function RankingMoves({ moves, highlight = [] }) {
  const mine = new Set(highlight);
  if (moves.length === 0) {
    return <p className="table__note">Aucun test joué : c'est le classement de départ.</p>;
  }
  return (
    <ul className="ranking-moves">
      {moves.map((move, index) => {
        const ours = mine.has(move.home.id) || mine.has(move.away.id);
        return (
          <li key={`${move.date}-${move.home.id}-${index}`} className={ours ? "ranking-moves__item--mine" : undefined}>
            <span className="muted ranking-moves__when">
              {formatShortDate(move.date)} · {move.competition}
            </span>
            <span className="ranking-moves__side ranking-moves__side--home">
              <ClubCrest name={move.home.name} size={18} />
              <span className="ranking-moves__name">{move.home.name}</span>
              <PointsChange change={move.change} />
            </span>
            <span className="ranking-moves__score">
              {move.home_score} – {move.away_score}
            </span>
            <span className="ranking-moves__side ranking-moves__side--away">
              <PointsChange change={-move.change} />
              <span className="ranking-moves__name">{move.away.name}</span>
              <ClubCrest name={move.away.name} size={18} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// La place d'une sélection au classement (null si on ne la connaît pas).
export const rankOf = (ranking, nationId) => ranking?.nations.find((n) => n.nation.id === nationId) ?? null;
