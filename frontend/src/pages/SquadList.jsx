import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import InjuryIcon from "../components/InjuryIcon.jsx";
import Modal from "../components/Modal.jsx";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import SortHeader from "../components/SortHeader.jsx";
import { ATTRIBUTES, POSITION_ORDER, POSITION_PLURALS, POSITIONS, formatLongDate, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";
import { chosenSlot } from "../save.js";

const AWAY_CLUB = "Hors championnats";

// La liste du sélectionneur : 42 joueurs à annoncer deux semaines avant le premier match
// d'une fenêtre internationale. Tant qu'elle n'est pas annoncée, on coche qui l'on veut
// parmi tous les joueurs sélectionnables (la proposition du staff sert de point de
// départ) ; une fois annoncée, elle ne bouge plus, sauf forfait d'un blessé.
export default function SquadList() {
  const { career } = useOutletContext();
  const navigate = useNavigate();
  const pool = useApi(useCallback(api.getSelectionPool, []));
  const confirm = useConfirm();
  const [picked, setPicked] = useState(null); // identifiants cochés (null : pas encore chargé)
  const [position, setPosition] = useState(null); // filtre par poste
  const [onlyPicked, setOnlyPicked] = useState(false);
  const [search, setSearch] = useState("");
  const [replacing, setReplacing] = useState(null); // le blessé de la liste que l'on remplace
  const [error, setError] = useState(null);

  const data = pool.data;
  const draftKey = data?.window ? `rugby.liste.${chosenSlot()}.${data.nation.code}.${data.window.code}` : null;

  // Point de départ : la liste annoncée, sinon le brouillon en cours, sinon celle du staff.
  useEffect(() => {
    if (!data) return;
    if (data.announced) {
      setPicked(new Set(data.selected));
      setOnlyPicked(true);
      return;
    }
    const known = new Set(data.players.map((entry) => entry.player.id));
    const draft = readDraft(draftKey)?.filter((id) => known.has(id));
    setPicked(new Set(draft ?? data.suggested));
  }, [data, draftKey]);

  const rows = useMemo(
    () =>
      (data?.players ?? []).map((entry) => ({
        ...entry.player,
        club_label: entry.club?.name ?? AWAY_CLUB,
        position_rating: entry.position_rating,
        starts: entry.starts,
        positionRank: POSITION_ORDER.indexOf(entry.player.position),
      })),
    [data],
  );
  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows.filter(
      (row) =>
        (position === null || row.position === position) &&
        (!onlyPicked || picked?.has(row.id)) &&
        (needle === "" || row.name.toLowerCase().includes(needle) || row.club_label.toLowerCase().includes(needle)),
    );
  }, [rows, position, onlyPicked, picked, search]);
  const table = useSort(shown, null);

  if (career.kind !== "nation") return <Navigate to="/" replace />;
  if (pool.loading && !data) return <p className="status">Chargement des joueurs sélectionnables…</p>;
  if (pool.error) return <p className="status status--error">{pool.error.message}</p>;
  if (picked === null) return <p className="status">Chargement…</p>;

  const locked = data.announced || data.window === null;
  const byPosition = Object.fromEntries(POSITION_ORDER.map((key) => [key, 0]));
  for (const row of rows) if (picked.has(row.id)) byPosition[row.position] += 1;
  const short = POSITION_ORDER.find((key) => byPosition[key] < data.minimum[key]);
  const problem =
    picked.size !== data.size
      ? picked.size < data.size
        ? `Il manque ${data.size - picked.size} joueur${data.size - picked.size > 1 ? "s" : ""}`
        : `${picked.size - data.size} joueur${picked.size - data.size > 1 ? "s" : ""} de trop`
      : short
        ? `Il faut au moins ${data.minimum[short]} ${POSITION_PLURALS[short]}`
        : null;

  const update = (next) => {
    setPicked(next);
    writeDraft(draftKey, [...next]);
  };
  const toggle = (row) => {
    if (locked) return;
    const next = new Set(picked);
    if (next.has(row.id)) next.delete(row.id);
    else next.add(row.id);
    update(next);
  };
  const open = (row) => navigate(`/joueurs/${row.id}`);

  const announce = () =>
    confirm.ask({
      eyebrow: data.window.name,
      title: "Annoncer la liste ?",
      text: `Les ${data.size} joueurs sont convoqués pour toute la fenêtre. La liste ne bouge plus ensuite, sauf pour remplacer un blessé.`,
      rows: POSITION_ORDER.map((key) => ({ label: POSITIONS[key].label, value: byPosition[key] })),
      confirmLabel: "Annoncer la liste",
      onConfirm: async () => {
        pool.setData(await api.announceList([...picked]));
        writeDraft(draftKey, null);
      },
    });

  // Ordre par défaut : par poste, les mieux notés à leur poste d'abord.
  const ordered = table.sort
    ? table.rows
    : [...table.rows].sort((a, b) => a.positionRank - b.positionRank || b.position_rating - a.position_rating);
  const header = (key, label, first = "desc", left = false, title) => (
    <SortHeader sortKey={key} label={label} sort={table.sort} onToggle={table.toggle} first={first} left={left} title={title} />
  );

  return (
    <>
      {confirm.dialog}
      <header className="squad__head">
        <div className="squad__stats">
          <h1 className="title">Liste des {data.size}</h1>
          <div className="stat">
            <span className={`big-num${picked.size === data.size ? "" : " big-num--accent"}`}>
              {picked.size} / {data.size}
            </span>
            <span className="muted">{data.announced ? "joueurs annoncés" : "joueurs cochés"}</span>
          </div>
          <div className="stat">
            <span className="big-num">{rows.length}</span>
            <span className="muted">sélectionnables</span>
          </div>
        </div>
        <div className="squad__compo">
          {data.window === null ? (
            <p className="muted">Plus de rendez-vous cette saison : la prochaine liste attendra.</p>
          ) : data.announced ? (
            <p className="muted">
              {data.window.name} · liste annoncée. Un blessé peut être remplacé (« Forfait »).
            </p>
          ) : (
            <>
              <p className="muted">
                {data.window.name} · à annoncer avant le {formatLongDate(data.window.announce_by)}
                {problem ? ` · ${problem}` : ""}
              </p>
              <button type="button" className="button button--small" onClick={() => update(new Set(data.suggested))}>
                Proposition du staff
              </button>
              <button type="button" className="button button--small" onClick={() => update(new Set())}>
                Tout retirer
              </button>
              <button type="button" className="button button--primary" disabled={problem !== null} onClick={announce}>
                Annoncer la liste
              </button>
            </>
          )}
        </div>
      </header>

      <div className="list-filters">
        <div className="chips chips--scroll" role="group" aria-label="Poste">
          <button type="button" className="chip" aria-pressed={position === null} onClick={() => setPosition(null)}>
            Tous
          </button>
          {POSITION_ORDER.map((key) => (
            <button
              key={key}
              type="button"
              className="chip"
              aria-pressed={position === key}
              title={`${byPosition[key]} dans la liste · le staff en prend ${data.quota[key]}, il en faut au moins ${data.minimum[key]}`}
              onClick={() => setPosition(position === key ? null : key)}
            >
              {POSITIONS[key].label}{" "}
              <span className={`chip__count${byPosition[key] < data.minimum[key] ? " chip__count--short" : ""}`}>
                {byPosition[key]}/{data.quota[key]}
              </span>
            </button>
          ))}
        </div>
        <div className="list-filters__side">
          <button type="button" className="chip" aria-pressed={onlyPicked} onClick={() => setOnlyPicked(!onlyPicked)}>
            Dans la liste
          </button>
          <input
            className="input list-filters__search"
            type="search"
            placeholder="Joueur ou club"
            aria-label="Chercher un joueur ou un club"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </div>

      {error && <p className="status--error">{error.message}</p>}

      <div className="card table-wrap squad__table fill">
        <table className="table">
          <thead>
            <tr>
              {header("picked", "", "desc", true, "Dans la liste")}
              {header("name", "Joueur", "asc", true)}
              {header("positionRank", "Poste", "asc", true)}
              {header("age", "Âge", "asc")}
              {header("club_label", "Club", "asc", true)}
              {header("overall", "Note")}
              {header("position_rating", "Au poste", "desc", false, "Note à son poste, le critère du staff")}
              {header("starts", "Tit.", "desc", false, "Titularisations cette saison, club et sélection")}
              {ATTRIBUTES.map((attr) => (
                <SortHeader
                  key={attr.key}
                  sortKey={attr.key}
                  label={attr.short}
                  title={attr.label}
                  sort={table.sort}
                  onToggle={table.toggle}
                  first="desc"
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {(table.sort?.key === "picked" ? sortByPicked(shown, picked, table.sort.dir) : ordered).map((row) => {
              const inList = picked.has(row.id);
              const injured = row.injury?.status === "active";
              return (
                <tr
                  key={row.id}
                  className={`${locked ? "" : "table__row--clickable"}${inList ? "" : " table__row--bench"}`}
                  onClick={() => toggle(row)}
                >
                  <td className="left">
                    <input
                      type="checkbox"
                      className="list-check"
                      checked={inList}
                      disabled={locked}
                      aria-label={`${row.name} dans la liste`}
                      onChange={() => toggle(row)}
                      onClick={(event) => event.stopPropagation()}
                    />
                  </td>
                  <td className="left">
                    <div className="squad__name">
                      <PlayerAvatar src={row.photo} size={26} />
                      <InjuryIcon injury={row.injury} />
                      <button
                        type="button"
                        className="link-button"
                        title="Voir sa fiche"
                        onClick={(event) => {
                          event.stopPropagation();
                          open(row);
                        }}
                      >
                        {row.name}
                      </button>
                      {data.announced && inList && injured && (
                        <button
                          type="button"
                          className="button button--small list-forfeit"
                          onClick={(event) => {
                            event.stopPropagation();
                            setReplacing(row);
                          }}
                        >
                          Forfait
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="left">{POSITIONS[row.position].label}</td>
                  <td className="muted">{row.age}</td>
                  <td className="left">
                    {row.club_name ? (
                      <span className="with-crest">
                        <ClubCrest name={row.club_name} size={18} />
                        {row.club_name}
                      </span>
                    ) : (
                      <span className="muted">{AWAY_CLUB}</span>
                    )}
                  </td>
                  <td className="note">{formatNote(row.overall)}</td>
                  <td className="note">{formatNote(row.position_rating)}</td>
                  <td className="muted">{row.starts}</td>
                  {ATTRIBUTES.map((attr) => {
                    const value = row[attr.key];
                    const tone = value >= 15 ? "cell--strong" : value <= 8 ? "cell--weak" : "";
                    return (
                      <td key={attr.key} className={tone}>
                        {value}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
        {shown.length === 0 && <p className="table__note">Aucun joueur ne correspond.</p>}
        <p className="table__note">
          Sous chaque poste : joueurs cochés / nombre que retient le staff. « Au poste » : la note du joueur à son
          poste. « Tit. » : ses titularisations de la saison, en club et en sélection. Les jours où la sélection joue,
          les joueurs de la liste manquent à leur club.
        </p>
      </div>

      {replacing && (
        <Replacement
          out={replacing}
          candidates={rows.filter((row) => !picked.has(row.id) && row.injury?.status !== "active")}
          onPick={async (candidate) => {
            setError(null);
            pool.setData(await api.replaceInList(replacing.id, candidate.id));
          }}
          onClose={() => setReplacing(null)}
        />
      )}
    </>
  );
}

// Forfait : qui remplace le blessé ? Les joueurs de son poste d'abord, les mieux notés en tête.
function Replacement({ out, candidates, onPick, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const sorted = [...candidates].sort((a, b) => b.position_rating - a.position_rating);
  const groups = [
    { label: "Au poste", players: sorted.filter((p) => p.position === out.position).slice(0, 15) },
    { label: "Autres postes", players: sorted.filter((p) => p.position !== out.position).slice(0, 15) },
  ];

  async function pick(candidate) {
    setBusy(true);
    setError(null);
    try {
      await onPick(candidate);
      onClose();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal compact className="lineup-picker" onClose={busy ? () => {} : onClose}>
      <div className="lineup-picker__head">
        <div>
          <p className="eyebrow">Forfait · {POSITIONS[out.position].label}</p>
          <h2 className="confirm__title">{out.name}</h2>
          <p className="muted lineup-picker__meta">Blessé : qui prend sa place dans la liste ?</p>
        </div>
      </div>
      {error && <p className="status--error lineup-picker__hint">{error.message}</p>}
      <div className="lineup-picker__list">
        {groups.map(
          (group) =>
            group.players.length > 0 && (
              <section key={group.label} className="lineup-picker__group">
                <h3 className="eyebrow">{group.label}</h3>
                {group.players.map((candidate) => (
                  <button key={candidate.id} type="button" className="lineup-picker__option" disabled={busy} onClick={() => pick(candidate)}>
                    <span className="lineup-picker__jersey" />
                    <span className="squad__name">{candidate.name}</span>
                    <span className="muted">{POSITIONS[candidate.position].label}</span>
                    <span className="muted">{candidate.club_label}</span>
                    <span className="note">{formatNote(candidate.position_rating)}</span>
                  </button>
                ))}
              </section>
            ),
        )}
      </div>
    </Modal>
  );
}

// Les joueurs cochés d'abord (ou en dernier), puis par poste et par note.
function sortByPicked(rows, picked, dir) {
  const sign = dir === "desc" ? -1 : 1;
  return [...rows].sort(
    (a, b) =>
      sign * (picked.has(a.id) - picked.has(b.id)) ||
      a.positionRank - b.positionRank ||
      b.position_rating - a.position_rating,
  );
}

// Brouillon de la liste, gardé le temps de la session (on peut aller voir une fiche et revenir).
function readDraft(key) {
  try {
    const raw = key && sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeDraft(key, ids) {
  try {
    if (!key) return;
    if (ids === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify(ids));
  } catch {
    // Stockage indisponible : le brouillon ne survivra pas à un changement de page.
  }
}
