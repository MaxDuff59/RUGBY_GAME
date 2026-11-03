import { useCallback, useEffect, useMemo, useState } from "react";

import { adminApi } from "../adminApi.js";
import { formatDayTime } from "../adminFormat.js";
import { POSITION_ORDER, POSITIONS } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import ClubCrest from "./ClubCrest.jsx";
import { useConfirm } from "./ConfirmDialog.jsx";
import PlayerAvatar from "./PlayerAvatar.jsx";

// Backoffice, onglet Sélections : la compo de chaque nation, son groupe et son XV, choisis
// parmi les pros des effectifs qui peuvent porter le maillot. Une compo peut rester partielle :
// le staff complète la liste de 42 et les places vides du XV ; le banc reste à lui.

// Au-delà, la liste demande d'affiner la recherche (plus de 700 Français).
const MAX_ROWS = 100;

const keyOf = (player) => `${player.club}\u0000${player.name}`;

// Le formulaire désigne les joueurs par leur clé ; l'API, le XV par leur rang dans le groupe.
function formOf(detail) {
  const squad = detail.squad.map(keyOf);
  return {
    squad,
    lineup: detail.slots.map((_, i) => (detail.lineup[i] == null ? null : squad[detail.lineup[i]])),
  };
}

function payload(form, players) {
  const lineup = form.lineup.map((key) => (key === null ? null : form.squad.indexOf(key)));
  return {
    squad: form.squad.map((key) => ({ club: players.get(key).club, name: players.get(key).name })),
    lineup: lineup.some((index) => index !== null) ? lineup : [],
  };
}

