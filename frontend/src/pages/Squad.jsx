import { Fragment, useCallback, useRef, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import InjuryIcon from "../components/InjuryIcon.jsx";
import { LineupLegend, LineupPitch, StrengthStrip, canDrag, useLineupEditor } from "../components/LineupBoard.jsx";
import LineupPicker from "../components/LineupPicker.jsx";
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
import { matchSheet } from "../lineup.js";

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

  if (loading) return <p className="status">Chargement de l'effectif…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  return <SquadView club={club} national={national} setData={setData} squadSort={squadSort} navigate={navigate} />;
}

// La page une fois l'effectif chargé (l'édition de la composition a ses propres hooks).
function SquadView({ club, national, setData, squadSort, navigate }) {
  const pitchRef = useRef(null);
  const pitchWidth = usePitchWidth(pitchRef);
  const [captainError, setCaptainError] = useState(null);
  const editor = useLineupEditor({
    team: club,
    save: (choice) => (national ? api.setSelectionLineup(choice) : api.setLineup(club.id, choice)),
    reset: () => (national ? api.resetSelectionLineup() : api.resetLineup(club.id)),
    onSaved: setData,
  });
  const { lineup } = editor;
  const starters = lineup.map(({ player }) => player);
  const sheet = matchSheet(club);
  const average = (values) => values.reduce((sum, v) => sum + v, 0) / values.length;
  const rows = squadSort.sort ? squadSort.rows : sortSquad(squadRows(club));
  const header = (key, label, first = "desc", left = false, title) => (
    <SortHeader sortKey={key} label={label} sort={squadSort.sort} onToggle={squadSort.toggle} first={first} left={left} title={title} />
  );
  const open = (player) => {
    if (!editor.drag.swallowed()) navigate(`/joueurs/${player.id}`);
  };
  // Doublon : nos joueurs retenus par une sélection qui joue le jour de notre prochain match.
  const away = club.players.filter((player) => player.duty?.away);
  const { jiff, jiff_min: jiffMin } = club.strength;
  // Sans tri choisi : titulaires, remplaçants, puis le reste, chacun sous son intertitre.
  const grouped = !squadSort.sort;
  const columns = 7 + (national ? 1 : 3) + ATTRIBUTES.length;

  // Capitaine : un pro de l'effectif, ou "" pour laisser le staff désigner le meneur du XV.
  async function chooseCaptain(value) {
    setCaptainError(null);
    try {
      setData(await api.setCaptain(club.id, value === "" ? null : Number(value)));
    } catch (err) {
      setCaptainError(err);
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
        {!national && (
          <div className="squad__compo">
            <CaptainPicker club={club} starters={starters} onChoose={chooseCaptain} />
            {captainError && <span className="status--error">{captainError.message}</span>}
          </div>
        )}
      </header>

      <div className="squad__body fill">
        <figure
          ref={pitchRef}
          className="squad__pitch"
          style={pitchWidth ? { width: pitchWidth, flexBasis: pitchWidth } : undefined}
          aria-label="XV de départ sur le terrain"
        >
          <LineupPitch editor={editor} captainId={club.strength.captain_id} />
          <LineupLegend />
        </figure>

        <div className="squad__side">
          <StrengthStrip editor={editor}>
            {jiffMin > 0 && (
              <span
                className={`compo-fact${jiff < jiffMin ? " compo-fact--alert" : ""}`}
                title="Joueurs issus des filières de formation françaises sur les 23 de la feuille de match"
              >
                <strong>{jiff}/23</strong> JIFF · min. {jiffMin}
              </span>
            )}
            {away.length > 0 && (
              <span className="compo-fact" title="Retenus par leur sélection, qui joue le jour de notre prochain match">
                <strong>{away.length}</strong> en sélection
              </span>
            )}
          </StrengthStrip>
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
                {rows.map((player, index) => (
                  <Fragment key={player.id}>
                    {grouped && player.group !== rows[index - 1]?.group && (
                      <tr className="table__group">
                        <td colSpan={columns}>{GROUP_LABELS[player.group]}</td>
                      </tr>
                    )}
                    <tr
                      className={[
                        "table__row--clickable",
                        !player.starter && "table__row--bench",
                        canDrag(player) && "table__row--draggable",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      tabIndex={0}
                      title={canDrag(player) ? "Clic : sa fiche · glisser sur le terrain : l'aligner" : undefined}
                      onPointerDown={(event) => {
                        // À la souris seulement : au doigt, la liste doit pouvoir défiler.
                        if (event.pointerType !== "mouse" || !canDrag(player)) return;
                        event.preventDefault();
                        editor.drag.begin(event, { player, from: player.starter ? player.jersey : null });
                      }}
                      onClick={() => open(player)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          open(player);
                        }
                      }}
                    >
                      <td className={`left jersey${player.starter ? "" : " jersey--bench"}`}>{player.jersey ?? ""}</td>
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
                  </Fragment>
                ))}
              </tbody>
            </table>
            <p className="table__note">
              {ATTRIBUTES.map((attr) => `${attr.short} ${attr.label.toLowerCase()}`).join(" · ")}.
              Attributs sur 20 ; en gras à partir de 15. N° : 1 à 15 le XV, 16 à 23 les remplaçants (choisis par le staff). Pot. :
              potentiel estimé par le staff (la note qu'il peut atteindre) ; Prog. : points
              d'attributs gagnés cette saison, match après match.{" "}
              {national
                ? "Le groupe est ta liste ; tant qu'elle n'est pas annoncée, celle que propose le staff. Les blessés ne sont pas alignés."
                : "Salaire par saison, contrat jusqu'en juin de l'année indiquée. Les blessés et les suspendus ne sont pas alignés : voir la page Médical. « En sélection » : retenu par sa sélection, qui joue le jour de notre prochain match (doublon) ; des espoirs complètent alors la feuille de match. C : le capitaine, qui calme les esprits tant qu'il est sur le terrain."}
            </p>
          </div>
        </div>
      </div>

      {editor.picking && (
        <LineupPicker
          entry={editor.picking}
          team={club}
          players={club.players}
          sheet={sheet}
          onPick={(candidate) => editor.place(editor.picking.slot.number, candidate)}
          onOpen={open}
          onClose={editor.closePicker}
        />
      )}
    </>
  );
}

// Lignes du tableau : le joueur, son numéro sur la feuille de match (1-15 titulaires,
// 16-23 remplaçants, null sinon), son groupe et le rang de son poste.
function squadRows(club) {
  const sheet = matchSheet(club);
  return club.players.map((player) => {
    const jersey = sheet.get(player.id) ?? null;
    const starter = jersey !== null && jersey <= 15;
    return {
      ...player,
      jersey,
      starter,
      group: starter ? "starters" : jersey !== null ? "bench" : "others",
      positionRank: POSITION_ORDER.indexOf(player.position),
    };
  });
}

const GROUP_LABELS = {
  starters: "Le XV de départ",
  bench: "Les remplaçants · choisis par le staff",
  others: "Hors de la feuille de match",
};

// Titulaires du 1 au 15, remplaçants du 16 au 23, puis les autres par poste et note décroissante.
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
