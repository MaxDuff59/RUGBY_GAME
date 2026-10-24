import { useState } from "react";

import ClubCrest from "./ClubCrest.jsx";
import MatchReport from "./MatchReport.jsx";
import WeatherIcon from "./WeatherIcon.jsx";
import { scoreNote } from "../format.js";

// Liste d'affiches d'une journée : domicile, score (ou « – »), extérieur, et sous le
// score le temps du match (la prévision s'il est à venir). Le club du joueur est mis en
// avant. Prolongation et tirs au but sont notés sous le score. Un match joué s'ouvre
// en fiche (`MatchReport`) ; `reports` à false pour les matchs internationaux, qui n'en ont pas.
export default function MatchList({ matches, myClubId, reports = true }) {
  const [open, setOpen] = useState(null);
  return (
    <>
      <ul className="matches">
        {matches.map((match) => {
          const played = match.home_score !== null;
          const mine = match.home.id === myClubId || match.away.id === myClubId;
          const note = played ? scoreNote(match) : null;
          const linked = played && reports;
          return (
            <li
              key={match.id}
              className={`match${mine ? " match--mine" : ""}${linked ? " match--link" : ""}`}
              onClick={linked ? () => setOpen(match) : undefined}
            >
              <span className="match__home">
                {match.home.name}
                <ClubCrest name={match.home.name} size={20} />
              </span>
              <span className="match__score num">
                {linked ? (
                  <button type="button" className="match__open" aria-label={`Fiche du match ${match.home.name} – ${match.away.name}`}>
                    {match.home_score} – {match.away_score}
                  </button>
                ) : played ? (
                  `${match.home_score} – ${match.away_score}`
                ) : (
                  "–"
                )}
                {(note || match.weather) && (
                  <small className="match__note">
                    {note}
                    <WeatherIcon weather={match.weather} size={14} className="match__weather" />
                  </small>
                )}
              </span>
              <span className="match__away">
                <ClubCrest name={match.away.name} size={20} />
                {match.away.name}
              </span>
            </li>
          );
        })}
      </ul>
      {open && <MatchReport summary={open} myClubId={myClubId} onClose={() => setOpen(null)} />}
    </>
  );
}