export default function AdminNations() {
  const nations = useApi(useCallback(adminApi.nations, []));
  const phone = useMediaQuery(PHONE_QUERY);
  const confirm = useConfirm();
  const [selected, setSelected] = useState(null);
  const [dirty, setDirty] = useState(false);

  // Changer de sélection avec des changements pas encore enregistrés : on demande d'abord.
  const choose = (code) => {
    if (!dirty || code === selected) return setSelected(code);
    confirm.ask({
      eyebrow: "Sélections",
      title: "Abandonner les changements",
      text: "Ce qui a été saisi n'est pas enregistré.",
      confirmLabel: "Abandonner",
      cautious: true,
      onConfirm: async () => {
        setDirty(false);
        setSelected(code);
      },
    });
  };

  if (nations.loading && !nations.data) return <p className="status">Chargement des sélections…</p>;
  if (nations.error) return <p className="status status--error">{nations.error.message}</p>;

  const list = (
    <section className="card admin__panel">
      <div className="admin__panel-head">
        <h2 className="eyebrow">Sélections</h2>
      </div>
      <div className="admin__scroll">
        <table className="table admin__table">
          <thead>
            <tr>
              <th className="left">Sélection</th>
              <th title="Joueurs du groupe, sur 42">Groupe</th>
              <th title="Places du XV choisies, sur 15">XV</th>
            </tr>
          </thead>
          <tbody>
            {nations.data.map((n) => (
              <tr key={n.code} className={`admin__row${selected === n.code ? " admin__row--on" : ""}`} onClick={() => choose(n.code)}>
                <td className="left">
                  {n.name}
                  {!n.edited && <span className="admin__tag">staff</span>}
                </td>
                <td>{n.edited ? n.listed : "—"}</td>
                <td>{n.edited ? n.starters : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );

  const editor = selected ? (
    <NationEditor
      key={selected}
      code={selected}
      onSaved={(detail) => nations.setData(nations.data.map((n) => (n.code === detail.code ? { ...n, ...summaryOf(detail) } : n)))}
      onDirty={setDirty}
      onBack={phone ? () => choose(null) : null}
    />
  ) : (
    <section className="card admin__panel admin__empty">
      <p className="muted">Choisis une sélection pour composer son groupe et son XV. Sans compo, son staff décide seul.</p>
    </section>
  );

  return (
    <div className="admin__split admin__split--nations">
      {confirm.dialog}
      {phone ? (selected ? editor : list) : (
        <>
          {list}
          {editor}
        </>
      )}
    </div>
  );
}

const summaryOf = ({ edited, listed, starters, updated_at, updated_by }) => ({ edited, listed, starters, updated_at, updated_by });

function NationEditor({ code, onSaved, onDirty, onBack }) {
  const nation = useApi(useCallback(() => adminApi.nation(code), [code]));
  const confirm = useConfirm();
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (nation.data && !form) setForm(formOf(nation.data));
  }, [nation.data, form]);
  const dirty = Boolean(form && nation.data) && JSON.stringify(form) !== JSON.stringify(formOf(nation.data));
  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);

  const players = useMemo(() => new Map((nation.data?.players ?? []).map((p) => [keyOf(p), p])), [nation.data]);

  if (nation.loading || (nation.data && !form)) return <section className="card admin__panel admin__empty"><p className="muted">Chargement…</p></section>;
  if (nation.error) return <section className="card admin__panel admin__empty"><p className="status--error">{nation.error.message}</p></section>;
  const n = nation.data;

  // Un joueur ajouté prend la première place libre du XV à son poste.
  function add(player) {
    const key = keyOf(player);
    setForm((f) => {
      const free = n.slots.findIndex((slot, i) => slot.position === player.position && f.lineup[i] === null);
      return { squad: [...f.squad, key], lineup: f.lineup.map((k, i) => (i === free ? key : k)) };
    });
  }
  const remove = (key) =>
    setForm((f) => ({ squad: f.squad.filter((k) => k !== key), lineup: f.lineup.map((k) => (k === key ? null : k)) }));
  // Un joueur déjà titulaire ailleurs quitte son ancienne place.
  const place = (index, key) =>
    setForm((f) => ({ ...f, lineup: f.lineup.map((k, i) => (i === index ? key : k === key ? null : k)) }));

  function applied(detail) {
    nation.setData(detail);
    setForm(formOf(detail));
    onSaved(detail);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      applied(await adminApi.saveNation(code, payload(form, players)));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const reset = () =>
    confirm.ask({
      eyebrow: n.name,
      title: "Rendre la sélection au staff",
      text: "La compo est effacée : le staff compose seul les prochaines listes.",
      confirmLabel: "Rendre au staff",
      cautious: true,
      onConfirm: async () => applied(await adminApi.resetNation(code)),
    });

  return (
    <section className="card admin__panel admin__detail">
      {confirm.dialog}
      <div className="admin__detail-head">
        {onBack && (
          <button type="button" className="admin__link" onClick={onBack}>
            ← Sélections
          </button>
        )}
        <div className="admin__club-head">
          <div>
            <p className="eyebrow">
              {form.squad.length}/{n.size} dans le groupe · {form.lineup.filter(Boolean).length}/{n.slots.length} dans le XV
            </p>
            <h2 className="admin__name">{n.name}</h2>
            {n.updated_at && (
              <p className="muted admin__hint">
                Modifiée le {formatDayTime(n.updated_at)} par {n.updated_by}
              </p>
            )}
          </div>
          {n.edited && (
            <button type="button" className="button admin__reset" onClick={reset}>
              Rendre au staff
            </button>
          )}
        </div>
        {n.missing.length > 0 && (
          <p className="admin__nation-gone">
            Plus dans les effectifs, sortis de la compo : {n.missing.join(", ")}.
          </p>
        )}
      </div>

      <div className="admin__nation">
        <div className="admin__scroll admin__nation-compo">
          <p className="muted admin__nation-note">
            Le staff complète la liste, les places vides du XV et le banc. Les parties s'en servent à la prochaine liste annoncée, jusqu'à leur première Coupe du monde.
            {n.home_only && " Sa fédération ne retient que les joueurs des clubs du pays."}
          </p>
          <Lineup slots={n.slots} form={form} players={players} onPlace={place} />
          <Squad nation={n} form={form} players={players} onRemove={remove} />
        </div>
        <Candidates nation={n} form={form} onAdd={add} />
      </div>

      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        <button type="button" className="button" disabled={busy || !dirty} onClick={() => setForm(formOf(n))}>
          Annuler
        </button>
        <button type="button" className="button button--primary" disabled={busy || !dirty} onClick={save}>
          {busy ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>
    </section>
  );
}

// Le XV, place par place : ceux du groupe à ce poste, puis les autres (hors poste, comme
// un manager peut le faire).
function Lineup({ slots, form, players, onPlace }) {
  const listed = form.squad.map((key) => [key, players.get(key)]);
  // Du 1 au 15 à l'écran ; `index` reste la place dans le XV (ordre du moteur).
  const places = slots.map((slot, index) => ({ ...slot, index })).sort((a, b) => a.number - b.number);
  return (
    <div className="admin__block">
      <h3 className="eyebrow">XV de départ</h3>
      <div className="admin__xv">
        {places.map(({ index, ...slot }) => {
          const here = listed.filter(([, p]) => p.position === slot.position);
          const others = listed.filter(([, p]) => p.position !== slot.position);
          return (
            <label key={slot.number} className="admin__xv-slot">
              <span className="admin__xv-number">{slot.number}</span>
              <select
                className="input admin__cell"
                aria-label={`Numéro ${slot.number}, ${POSITIONS[slot.position].label}`}
                value={form.lineup[index] ?? ""}
                onChange={(e) => onPlace(index, e.target.value || null)}
              >
                <option value="">{POSITIONS[slot.position].label} : au staff</option>
                {here.map(([key, p]) => (
                  <option key={key} value={key}>
                    {p.name}
                  </option>
                ))}
                {others.length > 0 && (
                  <optgroup label="Hors poste">
                    {others.map(([key, p]) => (
                      <option key={key} value={key}>
                        {p.name} ({POSITIONS[p.position].label})
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </label>
          );
        })}
      </div>
    </div>
  );
}

// Le groupe, poste par poste, avec ce que le staff prendrait à ce poste (son quota).
function Squad({ nation, form, players, onRemove }) {
  const jerseys = new Map(form.lineup.map((key, i) => [key, nation.slots[i].number]));
  return (
    <div className="admin__block">
      <h3 className="eyebrow">Groupe</h3>
      {form.squad.length === 0 && <p className="muted admin__note">Ajoute des joueurs depuis la liste : sans groupe, le staff compose seul.</p>}
      {POSITION_ORDER.map((position) => {
        const keys = form.squad.filter((key) => players.get(key).position === position);
        if (keys.length === 0) return null;
        return (
          <div key={position} className="admin__group">
            <h4 className="admin__group-title">
              {POSITIONS[position].label}
              <span className="admin__group-count muted">
                {keys.length} · le staff en prend {nation.quota[position]}, {nation.minimum[position]} au moins
              </span>
            </h4>
            <ul className="admin__nation-list">
              {keys.map((key) => {
                const p = players.get(key);
                return (
                  <li key={key} className="admin__nation-player">
                    <PlayerAvatar src={p.photo_url} size={28} />
                    <span className="admin__person">
                      <span className="admin__person-name">
                        {p.name}
                        {jerseys.has(key) && <span className="admin__tag">n° {jerseys.get(key)}</span>}
                      </span>
                      <span className="admin__person-meta">{p.club}</span>
                    </span>
                    <button type="button" className="admin__link" onClick={() => onRemove(key)} aria-label={`Retirer ${p.name}`}>
                      Retirer
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

// Ceux qui peuvent porter le maillot et ne sont pas encore du groupe, les internationaux d'abord.
function Candidates({ nation, form, onAdd }) {
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState("");
  const full = form.squad.length >= nation.size;

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const listed = new Set(form.squad);
    return nation.players.filter(
      (p) =>
        !listed.has(keyOf(p)) &&
        (!position || p.position === position) &&
        (!needle || p.name.toLowerCase().includes(needle) || p.club.toLowerCase().includes(needle)),
    );
  }, [nation.players, form.squad, query, position]);

  return (
    <div className="admin__nation-pool">
      <div className="admin__tools">
        <input className="input" type="search" placeholder="Rechercher un joueur ou un club" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select className="input" value={position} onChange={(e) => setPosition(e.target.value)} aria-label="Poste">
          <option value="">Tous les postes</option>
          {POSITION_ORDER.map((p) => (
            <option key={p} value={p}>
              {POSITIONS[p].label}
            </option>
          ))}
        </select>
      </div>
      <div className="admin__scroll">
        <ul className="admin__nation-list">
          {shown.slice(0, MAX_ROWS).map((p) => (
            <li key={keyOf(p)} className="admin__nation-player">
              <PlayerAvatar src={p.photo_url} size={28} />
              <span className="admin__person">
                <span className="admin__person-name">
                  {p.name}
                  {p.international && <span className="admin__tag">int.</span>}
                </span>
                <span className="admin__person-meta">
                  {POSITIONS[p.position].label} · {p.club}
                </span>
              </span>
              <ClubCrest name={p.club} size={20} />
              <button type="button" className="button button--small" disabled={full} onClick={() => onAdd(p)} aria-label={`Ajouter ${p.name}`}>
                Ajouter
              </button>
            </li>
          ))}
        </ul>
        {shown.length === 0 && <p className="muted admin__more">Aucun joueur.</p>}
        {shown.length > MAX_ROWS && (
          <p className="muted admin__more">
            {shown.length - MAX_ROWS} joueurs de plus : choisis un poste ou affine la recherche.
          </p>
        )}
      </div>
    </div>
  );
}
