import { useCallback, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import InjuryIcon from "../components/InjuryIcon.jsx";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import WindowBoard from "../components/WindowBoard.jsx";
import { POSITION_ORDER, POSITIONS, formatLongDate, formatNote, formatShortDate } from "../format.js";
import { useApi } from "../hooks/useApi.js";

// Le calendrier international de la saison : une fenêtre à la fois (ses matchs, son
// classement s'il y en a un), et la liste de 42 de chacune de ses sélections. Dans une
// carrière de club, nos joueurs retenus sont mis en avant ; dans celle d'un sélectionneur,
// sa sélection.
export default function Internationals() {
  const { career } = useOutletContext();
  const selector = career.kind === "nation";
  const calendar = useApi(useCallback(api.getInternationals, []));
  const [code, setCode] = useState(null);

  if (calendar.loading) return <p className="status">Chargement…</p>;
  if (calendar.error) return <p className="status status--error">{calendar.error.message}</p>;

  const { windows, my_players: mine, year } = calendar.data;
  const shown = windows.find((w) => w.code === code) ?? windows.find((w) => !w.finished) ?? windows.at(-1);

  if (!shown) {
    return (
      <>
        <header className="page-head">
          <h1 className="title">Sélections</h1>
        </header>
        <div className="card card--padded">
          <p className="eyebrow">Aucune fenêtre internationale</p>
          <p style={{ margin: "8px 0 0" }}>
            Ce monde n'a pas de sélections nationales, ou toutes leurs fenêtres étaient déjà commencées quand
            elles sont arrivées dans cette partie : elles reviendront la saison prochaine.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">{selector ? "Calendrier international" : "Sélections"}</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Saison {year} · {shown.name}, du {formatShortDate(shown.dates[0])} au {formatShortDate(shown.dates.at(-1))} ·{" "}
            {shown.announced
              ? "listes annoncées"
              : `listes annoncées le ${formatLongDate(shown.announce_by)} au plus tard`}
            {!selector && mine.length > 0 && ` · ${mine.length} de tes joueurs retenus`}
          </p>
        </div>
        <div className="chips" role="group" aria-label="Fenêtre internationale">
          {windows.map((w) => (
            <button key={w.code} type="button" className="chip" aria-pressed={w.code === shown.code} onClick={() => setCode(w.code)}>
              {w.short_name}
            </button>
          ))}
        </div>
      </header>

      <div className="two-col fill">
        <WindowBoard key={shown.code} windows={[shown]} myId={selector ? career.club_id : null} />
        <Squads
          key={`squads-${shown.code}`}
          window={shown}
          initial={selector ? career.nation : mine[0]?.nation.code}
          myClubId={selector ? null : career.club_id}
        />
      </div>
    </>
  );
}

// Les listes de la fenêtre : une sélection à la fois, ses 42 joueurs rangés par poste.
function Squads({ window, initial, myClubId }) {
  const navigate = useNavigate();
  const nations = window.nations;
  const [nationCode, setNationCode] = useState(nations.some((n) => n.code === initial) ? initial : nations[0].code);
  const squad = useApi(useCallback(() => api.getNationSquad(window.code, nationCode), [window.code, nationCode]));
  const nation = nations.find((n) => n.code === nationCode);
  const players = [...(squad.data?.players ?? [])].sort(
    (a, b) =>
      POSITION_ORDER.indexOf(a.player.position) - POSITION_ORDER.indexOf(b.player.position) ||
      b.position_rating - a.position_rating,
  );

  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow with-crest">
          <ClubCrest name={nation.name} size={18} />
          Liste · {nation.name}
        </h2>
        <select
          className="input tactics__select"
          aria-label="Sélection"
          value={nationCode}
          onChange={(event) => setNationCode(event.target.value)}
        >
          {nations.map((n) => (
            <option key={n.code} value={n.code}>
              {n.name}
            </option>
          ))}
        </select>
      </div>
      <div className="card table-wrap">
        {squad.loading && <p className="table__note">Chargement…</p>}
        {squad.error && <p className="table__note">{squad.error.message}</p>}
        {squad.data && squad.data.announced_on === null && (
          <p className="table__note">
            Liste pas encore annoncée : elle le sera le {formatLongDate(window.announce_by)} au plus tard, deux
            semaines avant le premier match.
          </p>
        )}
        {players.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th scope="col" className="left">Joueur</th>
                <th scope="col" className="left">Poste</th>
                <th scope="col">Âge</th>
                <th scope="col" className="left">Club</th>
                <th scope="col" title="Note à son poste">Au poste</th>
                <th scope="col" title="Titularisations cette saison, club et sélection">Tit.</th>
              </tr>
            </thead>
            <tbody>
              {players.map(({ player, club, position_rating: rating, starts }) => (
                <tr
                  key={player.id}
                  className={`table__row--clickable${club?.id === myClubId && myClubId !== null ? " table__row--ours" : ""}`}
                  tabIndex={0}
                  onClick={() => navigate(`/joueurs/${player.id}`)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") navigate(`/joueurs/${player.id}`);
                  }}
                >
                  <td className="left">
                    <div className="squad__name">
                      <PlayerAvatar src={player.photo} size={26} />
                      <InjuryIcon injury={player.injury} />
                      {player.name}
                    </div>
                  </td>
                  <td className="left">{POSITIONS[player.position].label}</td>
                  <td className="muted">{player.age}</td>
                  <td className="left">
                    {club ? (
                      <span className="with-crest">
                        <ClubCrest name={club.name} size={18} />
                        {club.name}
                      </span>
                    ) : (
                      <span className="muted">Hors championnats</span>
                    )}
                  </td>
                  <td className="note">{formatNote(rating)}</td>
                  <td className="muted">{starts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {squad.data?.announced_on && (
          <p className="table__note">
            Annoncée le {formatLongDate(squad.data.announced_on)}. Les jours où {nation.name} joue, ces joueurs
            manquent à leur club{myClubId !== null ? " ; les tiens sont en gras" : ""}.
          </p>
        )}
      </div>
    </section>
  );
}
