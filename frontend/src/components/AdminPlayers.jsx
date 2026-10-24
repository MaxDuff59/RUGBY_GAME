import { useCallback, useEffect, useMemo, useState } from "react";

import { adminApi } from "../adminApi.js";
import { byLeague } from "../adminFormat.js";
import { ATTRIBUTES, KEY_ATTRIBUTES, NATIONALITIES, POSITION_ORDER, POSITIONS } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import ClubCrest from "./ClubCrest.jsx";
import { useConfirm } from "./ConfirmDialog.jsx";
import PlayerAvatar from "./PlayerAvatar.jsx";

// Backoffice, onglet Joueurs : tous les joueurs des effectifs (recherche, club, poste), et
// pour le joueur choisi sa fiche, son club, sa photo et ses notes. Tout vaut pour les
// nouvelles parties, comme l'effectif d'un club. « Nouveau joueur » en crée un dans le club
// de son choix. Un club n'a pas deux joueurs du même nom : club et nom désignent le joueur.

// Joueur en cours de création (à la place d'une clé dans `selected`).
const NEW = "\u0000nouveau";
// Au-delà, la liste demande d'affiner la recherche (des milliers de joueurs).
const MAX_ROWS = 200;
const SQUADS = { pros: "Pros", youths: "Espoirs" };

