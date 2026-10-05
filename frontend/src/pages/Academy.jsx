import { useCallback, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import Level from "../components/Level.jsx";
import MatchList from "../components/MatchList.jsx";
import SortHeader from "../components/SortHeader.jsx";
import { ATTRIBUTES, POSITIONS, formatContractEnd, formatLongDate, formatMoney, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";

// Centre de formation : les espoirs et leur championnat, promotions et rétrogradations.
export default function Academy() {
  const { career } = useOutletContext();
  const myId = career.club_id;
  const { data, error, loading, setData } = useApi(useCallback(api.getAcademy, []));
  const [view, setView] = useState("youths"); // youths | pros | calendar
  const youthSort = useSort(data?.youths ?? [], { key: "overall", dir: "desc" });
  const proSort = useSort(data?.eligible_pros ?? [], { key: "age", dir: "asc" });

  const confirm = useConfirm();

  function promote(player) {
    confirm.ask({
      eyebrow: "Centre de formation · Promotion",
      title: `Promouvoir ${player.name}`,
      text: `${POSITIONS[player.position].label}, ${player.age} ans, note ${formatNote(player.overall)}. Il quitte les espoirs pour l'effectif pro et signe un contrat de pro.`,
      rows: [
        { label: "Effectif pro", from: data.squad_size, to: data.squad_size + 1, hint: `${data.squad_max} au maximum` },
        { label: "Salaire", from: formatMoney(player.wage), to: "salaire de pro", hint: "fixé à la signature selon son niveau" },
        { label: "Fin de contrat", value: formatContractEnd(player.contract_until) },
      ],
      confirmLabel: "Promouvoir",
      onConfirm: async () => setData(await api.promoteYouth(player.id)),
    });
  }

  function demote(player) {
    confirm.ask({
      eyebrow: "Centre de formation · Rétrogradation",
      title: `Rétrograder ${player.name}`,
      text: `${POSITIONS[player.position].label}, ${player.age} ans, note ${formatNote(player.overall)}. Il redescend chez les espoirs pour y gagner du temps de jeu.`,
      rows: [
        { label: "Effectif pro", from: data.squad_size, to: data.squad_size - 1, hint: `${data.squad_min} au minimum` },
        { label: "Salaire", value: formatMoney(player.wage), hint: "inchangé" },
        { label: "Fin de contrat", value: formatContractEnd(player.contract_until) },
      ],
      confirmLabel: "Rétrograder",
      onConfirm: async () => setData(await api.demotePro(player.id)),
    });
  }

  if (loading && !data) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const squadFull = data.squad_size >= data.squad_max;
  const squadAtMinimum = data.squad_size <= data.squad_min;
  const starters = new Set(data.strength.lineup_ids);
  const average = (values) => (values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : 0);
  const leaving = data.youths.filter((y) => y.age >= data.youth_exit_age - 1).length;

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Formation</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Les espoirs jouent leur championnat les mêmes jours que les pros. Promeus-les quand ils sont
            prêts : à {data.youth_exit_age} ans, un espoir non promu quitte le centre. Un pro de{" "}
            {data.youth_max_age} ans ou moins peut redescendre.
          </p>
        </div>
        <div className="page-head__stats">
          <div className="stat">
            <Level value={data.academy_level} label={`centre niveau ${data.academy_level} sur 5`} />
            <span className="muted">
              centre niveau {data.academy_level} · <Link to="/infrastructures">améliorer</Link>
            </span>
          </div>
          <Stat value={data.youths.length} label="espoirs" />
          <Stat value={formatNote(average(data.youths.filter((y) => starters.has(y.id)).map((y) => y.overall)))} label="note du XV espoirs" />
          <Stat value={data.intake_per_year} label="jeunes par intersaison" />
        </div>
      </header>

      {confirm.dialog}

      <div className="chips" role="tablist" aria-label="Vue">
        {[
          ["youths", `Espoirs · ${data.youths.length}`],
          ["pros", `Pros rétrogradables · ${data.eligible_pros.length}`],
          ["calendar", "Championnat espoirs"],
        ].map(([key, label]) => (
          <button key={key} type="button" className="chip" role="tab" aria-pressed={view === key} onClick={() => setView(key)}>
            {label}
          </button>
        ))}
      </div>

      {view === "youths" && (
        <section className="section fill">
          <div className="section__head">
            <h2 className="eyebrow">Espoirs</h2>
            <span className="muted">
              {leaving > 0
                ? `${leaving} joueur${leaving > 1 ? "s" : ""} en dernière année au centre`
                : "Aucun joueur en dernière année au centre"}
              {" · "}effectif pro {data.squad_size}/{data.squad_max}
            </span>
          </div>
          <PlayerTable
            players={youthSort.rows}
            sort={youthSort}
            starters={starters}
            exitAge={data.youth_exit_age}
            action={(player) => (
              <button
                type="button"
                className="button button--small button--primary"
                disabled={squadFull}
                title={squadFull ? "Effectif pro complet" : undefined}
                onClick={() => promote(player)}
              >
                Promouvoir
              </button>
            )}
          />
        </section>
      )}

      {view === "pros" && (
        <section className="section fill">
          <div className="section__head">
            <h2 className="eyebrow">Pros de {data.youth_max_age} ans ou moins</h2>
            <span className="muted">Redescendre un jeune pro lui donne du temps de jeu chez les espoirs</span>
          </div>
          <PlayerTable
            players={proSort.rows}
            sort={proSort}
            starters={new Set()}
            action={(player) => (
              <button
                type="button"
                className="button button--small"
                disabled={squadAtMinimum}
                title={squadAtMinimum ? `Effectif pro minimum (${data.squad_min})` : undefined}
                onClick={() => demote(player)}
              >
                Rétrograder
              </button>
            )}
          />
        </section>
      )}

      {view === "calendar" && (
        <div className="club-grid fill">
          {data.last_matchday && (
            <section className="section">
              <div className="section__head">
                <h2 className="eyebrow">Dernière journée · J{data.last_matchday.matchday}</h2>
                <span className="muted">{formatLongDate(data.last_matchday.date)}</span>
              </div>
              <div className="card">
                <MatchList matches={data.last_matchday.matches} myClubId={myId} />
              </div>
            </section>
          )}
          {data.next_matchday && (
            <section className="section">
              <div className="section__head">
                <h2 className="eyebrow">Prochaine journée · J{data.next_matchday.matchday}</h2>
                <span className="muted">{formatLongDate(data.next_matchday.date)}</span>
              </div>
              <div className="card">
                <MatchList matches={data.next_matchday.matches} myClubId={myId} />
              </div>
            </section>
          )}
          <Standings standings={data.standings} myId={myId} />
        </div>
      )}
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

// Tableau d'espoirs ou de jeunes pros, avec un bouton d'action par ligne.
function PlayerTable({ players, sort, starters, exitAge, action }) {
  const header = (key, label, first = "desc", left = false, title) => (
    <SortHeader sortKey={key} label={label} sort={sort.sort} onToggle={sort.toggle} first={first} left={left} title={title} />
  );
  return (
    <div className="card table-wrap">
      <table className="table">
        <thead>
          <tr>
            {header("name", "Joueur", "asc", true)}
            {header("age", "Âge", "asc")}
            {header("overall", "Note")}
            {header("wage", "Salaire")}
            {header("contract_until", "Contrat", "asc")}
            {ATTRIBUTES.map((attr) => (
              <SortHeader key={attr.key} sortKey={attr.key} label={attr.short} title={attr.label} sort={sort.sort} onToggle={sort.toggle} first="desc" />
            ))}
            <th scope="col"></th>
          </tr>
        </thead>
        <tbody>
          {players.map((player) => (
            <tr key={player.id}>
              <td className="left">
                <div style={{ fontWeight: 600 }}>
                  {player.name}
                  {starters.has(player.id) && <span className="jersey"> · XV</span>}
                </div>
                <div className="muted">
                  {POSITIONS[player.position].label}
                  {exitAge && player.age >= exitAge - 1 && <span className="tag tag--fragile" style={{ marginLeft: 6 }}>Dernière année</span>}
                  {player.injury?.status === "active" && <span className="tag tag--injured" style={{ marginLeft: 6 }}>Blessé</span>}
                </div>
              </td>
              <td className="muted">{player.age}</td>
              <td className="note">{formatNote(player.overall)}</td>
              <td className="muted">{formatMoney(player.wage)}</td>
              <td className="muted">{formatContractEnd(player.contract_until)}</td>
              {ATTRIBUTES.map((attr) => {
                const value = player[attr.key];
                const tone = value >= 15 ? "cell--strong" : value <= 8 ? "cell--weak" : "";
                return (
                  <td key={attr.key} className={tone}>
                    {value}
                  </td>
                );
              })}
              <td>{action(player)}</td>
            </tr>
          ))}
          {players.length === 0 && (
            <tr>
              <td colSpan={6 + ATTRIBUTES.length} className="left muted">Personne.</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="table__note">
        « XV » : titulaire de l'équipe espoirs. Attributs sur 20 ; en gras à partir de 15. Les jeunes progressent à
        chaque intersaison, d'autant plus que le centre est bon.
      </p>
    </div>
  );
}

function Standings({ standings, myId }) {
  const { rows, sort, toggle } = useSort(standings, { key: "rank", dir: "asc" });
  const header = (key, label, first = "desc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={sort} onToggle={toggle} first={first} left={left} />
  );
  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Classement espoirs</h2>
        <span className="muted">Saison régulière, sans phases finales</span>
      </div>
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              {header("rank", "#", "asc", true)}
              {header("club_name", "Club", "asc", true)}
              {header("played", "J")}
              {header("won", "G")}
              {header("drawn", "N")}
              {header("lost", "P")}
              {header("points_difference", "Diff")}
              {header("league_points", "Pts")}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.club_id} className={row.club_id === myId ? "table__row--mine" : undefined}>
                <td className="left">{row.rank}</td>
                <td className="left">{row.club_name}</td>
                <td>{row.played}</td>
                <td>{row.won}</td>
                <td>{row.drawn}</td>
                <td>{row.lost}</td>
                <td>{row.points_difference > 0 ? `+${row.points_difference}` : row.points_difference}</td>
                <td style={{ fontWeight: 700 }}>{row.league_points}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
