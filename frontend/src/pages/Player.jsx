import { useCallback, useRef } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";

import { api } from "../api.js";
import Pitch from "../components/Pitch.jsx";
import Radar from "../components/Radar.jsx";
import Swarm from "../components/Swarm.jsx";
import {
  ATTRIBUTES,
  INJURY_SOURCES,
  KEY_ATTRIBUTES,
  POSITIONS,
  SEVERITIES,
  formatContractEnd,
  formatMoney,
  formatNote,
  formatPercent,
  formatShortDate,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { usePitchWidth } from "../hooks/usePitchWidth.js";
import { SLOTS, jerseyNumbers } from "../lineup.js";

// Notes du moteur, dans l'ordre d'affichage.
const RATINGS = [
  { key: "scrum", label: "Mêlée" },
  { key: "lineout", label: "Touche" },
  { key: "carrying", label: "Portage" },
  { key: "attack", label: "Attaque" },
  { key: "defense", label: "Défense" },
];

// Libellés courts des postes, pour tenir sur le terrain.
const SHORT_POSITIONS = {
  PROP: "Pilier",
  HOOKER: "Talonneur",
  LOCK: "2e ligne",
  BACK_ROW: "3e ligne",
  SCRUM_HALF: "Mêlée",
  FLY_HALF: "Ouvreur",
  CENTRE: "Centre",
  WING: "Ailier",
  FULLBACK: "Arrière",
};

// Fiche complète d'un joueur : identité, comparaison à son poste, où il peut
// jouer, notes du moteur, saison en cours et blessures.
export default function Player() {
  const { playerId } = useParams();
  const { career } = useOutletContext();
  const navigate = useNavigate();
  const detail = useApi(useCallback(() => api.getPlayer(playerId), [playerId]));
  const clubId = detail.data?.club?.id ?? null;
  const club = useApi(useCallback(() => (clubId === null ? Promise.resolve(null) : api.getClub(clubId)), [clubId]));
  const pitchCardRef = useRef(null);
  const pitchWidth = usePitchWidth(pitchCardRef, Boolean(detail.data));

  if (detail.loading || club.loading) return <p className="status">Chargement de la fiche…</p>;
  if (detail.error) return <p className="status status--error">{detail.error.message}</p>;
  if (club.error) return <p className="status status--error">{club.error.message}</p>;

  const data = detail.data;
  const { player } = data;
  const position = POSITIONS[player.position];
  const isYouth = player.squad === "youth";
  // Les espoirs n'ont pas de numéro : l'effectif renvoyé par /clubs ne contient que les pros.
  const squadPlayers = !isYouth && club.data ? club.data.players : [];
  const jerseys = jerseyNumbers(squadPlayers, data.lineup_ids);
  const jersey = jerseys.get(player.id) ?? null;
  const mine = data.club?.id === career.club_id;
  const peerLabel = `${position.label.toLowerCase()}s`;

  // Sur le terrain : sa note à chaque place ; son poste naturel en accent, sa place actuelle numérotée.
  const markers = SLOTS.map((slot) => ({
    key: slot.number,
    x: slot.x,
    y: slot.y,
    number: formatNote(data.position_ratings[slot.position]),
    label: slot.number === jersey ? `n° ${slot.number} · lui` : SHORT_POSITIONS[slot.position],
    tone: slot.position === player.position ? "accent" : "muted",
  }));

  // Essaims : la note au poste, puis les attributs qui comptent pour ce poste.
  const swarmPoints = (key) =>
    data.peers.map((peer) => ({
      id: peer.id,
      value: peer[key],
      tone: peer.id === player.id ? "player" : peer.club_id === data.club?.id ? "teammate" : undefined,
    }));
  const swarms = [
    { key: "position_rating", label: `Note au poste` },
    ...KEY_ATTRIBUTES[player.position].map((key) => ({
      key,
      label: ATTRIBUTES.find((attr) => attr.key === key).label,
    })),
  ];

  return (
    <>
      <header className="player-head">
        <div className="player-head__identity">
          <p className="eyebrow">
            <button type="button" className="link-button" onClick={() => navigate(-1)}>← Retour</button>
            {" · "}
            {data.club ? <Link to={mine ? "/effectif" : "/transferts"}>{data.club.name}</Link> : <Link to="/transferts">Agent libre</Link>}
            {data.club && " · "}
            {data.club && (isYouth ? "Espoir" : jersey !== null ? `Titulaire · n° ${jersey}` : "Remplaçant")}
          </p>
          <h1 className="title player-head__name">
            <span className="player-head__first">{player.first_name}</span>
            {player.last_name}
          </h1>
          <p className="muted player-head__line">
            {position.label} · {player.age} ans ·{" "}
            {data.club
              ? `contrat jusqu'en juin ${formatContractEnd(player.contract_until)}`
              : `sans contrat depuis juin ${formatContractEnd(player.contract_until)}`}
            {player.loaned_from_name && ` · prêté par ${player.loaned_from_name}`}
            {player.injury?.status === "active" && (
              <>
                {" · "}
                <span className="tag tag--injured">Blessé</span> retour le {formatShortDate(player.injury.return_date)}
              </>
            )}
            {player.injury?.status === "fragile" && (
              <>
                {" · "}
                <span className="tag tag--fragile">Fragile</span> jusqu'au {formatShortDate(player.injury.fragile_until)}
              </>
            )}
          </p>
        </div>

        <div className="player-head__stats">
          <Stat value={data.season.matches} label="matchs" />
          <Stat value={data.season.tries} label="essais" />
          <Stat value={data.season.points} label="points" />
          <Stat value={formatMoney(player.wage)} label="salaire / saison" />
          <Stat value={formatMoney(player.value)} label="valeur" />
          <div className="stat player-head__overall">
            <span className="player-head__note">{formatNote(player.overall)}</span>
            <span className="muted">note · meilleur que {Math.round(data.better_than.overall * 100)} % des {peerLabel}</span>
          </div>
        </div>
      </header>

      <div className="player-grid fill">
        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Comparé aux {peerLabel}</h2>
            <span className="muted">{data.peers.length - 1} autres {peerLabel}</span>
          </div>
          <div className="card card--padded player-card player-card--graphs">
            <div className="player-card__radar">
              <Radar axes={ATTRIBUTES} values={player} />
            </div>
            <div className="swarms">
              {swarms.map((swarm) => (
                <Swarm key={swarm.key} label={swarm.label} points={swarmPoints(swarm.key)} playerId={player.id} />
              ))}
            </div>
            <p className="table__note player-card__note player-card__legend">
              <span className="legend legend--player">Lui</span>
              <span className="legend legend--teammate">Coéquipiers</span>
              <span className="legend legend--others">Autres {peerLabel}</span>
              <span>Percentile : part des {peerLabel} qu'il devance.</span>
            </p>
          </div>
        </section>

        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Où il peut jouer</h2>
            <span className="muted">Naturel : {position.label}</span>
          </div>
          <div ref={pitchCardRef} className="card card--padded player-card">
            <Pitch compact markers={markers} style={{ width: pitchWidth ?? "100%", maxWidth: "100%", margin: "0 auto" }} />
            <p className="table__note player-card__note">
              Sa note à chaque place, selon le critère que le staff utilise pour choisir les titulaires.
              {jersey !== null && ` Il occupe le n° ${jersey}.`}
            </p>
          </div>
        </section>

        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Notes du moteur</h2>
            <span className="muted">Sur 20</span>
          </div>
          <div className="card card--padded player-card">
            <div className="strength">
              {RATINGS.map((rating) => (
                <div key={rating.key} className="strength__row">
                  <span className="strength__label">{rating.label}</span>
                  <div className="meter">
                    <div className="meter__fill" style={{ width: `${(data.ratings[rating.key] / 20) * 100}%` }} />
                  </div>
                  <span className="strength__value num">{formatNote(data.ratings[rating.key])}</span>
                </div>
              ))}
            </div>

            <h3 className="eyebrow player-card__sub">Saison {data.season.year ?? ""}</h3>
            <div className="situation">
              <Fact label="Matchs joués" value={data.season.matches} />
              <Fact label="Essais" value={data.season.tries} />
              <Fact label="Transformations" value={data.season.conversions} />
              <Fact label="Pénalités" value={data.season.penalties} />
              <Fact label="Drops" value={data.season.drops} />
              <Fact label="Points" value={data.season.points} />
            </div>

            <h3 className="eyebrow player-card__sub">Blessures · {data.injuries.length}</h3>
            {data.injuries.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>Jamais blessé.</p>
            ) : (
              <ul className="injury-list injury-list--flush">
                {data.injuries.map((injury) => (
                  <li key={injury.id}>
                    <span className={`tag tag--${injury.severity}`}>{SEVERITIES[injury.severity].label}</span>
                    <span style={{ fontWeight: 600 }}>{injury.kind}</span>
                    <span className="muted">
                      {INJURY_SOURCES[injury.source]} le {formatShortDate(injury.occurred_on)} · {injury.weeks_total} sem.
                      {injury.status === "active" && ` · retour le ${formatShortDate(injury.return_date)}`}
                      {injury.status === "fragile" && ` · fragile, rechute ${formatPercent(injury.relapse_risk)} par match`}
                      {injury.relapse && " · rechute"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="big-num">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}

function Fact({ label, value }) {
  return (
    <div className="stat">
      <span className="eyebrow">{label}</span>
      <span className="num" style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}