const keyOf = (player) => `${player.club}\u0000${player.name}`;
const average = (attributes) => Object.values(attributes).reduce((sum, v) => sum + v, 0) / ATTRIBUTES.length;
const oneDecimal = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export default function AdminPlayers() {
  const players = useApi(useCallback(adminApi.players, []));
  const clubs = useApi(useCallback(adminApi.clubs, []));
  const phone = useMediaQuery(PHONE_QUERY);
  const confirm = useConfirm();
  const [query, setQuery] = useState("");
  const [club, setClub] = useState("");
  const [position, setPosition] = useState("");
  const [fixedOnly, setFixedOnly] = useState(false);
  const [selected, setSelected] = useState(null);
  const [dirty, setDirty] = useState(false);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (players.data ?? []).filter(
      (p) =>
        (!club || p.club === club) &&
        (!position || p.position === position) &&
        (!fixedOnly || p.attributes) &&
        (!needle || p.name.toLowerCase().includes(needle)),
    );
  }, [players.data, query, club, position, fixedOnly]);

  // Changer de joueur avec des changements pas encore enregistrés : on demande d'abord.
  const choose = (key) => {
    if (!dirty || key === selected) return setSelected(key);
    confirm.ask({
      eyebrow: "Joueurs",
      title: "Abandonner les changements",
      text: "Ce qui a été saisi n'est pas enregistré.",
      confirmLabel: "Abandonner",
      cautious: true,
      onConfirm: async () => {
        setDirty(false);
        setSelected(key);
      },
    });
  };

  // Un joueur enregistré (peut-être renommé ou parti ailleurs) : sa ligne remplace l'ancienne.
  const replace = (oldKey, detail) => {
    const { typical, ...row } = detail;
    const known = players.data.some((p) => keyOf(p) === oldKey);
    players.setData(known ? players.data.map((p) => (keyOf(p) === oldKey ? row : p)) : [row, ...players.data]);
    setDirty(false);
    setSelected(keyOf(row));
  };
  const removed = (key) => {
    players.setData(players.data.filter((p) => keyOf(p) !== key));
    setDirty(false);
    setSelected(null);
  };

  if (players.loading || clubs.loading) return <p className="status">Chargement des joueurs…</p>;
  if (players.error || clubs.error) return <p className="status status--error">{(players.error ?? clubs.error).message}</p>;

  const list = (
    <section className="card admin__panel">
      <div className="admin__tools">
        <input className="input" type="search" placeholder="Rechercher un joueur" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="admin__tools-row">
          <ClubSelect clubs={clubs.data} value={club} onChange={setClub} empty="Tous les clubs" />
          <select className="input" value={position} onChange={(e) => setPosition(e.target.value)} aria-label="Poste">
            <option value="">Tous les postes</option>
            {POSITION_ORDER.map((p) => (
              <option key={p} value={p}>
                {POSITIONS[p].label}
              </option>
            ))}
          </select>
        </div>
        <div className="admin__tools-row">
          <label className="admin__check">
            <input type="checkbox" checked={fixedOnly} onChange={(e) => setFixedOnly(e.target.checked)} />
            Notes fixées seulement
          </label>
          <span className="admin__spacer" />
          <button type="button" className="button button--primary" onClick={() => choose(NEW)}>
            Nouveau joueur
          </button>
        </div>
      </div>
      <div className="admin__scroll">
        <table className="table admin__table">
          <thead>
            <tr>
              <th className="left">Joueur</th>
              <th className="left">Club</th>
              <th title="Note générale fixée (sinon tirée à la création de chaque partie)">Note</th>
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, MAX_ROWS).map((p) => (
              <tr key={keyOf(p)} className={`admin__row${keyOf(p) === selected ? " admin__row--on" : ""}`} onClick={() => choose(keyOf(p))}>
                <td className="left">
                  <span className="person">
                    <PlayerAvatar src={p.photo_url} size={30} />
                    <span className="admin__person">
                      <span className="admin__person-name">{p.name}</span>
                      <span className="admin__person-meta">
                        {POSITIONS[p.position].label}
                        {p.squad === "youths" ? " · espoir" : ""}
                      </span>
                    </span>
                  </span>
                </td>
                <td className="left">
                  <span className="admin__player-club">
                    <ClubCrest name={p.club} size={20} />
                    <span className="admin__player-club-name">{p.club}</span>
                  </span>
                </td>
                <td>{p.attributes ? oneDecimal.format(average(p.attributes)) : "—"}</td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr>
                <td colSpan={3} className="left muted">
                  Aucun joueur.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {shown.length > MAX_ROWS && (
          <p className="muted admin__more">
            {shown.length - MAX_ROWS} joueurs de plus : choisis un club ou affine la recherche.
          </p>
        )}
      </div>
    </section>
  );

  const back = phone ? () => choose(null) : null;
  let editor;
  if (selected === NEW) {
    editor = <CreatePlayerForm clubs={clubs.data} club={club} onCreated={(detail) => replace(null, detail)} onDirty={setDirty} onBack={back} />;
  } else if (selected) {
    const [clubName, name] = selected.split("\u0000");
    editor = (
      <PlayerEditor
        key={selected}
        club={clubName}
        name={name}
        clubs={clubs.data}
        onSaved={(detail) => replace(selected, detail)}
        onPhoto={(detail) => players.setData(players.data.map((p) => (keyOf(p) === selected ? { ...p, ...detail } : p)))}
        onDeleted={() => removed(selected)}
        onDirty={setDirty}
        onBack={back}
      />
    );
  } else {
    editor = (
      <section className="card admin__panel admin__empty">
        <p className="muted">Choisis un joueur pour changer sa fiche, son club, sa photo ou ses notes, ou crée-en un.</p>
      </section>
    );
  }

  return (
    <div className="admin__split admin__split--players">
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

// Les clubs regroupés par championnat.
function ClubSelect({ clubs, value, onChange, empty }) {
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Club">
      {empty && <option value="">{empty}</option>}
      {byLeague(clubs).map(([league, list]) => (
        <optgroup key={league} label={league}>
          {list.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

// --- Fiche ---------------------------------------------------------------------------------

const formOf = (player) => ({
  name: player.name,
  position: player.position,
  nationality: player.nationality,
  international: player.international,
  born: player.born,
  photo: player.photo,
  attributes: player.attributes,
  club: player.club,
  squad: player.squad,
});

function SheetFields({ form, set, clubs, current }) {
  const target = clubs.find((c) => c.name === form.club);
  return (
    <div className="admin__fields">
      <label className="field admin__field">
        <span className="field__label">Nom</span>
        <input className="input" value={form.name} maxLength={100} required placeholder="Prénom Nom" onChange={(e) => set("name", e.target.value)} />
      </label>
      <label className="field admin__field">
        <span className="field__label">Poste</span>
        <select className="input" value={form.position} onChange={(e) => set("position", e.target.value)}>
          {POSITION_ORDER.map((p) => (
            <option key={p} value={p}>
              {POSITIONS[p].label}
            </option>
          ))}
        </select>
      </label>
      <label className="field admin__field">
        <span className="field__label">Club</span>
        <ClubSelect clubs={clubs} value={form.club} onChange={(v) => set("club", v)} />
        <span className="muted admin__hint">
          {form.club !== current && target?.roster_source === "inventé"
            ? "Ce club n'a pas d'effectif : le jeu invente ses autres joueurs"
            : target?.league_name}
        </span>
      </label>
      <label className="field admin__field">
        <span className="field__label">Groupe</span>
        <select className="input" value={form.squad} onChange={(e) => set("squad", e.target.value)}>
          {Object.entries(SQUADS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <span className="muted admin__hint">Un espoir de 21 ans ou plus ne reste pas au centre de formation</span>
      </label>
      <label className="field admin__field">
        <span className="field__label">Nationalité</span>
        <select className="input" value={form.nationality ?? ""} onChange={(e) => set("nationality", e.target.value || null)}>
          <option value="">—</option>
          {form.nationality && !NATIONALITIES[form.nationality] && <option value={form.nationality}>{form.nationality}</option>}
          {Object.entries(NATIONALITIES).map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="field admin__field">
        <span className="field__label">Né le</span>
        <input className="input" type="date" value={form.born ?? ""} onChange={(e) => set("born", e.target.value || null)} />
        <span className="muted admin__hint">Sans date, son âge est tiré au hasard</span>
      </label>
      <label className="admin__check admin__field">
        <input type="checkbox" checked={form.international} onChange={(e) => set("international", e.target.checked)} />
        International (plus fort que ses coéquipiers quand ses notes sont tirées)
      </label>
    </div>
  );
}

// Ce que l'API attend : sans les champs vides.
const payload = (form) => ({ ...form, name: form.name.trim(), photo: form.photo?.trim() || null });

function CreatePlayerForm({ clubs, club, onCreated, onDirty, onBack }) {
  const [form, setForm] = useState(() => ({
    name: "",
    position: "PROP",
    nationality: null,
    international: false,
    born: null,
    photo: null,
    attributes: null,
    club: club || clubs[0]?.name,
    squad: "pros",
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));
  const dirty = Boolean(form.name.trim());
  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onCreated(await adminApi.createPlayer(payload(form)));
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <form className="card admin__panel admin__detail" onSubmit={create}>
      <div className="admin__detail-head">
        {onBack && (
          <button type="button" className="admin__link" onClick={onBack}>
            ← Joueurs
          </button>
        )}
        <p className="eyebrow">Nouveau joueur</p>
        <h2 className="admin__name">{form.name.trim() || "Sans nom"}</h2>
        <p className="muted">Il rejoint l'effectif du club pour les nouvelles parties. Photo et notes se fixent une fois le joueur créé.</p>
      </div>
      <div className="admin__scroll admin__detail-body">
        <div className="admin__block">
          <SheetFields form={form} set={set} clubs={clubs} current={form.club} />
        </div>
      </div>
      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        <button type="submit" className="button button--primary" disabled={busy || !dirty}>
          {busy ? "Création…" : "Créer le joueur"}
        </button>
      </div>
    </form>
  );
}

function PlayerEditor({ club, name, clubs, onSaved, onPhoto, onDeleted, onDirty, onBack }) {
  const player = useApi(useCallback(() => adminApi.player(club, name), [club, name]));
  const confirm = useConfirm();
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (player.data && !form) setForm(formOf(player.data));
  }, [player.data, form]);
  const dirty = Boolean(form && player.data) && JSON.stringify(form) !== JSON.stringify(formOf(player.data));
  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);

  if (player.loading || (player.data && !form)) return <section className="card admin__panel admin__empty"><p className="muted">Chargement…</p></section>;
  if (player.error) return <section className="card admin__panel admin__empty"><p className="status--error">{player.error.message}</p></section>;
  const p = player.data;
  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      // Renommé ou parti dans un autre club, il a une autre clé : la fiche se rouvre.
      const detail = await adminApi.savePlayer(club, name, payload(form));
      player.setData(detail);
      setForm(formOf(detail));
      onSaved(detail);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  // La photo s'enregistre tout de suite, sans toucher aux saisies en cours.
  async function photo(call) {
    setError(null);
    try {
      const detail = await call();
      player.setData(detail);
      onPhoto(detail);
    } catch (err) {
      setError(err);
    }
  }

  function upload(event) {
    const file = event.target.files[0];
    event.target.value = "";
    if (file) photo(async () => adminApi.uploadPlayerPhoto(club, name, await squarePhoto(file)));
  }

  const remove = () =>
    confirm.ask({
      eyebrow: p.club,
      title: `Supprimer ${p.name}`,
      text: "Il quitte l'effectif du club dans les nouvelles parties. Les parties déjà commencées le gardent.",
      confirmLabel: "Supprimer",
      cautious: true,
      onConfirm: async () => {
        await adminApi.deletePlayer(club, name);
        onDeleted();
      },
    });

  return (
    <section className="card admin__panel admin__detail">
      {confirm.dialog}
      <div className="admin__detail-head">
        {onBack && (
          <button type="button" className="admin__link" onClick={onBack}>
            ← Joueurs
          </button>
        )}
        <div className="admin__club-head">
          <PlayerAvatar src={p.photo_url} size={56} />
          <div>
            <p className="eyebrow">
              {p.club} · {SQUADS[p.squad]}
            </p>
            <h2 className="admin__name">{p.name}</h2>
            <p className="muted">
              {POSITIONS[p.position].label}
              {p.attributes ? ` · notes fixées, ${oneDecimal.format(average(p.attributes))} de moyenne` : " · notes tirées par le jeu"}
            </p>
          </div>
          <button type="button" className="button admin__reset" onClick={remove}>
            Supprimer
          </button>
        </div>
      </div>

      <div className="admin__scroll admin__detail-body">
        <div className="admin__block">
          <h3 className="eyebrow">Fiche</h3>
          <p className="muted admin__note">Pour les nouvelles parties : les parties commencées gardent leurs joueurs.</p>
          <SheetFields form={form} set={set} clubs={clubs} current={p.club} />
        </div>

        <div className="admin__block">
          <h3 className="eyebrow">Photo</h3>
          <div className="admin__logo">
            <PlayerAvatar src={p.photo_url} size={72} />
            <div className="admin__logo-text">
              <span>{p.photo_id ? "Photo envoyée depuis le backoffice" : p.photo ? "Photo de Wikimedia Commons" : "Pas de photo : silhouette"}</span>
              <span className="muted">Une image du visage ; elle est recadrée en carré et réduite avant l'envoi.</span>
            </div>
            <div className="admin__actions">
              <label className="button button--small admin__file">
                Envoyer une photo
                <input type="file" accept="image/*" onChange={upload} />
              </label>
              {p.photo_id && (
                <button type="button" className="button button--small" onClick={() => photo(() => adminApi.deletePlayerPhoto(club, name))}>
                  Retirer la photo envoyée
                </button>
              )}
            </div>
          </div>
          <label className="field admin__field">
            <span className="field__label">Fichier sur Wikimedia Commons</span>
            <input className="input" value={form.photo ?? ""} maxLength={300} placeholder="Nom du fichier.jpg" onChange={(e) => set("photo", e.target.value || null)} />
            <span className="muted admin__hint">{p.photo_id ? "Utilisé si la photo envoyée est retirée" : "Pris à Wikimedia à la première demande, puis gardé par le jeu"}</span>
          </label>
        </div>

        <RatingsBlock form={form} set={set} typical={p.typical} />
      </div>

      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        <button type="button" className="button" disabled={!dirty || busy} onClick={() => setForm(formOf(p))}>
          Annuler
        </button>
        <button type="button" className="button button--primary" disabled={!dirty || busy || !form.name.trim()} onClick={save}>
          {busy ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>
    </section>
  );
}

// --- Notes ---------------------------------------------------------------------------------

function RatingsBlock({ form, set, typical }) {
  const notes = form.attributes;
  const key = new Set(KEY_ATTRIBUTES[form.position]);
  const setNote = (name, value) => set("attributes", { ...notes, [name]: Math.min(20, Math.max(1, Math.round(Number(value) || 1))) });

  return (
    <div className="admin__block">
      <h3 className="eyebrow">Notes</h3>
      {notes ? (
        <>
          <p className="muted admin__note">
            Fixées : le joueur a ces notes au début de chaque nouvelle partie, puis progresse ou décline comme les autres.
            Note générale {oneDecimal.format(average(notes))}.
          </p>
          <div className="admin__ratings">
            {ATTRIBUTES.map((a) => (
              <label key={a.key} className={`admin__rating${key.has(a.key) ? " admin__rating--key" : ""}`}>
                <span className="admin__rating-label">{a.label}</span>
                <input type="range" min={1} max={20} step={1} value={notes[a.key]} onChange={(e) => setNote(a.key, e.target.value)} />
                <input className="input admin__rating-value" type="number" min={1} max={20} value={notes[a.key]} onChange={(e) => setNote(a.key, e.target.value)} aria-label={a.label} />
              </label>
            ))}
          </div>
          <div className="admin__actions">
            <button type="button" className="button button--small" onClick={() => set("attributes", { ...typical })}>
              Notes typiques de son club
            </button>
            <button type="button" className="button button--small" onClick={() => set("attributes", null)}>
              Laisser le jeu les tirer
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="muted admin__note">
            Tirées à la création de chaque partie autour du niveau de son club, plus haut s'il est international, selon son âge.
            Pour un joueur comme lui : {oneDecimal.format(average(typical))} de moyenne.
          </p>
          <div className="admin__actions">
            <button type="button" className="button button--small" onClick={() => set("attributes", { ...typical })}>
              Fixer ses notes
            </button>
          </div>
        </>
      )}
      <p className="muted admin__hint">En gras : les notes qui comptent le plus à son poste.</p>
    </div>
  );
}

// La photo recadrée en carré (le haut de l'image, où est le visage) et réduite, en JPEG base64.
async function squarePhoto(file, size = 320) {
  const image = await createImageBitmap(file);
  const side = Math.min(image.width, image.height);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = Math.min(size, side);
  const top = image.height > image.width ? (image.height - side) * 0.2 : 0;
  canvas.getContext("2d").drawImage(image, (image.width - side) / 2, top, side, side, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.88).split(",")[1];
}
