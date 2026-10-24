import { useCallback, useRef, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import InjuryIcon from "../components/InjuryIcon.jsx";
import LineupPicker from "../components/LineupPicker.jsx";
import Pitch from "../components/Pitch.jsx";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import SortHeader from "../components/SortHeader.jsx";
import {
  ATTRIBUTES,
  POSITION_ORDER,
  POSITIONS,
  formatContractEnd,
  formatGain,
  formatMoney,
  formatNote,
  formatPotential,
  formatSuspension,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { usePitchWidth } from "../hooks/usePitchWidth.js";
import { useSort } from "../hooks/useSort.js";
import { buildLineup, lineupChoice } from "../lineup.js";

// L'effectif du club et son XV de départ. Pour un sélectionneur, la même page montre son
// groupe (sa liste de 42, ou celle que propose le staff tant qu'elle n'est pas annoncée).
// Dans un club, les joueurs retenus par une sélection qui joue le jour du prochain match
// sont marqués « En sélection » et sortent du XV ; des espoirs montent à leur place.
export default function Squad() {
  const { career } = useOutletContext();
  const navigate = useNavigate();
  const national = career.kind === "nation";
  const load = useCallback(
    () => (national ? api.getSelectionTeam() : api.getClub(career.club_id)),
    [national, career.club_id],
  );
  const { data: club, error, loading, setData } = useApi(load);
  // Sans tri choisi (null), l'ordre reste celui du staff : titulaires du 1 au 15, puis les autres.
  const squadSort = useSort(club ? squadRows(club) : [], null);
  const pitchRef = useRef(null);
  const pitchWidth = usePitchWidth(pitchRef, Boolean(club));
  // Place du terrain touchée : on choisit qui la prend.
  const [picking, setPicking] = useState(null);
  const [resetting, setResetting] = useState(false);
  const [captainError, setCaptainError] = useState(null);

  if (loading) return <p className="status">Chargement de l'effectif…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const lineup = buildLineup(club.players, club.strength.lineup_ids);
  const starters = lineup.map(({ player }) => player);
  const average = (values) => values.reduce((sum, v) => sum + v, 0) / values.length;
  const rows = squadSort.sort ? squadSort.rows : sortSquad(squadRows(club));
  const header = (key, label, first = "desc", left = false, title) => (
    <SortHeader sortKey={key} label={label} sort={squadSort.sort} onToggle={squadSort.toggle} first={first} left={left} title={title} />
  );
  const open = (player) => navigate(`/joueurs/${player.id}`);
  const jerseys = new Map(lineup.map(({ slot, player }) => [player.id, slot.number]));
  // Doublon : nos joueurs retenus par une sélection qui joue le jour de notre prochain match.
  const away = club.players.filter((player) => player.duty?.away);

  // Le joueur choisi prend la place ; s'il était titulaire, il échange avec l'ancien.
  async function replace({ slot, player }, candidate) {
    const place = lineup.findIndex((entry) => entry.slot.number === slot.number);
    const from = lineup.findIndex((entry) => entry.player.id === candidate.id);
    const next = lineup.map((entry, index) => {
      if (index === place) return { ...entry, player: candidate };
      if (index === from) return { ...entry, player };
      return entry;
    });
    const choice = lineupChoice(next);
    setData(await (national ? api.setSelectionLineup(choice) : api.setLineup(club.id, choice)));
  }

  // Capitaine : un pro de l'effectif, ou "" pour laisser le staff désigner le meneur du XV.
  async function chooseCaptain(value) {
    setCaptainError(null);
    try {
      setData(await api.setCaptain(club.id, value === "" ? null : Number(value)));
    } catch (err) {
      setCaptainError(err);
    }
  }

  async function resetLineup() {
    setResetting(true);
    try {
      setData(await (national ? api.resetSelectionLineup() : api.resetLineup(club.id)));
    } finally {
      setResetting(false);
    }
  }

  return (
    <>
      <header className="squad__head">
        <div className="squad__stats">
          <h1 className="title">{national ? "Composition" : "Effectif"}</h1>
          <Stat value={club.players.length} label={national ? "joueurs dans le groupe" : "joueurs"} />
          <Stat value={formatNote(average(starters.map((p) => p.overall)))} label="note moyenne du XV" />
          <Stat value={formatNote(average(starters.map((p) => p.age)))} label="âge moyen du XV" />
        </div>
        <div className="squad__compo">
          <p className="muted">
            {club.lineup_custom ? "Ta composition" : "Composition choisie par le staff"} · touche un joueur du
            terrain pour le remplacer, une ligne du tableau pour sa fiche
            {away.length > 0 && ` · doublon : ${away.length} joueur${away.length > 1 ? "s" : ""} en sélection au prochain match`}
            {club.strength.jiff_min > 0 && (
              <span className={club.strength.jiff < club.strength.jiff_min ? "status--error" : undefined}>
                {` · JIFF sur la feuille de match : ${club.strength.jiff} / 23 (minimum ${club.strength.jiff_min})`}
              </span>
            )}
          </p>
          {club.lineup_custom && (
            <button type="button" className="button button--small" disabled={resetting} onClick={resetLineup}>
              Rendre la main au staff
            </button>
          )}
          {!national && <CaptainPicker club={club} starters={starters} onChoose={chooseCaptain} />}
          {captainError && <span className="status--error">{captainError.message}</span>}
        </div>
      </header>

      <div className="squad__body fill">
        <figure
          ref={pitchRef}
          className="squad__pitch"
          style={pitchWidth ? { width: pitchWidth, flexBasis: pitchWidth } : undefined}
          aria-label="XV de départ sur le terrain"
        >
          <Pitch
            markers={lineup.map(({ slot, player }) => ({
              key: slot.number,
              x: slot.x,
              y: slot.y,
              number: slot.number,
              label: player.id === club.strength.captain_id ? `${player.last_name} (C)` : player.last_name,
              title: `${player.name} · ${POSITIONS[player.position].label}${player.id === club.strength.captain_id ? " · capitaine" : ""}`,
              entry: { slot, player },
            }))}
            onPick={(marker) => setPicking(marker.entry)}
          />
          <figcaption className="muted">Sens de l'attaque vers le haut. Avants en haut, arrières en bas.</figcaption>
        </figure>

        <div className="card table-wrap squad__table">
          <table className="table">
            <thead>
              <tr>
                {header("jersey", "N°", "asc", true)}
                {header("name", "Joueur", "asc", true)}
                {header("positionRank", "Poste", "asc", true)}
                {header("age", "Âge", "asc")}
                {header("overall", "Note")}
                {header("potential_high", "Pot.", "desc", false, "Potentiel estimé")}
                {header("season_gain", "Prog.", "desc", false, "Points d'attributs gagnés cette saison")}
                {national && header("club_name", "Club", "asc", true)}
                {!national && header("value", "Valeur")}
                {!national && header("wage", "Salaire")}
                {!national && header("contract_until", "Contrat", "asc", false, "Fin du contrat")}
                {ATTRIBUTES.map((attr) => (
                  <SortHeader
                    key={attr.key}
                    sortKey={attr.key}
                    label={attr.short}
                    title={attr.label}
                    sort={squadSort.sort}
                    onToggle={squadSort.toggle}
                    first="desc"
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((player) => (
                <tr
                  key={player.id}
                  className={`table__row--clickable${player.jersey === null ? " table__row--bench" : ""}`}
                  tabIndex={0}
                  onClick={() => open(player)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      open(player);
                    }
                  }}
                >
                  <td className="left jersey">{player.jersey ?? ""}</td>
                  <td className="left">
                    <div className="squad__name">
                      <PlayerAvatar src={player.photo} size={26} />
                      <InjuryIcon injury={player.injury} />
                      {player.name}
                      {club.strength.jiff_min > 0 && !player.jiff && (
                        <span className="tag tag--light" title="Pas issu des filières de formation françaises : il ne compte pas parmi les JIFF de la feuille de match">
                          Non JIFF
                        </span>
                      )}
                      {player.id === club.strength.captain_id && (
                        <span className="captain-badge" title="Capitaine">
                          C
                        </span>
                      )}
                      <DutyTag player={player} />
                      {player.suspended_matches > 0 && (
                        <span className="tag tag--injured" title="Suspendu par la commission de discipline : il ne peut pas jouer">
                          {formatSuspension(player.suspended_matches)}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="left">{POSITIONS[player.position].label}</td>
                  <td className="muted">{player.age}</td>
                  <td className="note">{formatNote(player.overall)}</td>
                  <td>{formatPotential(player)}</td>
                  <td className="muted">{formatGain(player.season_gain)}</td>
                  {national ? (
                    <td className="left">
                      {player.club_name ? (
                        <span className="with-crest">
                          <ClubCrest name={player.club_name} size={18} />
                          {player.club_name}
                        </span>
                      ) : (
                        <span className="muted">Hors championnats</span>
                      )}
                    </td>
                  ) : (
                    <>
                      <td>{formatMoney(player.value)}</td>
                      <td className="muted">{formatMoney(player.wage)}</td>
                      <td className="muted">
                        {player.loaned_from ? `Prêt · ${player.loaned_from_name}` : formatContractEnd(player.contract_until)}
                      </td>
                    </>
                  )}
                  {ATTRIBUTES.map((attr) => {
                    const value = player[attr.key];
                    const tone = value >= 15 ? "cell--strong" : value <= 8 ? "cell--weak" : "";
                    return (
                      <td key={attr.key} className={tone}>
                        {value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="table__note">
            {ATTRIBUTES.map((attr) => `${attr.short} ${attr.label.toLowerCase()}`).join(" · ")}.
            Attributs sur 20 ; en gras à partir de 15. Le numéro indique les titulaires. Pot. :
            potentiel estimé par le staff (la note qu'il peut atteindre) ; Prog. : points
            d'attributs gagnés cette saison, match après match.{" "}
            {national
              ? "Le groupe est ta liste ; tant qu'elle n'est pas annoncée, celle que propose le staff. Les blessés ne sont pas alignés."
              : "Salaire par saison, contrat jusqu'en juin de l'année indiquée. Les blessés et les suspendus ne sont pas alignés : voir la page Médical. « En sélection » : retenu par sa sélection, qui joue le jour de notre prochain match (doublon) ; des espoirs complètent alors la feuille de match. C : le capitaine, qui calme les esprits tant qu'il est sur le terrain."}
          </p>
        </div>
      </div>

      {picking && (
        <LineupPicker
          entry={picking}
          players={club.players.filter((player) => !player.duty?.away && !player.suspended_matches)}
          jerseys={jerseys}
          onPick={(candidate) => replace(picking, candidate)}
          onOpen={open}
          onClose={() => setPicking(null)}
        />
      )}
    </>
  );
}

// Lignes du tableau : le joueur, son numéro de titulaire (null sinon) et le rang de son poste.
function squadRows(club) {
  const jerseys = new Map(
    buildLineup(club.players, club.strength.lineup_ids).map(({ slot, player }) => [player.id, slot.number]),
  );
  return club.players.map((player) => ({
    ...player,
    jersey: jerseys.get(player.id) ?? null,
    positionRank: POSITION_ORDER.indexOf(player.position),
  }));
}

// Titulaires du 1 au 15, puis les remplaçants par poste et note décroissante.
function sortSquad(rows) {
  return [...rows].sort((a, b) => {
    if (a.jersey !== null || b.jersey !== null) {
      if (a.jersey === null) return 1;
      if (b.jersey === null) return -1;
      return a.jersey - b.jersey;
    }
    if (a.positionRank !== b.positionRank) return a.positionRank - b.positionRank;
    return b.overall - a.overall;
  });
}

// À côté du nom : retenu en sélection (absent du prochain match, ou seulement dans la
// liste), ou espoir monté le temps d'un doublon.
function DutyTag({ player }) {
  const { duty } = player;
  if (duty?.away) {
    return (
      <span className="tag tag--fragile" title={`${duty.competition} · ${duty.nation.name} joue le jour de notre prochain match`}>
        En sélection
      </span>
    );
  }
  if (duty) {
    return (
      <span className="tag tag--light" title={`Dans la liste de ${duty.nation.name} · ${duty.competition}`}>
        {duty.nation.code}
      </span>
    );
  }
  if (player.squad === "youth") {
    return (
      <span className="tag tag--light" title="Espoir appelé pour suppléer un international">
        Espoir
      </span>
    );
  }
  return null;
}

// Le capitaine : celui du manager, ou « Choix du staff », qui donne le brassard au plus
// grand meneur du XV (expérience et niveau, sur 20 à côté de chaque nom).
function CaptainPicker({ club, starters, onChoose }) {
  const staffPick = starters.reduce((best, p) => (best === null || p.leadership > best.leadership ? p : best), null);
  const options = [...club.players].filter((p) => p.squad !== "youth").sort((a, b) => b.leadership - a.leadership);
  return (
    <label className="captain-picker">
      <span className="muted">Capitaine</span>
      <select className="input tactics__select" value={club.captain_choice ?? ""} onChange={(event) => onChoose(event.target.value)}>
        <option value="">Choix du staff{staffPick ? ` · ${staffPick.name}` : ""}</option>
        {options.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} · meneur {formatNote(p.leadership)}
          </option>
        ))}
      </select>
    </label>
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
