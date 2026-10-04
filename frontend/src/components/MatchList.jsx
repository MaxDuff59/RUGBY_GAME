// Liste d'affiches d'une journée : domicile, score (ou « – »), extérieur.
// Le club du joueur est mis en avant.
export default function MatchList({ matches, myClubId }) {
  return (
    <ul className="matches">
      {matches.map((match) => {
        const played = match.home_score !== null;
        const mine = match.home.id === myClubId || match.away.id === myClubId;
        return (
          <li key={match.id} className={`match${mine ? " match--mine" : ""}`}>
            <span className="match__home">{match.home.name}</span>
            <span className="match__score num">
              {played ? `${match.home_score} – ${match.away_score}` : "–"}
            </span>
            <span className="match__away">{match.away.name}</span>
          </li>
        );
      })}
    </ul>
  );
}
