import { useCallback, useEffect, useMemo, useState } from "react";

import { adminApi } from "../adminApi.js";
import { byLeague, formatDayTime } from "../adminFormat.js";
import { defaultClubInfo, setClubOverride } from "../clubs.js";
import { NATIONALITIES, POSITION_ORDER, POSITIONS } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import ClubCrest from "./ClubCrest.jsx";
import { useConfirm } from "./ConfirmDialog.jsx";
import JerseyFlat from "./JerseyFlat.jsx";

// Backoffice, onglet Clubs : les clubs par championnat (vrais et créés), et pour le club
// choisi sa fiche (championnat, stade, niveau, budget), ses couleurs et son blason, puis son
// effectif. Fiche et effectif valent pour les nouvelles parties ; couleurs et blason tout de
// suite. « Nouveau club » en crée un dans le championnat de son choix.

const EDITED_LABELS = {
  city: "ville",
  stadium: "stade",
  capacity: "capacité",
  level: "niveau",
  wealth: "budget",
  colors: "couleurs",
  light: "blason blanc",
  logo: "blason",
  roster: "effectif",
  league: "championnat",
};

// Club en cours de création (à la place d'un nom dans `selected`).
const NEW = "\u0000nouveau";

const DEFAULT_COLORS = ["#16181B", "#FFFFFF"];

export default function AdminClubs() {
  const clubs = useApi(useCallback(adminApi.clubs, []));
  const leagues = useApi(useCallback(adminApi.leagues, []));
  const phone = useMediaQuery(PHONE_QUERY);
  const confirm = useConfirm();
  const [query, setQuery] = useState("");
  const [league, setLeague] = useState("");
  const [selected, setSelected] = useState(null);
  const [dirty, setDirty] = useState(false);

  // Chaque championnat (archivés seulement s'ils gardent des clubs), même vide, avec ses clubs.
  const groups = useMemo(() => {
    const list = clubs.data ?? [];
    return (leagues.data ?? [])
      .map((lg) => ({ league: lg, clubs: list.filter((c) => c.league === lg.code) }))
      .filter((g) => !g.league.archived || g.clubs.length);
  }, [clubs.data, leagues.data]);
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return groups
      .filter((g) => !league || g.league.code === league)
      .map((g) => ({ ...g, clubs: g.clubs.filter((c) => !needle || c.name.toLowerCase().includes(needle)) }))
      .filter((g) => !needle || g.clubs.length);
  }, [groups, query, league]);

  // Changer de club avec des retouches pas encore enregistrées : on demande d'abord.
  const choose = (name) => {
    if (!dirty || name === selected) return setSelected(name);
    confirm.ask({
      eyebrow: selected === NEW ? "Nouveau club" : selected,
      title: "Abandonner les changements",
      text: "Ce qui a été saisi n'est pas enregistré.",
      confirmLabel: "Abandonner",
      cautious: true,
      onConfirm: async () => {
        setDirty(false);
        setSelected(name);
      },
    });
  };

  // Un club enregistré : sa ligne, et le compte des championnats (il a pu changer de l'un à l'autre).
  const replace = (summary) => {
    const known = clubs.data.some((c) => c.name === summary.name);
    clubs.setData(
      known ? clubs.data.map((c) => (c.name === summary.name ? { ...c, ...summary } : c)) : [...clubs.data, summary],
    );
    leagues.reload();
  };
  const created = (detail) => {
    replace(detail);
    setDirty(false);
    setSelected(detail.name);
  };
  const removed = (name) => {
    clubs.setData(clubs.data.filter((c) => c.name !== name));
    leagues.reload();
    setDirty(false);
    setSelected(null);
  };

  if (clubs.loading || leagues.loading) return <p className="status">Chargement des clubs…</p>;
  if (clubs.error || leagues.error) return <p className="status status--error">{(clubs.error ?? leagues.error).message}</p>;

  const list = (
    <section className="card admin__panel">
      <div className="admin__tools">
        <input className="input" type="search" placeholder="Rechercher un club" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="admin__tools-row">
          <select className="input" value={league} onChange={(e) => setLeague(e.target.value)} aria-label="Championnat">
            <option value="">Tous les championnats</option>
            {groups.map(({ league: lg }) => (
              <option key={lg.code} value={lg.code}>
                {lg.name}
              </option>
            ))}
          </select>
          <button type="button" className="button button--primary" onClick={() => choose(NEW)}>
            Nouveau club
          </button>
        </div>
      </div>
      <div className="admin__scroll">
        {shown.map(({ league: lg, clubs: list }) => (
          <div key={lg.code} className="admin__group">
            <h3 className="admin__group-title eyebrow">
              {lg.name}
              <span className="admin__group-count">
                {lg.clubs}/{lg.max_clubs}
              </span>
              {!lg.ready && (
                <span className="admin__warn" title={lg.archived ? "Archivé : hors des nouvelles parties" : `Il faut au moins ${lg.min_clubs} clubs pour sa formule`}>
                  {lg.archived ? "Archivé" : `Incomplet · ${lg.min_clubs} min.`}
                </span>
              )}
            </h3>
            {list.length === 0 && <p className="muted admin__group-empty">Aucun club.</p>}
            <ul className="admin__clubs">
              {list.map((club) => (
                <li key={club.name}>
                  <button
                    type="button"
                    className="admin__club"
                    aria-pressed={club.name === selected}
                    onClick={() => choose(club.name)}
                  >
                    <ClubCrest name={club.name} size={28} />
                    <span className="admin__club-name">{club.name}</span>
                    <Swatches colors={club.colors ?? defaultClubInfo(club.name).colors} />
                    {(club.created || club.edited.length > 0) && (
                      <span
                        className={`admin__dot${club.created ? " admin__dot--new" : ""}`}
                        title={club.created ? "Club créé depuis le backoffice" : `Retouché : ${club.edited.map((f) => EDITED_LABELS[f]).join(", ")}`}
                      />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );

  const back = phone ? () => choose(null) : null;
  let editor;
  if (selected === NEW) {
    editor = <CreateClubForm leagues={leagues.data} onCreated={created} onDirty={setDirty} onBack={back} />;
  } else if (selected) {
    editor = (
      <ClubEditor
        key={selected}
        name={selected}
        leagues={leagues.data}
        onChange={replace}
        onDeleted={removed}
        onDirty={setDirty}
        onBack={back}
      />
    );
  } else {
    editor = (
      <section className="card admin__panel admin__empty">
        <p className="muted">
          Choisis un club pour retoucher sa fiche, son championnat, ses couleurs, son blason ou son effectif, ou crée-en un.
        </p>
      </section>
    );
  }

  return (
    <div className="admin__split admin__split--clubs">
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

// Les championnats où l'on peut mettre un club : pas les archivés, ni les pleins (sauf le sien).
function LeagueSelect({ leagues, value, current, onChange }) {
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      {leagues
        .filter((lg) => !lg.archived || lg.code === current)
        .map((lg) => {
          const full = lg.clubs >= lg.max_clubs && lg.code !== current;
          return (
            <option key={lg.code} value={lg.code} disabled={full}>
              {lg.name} ({lg.clubs}/{lg.max_clubs}){full ? " · complet" : ""}
            </option>
          );
        })}
    </select>
  );
}

function NationSelect({ value, onChange, empty = "Aucun pays" }) {
  return (
    <select className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">{empty}</option>
      {Object.entries(NATIONALITIES).map(([code, label]) => (
        <option key={code} value={code}>
          {label}
        </option>
      ))}
    </select>
  );
}

function Swatches({ colors }) {
  return (
    <span className="admin__swatches" aria-hidden="true">
      {colors.map((color, i) => (
        <span key={i} className="admin__swatch" style={{ background: color }} />
      ))}
    </span>
  );
}

// --- Un club ------------------------------------------------------------------------------

function ClubEditor({ name, leagues, onChange, onDeleted, onDirty, onBack }) {
  const club = useApi(useCallback(() => adminApi.club(name), [name]));
  const confirm = useConfirm();
  const [tab, setTab] = useState("sheet");
  const [sheetDirty, setSheetDirty] = useState(false);
  const [rosterDirty, setRosterDirty] = useState(false);

  useEffect(() => onDirty(sheetDirty || rosterDirty), [sheetDirty, rosterDirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);

  // Après chaque enregistrement : la fiche, la ligne de la liste et les couleurs de l'interface.
  const saved = (detail) => {
    club.setData(detail);
    onChange(detail);
    setClubOverride(detail.name, overrideOf(detail));
  };

  if (club.loading) return <section className="card admin__panel admin__empty"><p className="muted">Chargement…</p></section>;
  if (club.error) return <section className="card admin__panel admin__empty"><p className="status--error">{club.error.message}</p></section>;
  const c = club.data;

  const resetAll = () =>
    confirm.ask({
      eyebrow: c.name,
      title: "Tout remettre d'origine",
      text: "Fiche, championnat, couleurs, blason envoyé et effectif reviennent à ceux du jeu. Les parties commencées ne changent pas.",
      confirmLabel: "Remettre d'origine",
      cautious: true,
      onConfirm: async () => {
        saved(await adminApi.resetClub(c.name));
        setSheetDirty(false);
        setRosterDirty(false);
      },
    });
  const remove = () =>
    confirm.ask({
      eyebrow: c.name,
      title: "Supprimer le club",
      text: "Le club disparaît des nouvelles parties. Les parties déjà commencées le gardent.",
      confirmLabel: "Supprimer",
      cautious: true,
      onConfirm: async () => {
        await adminApi.resetClub(c.name);
        setClubOverride(c.name, {});
        onDeleted(c.name);
      },
    });

  return (
    <section className="card admin__panel admin__detail">
      {confirm.dialog}
      <div className="admin__detail-head">
        {onBack && (
          <button type="button" className="admin__link" onClick={onBack}>
            ← Clubs
          </button>
        )}
        <div className="admin__club-head">
          <ClubCrest name={c.name} size={48} />
          <div>
            <p className="eyebrow">{c.league_name}</p>
            <h2 className="admin__name">{c.name}</h2>
            <p className="muted">
              {c.created
                ? `Club créé par ${c.updated_by}, ${formatDayTime(c.updated_at)}`
                : c.edited.length
                  ? `Retouché (${c.edited.map((f) => EDITED_LABELS[f]).join(", ")})${c.updated_by ? ` par ${c.updated_by}, ${formatDayTime(c.updated_at)}` : ""}`
                  : "Tel que dans le jeu"}
            </p>
          </div>
          {c.created ? (
            <button type="button" className="button admin__reset" onClick={remove}>
              Supprimer le club
            </button>
          ) : (
            c.edited.length > 0 && (
              <button type="button" className="button admin__reset" onClick={resetAll}>
                Tout remettre d'origine
              </button>
            )
          )}
        </div>
        <div className="chips" role="group" aria-label="Partie de la fiche">
          <button type="button" className="chip chip--small" aria-pressed={tab === "sheet"} onClick={() => setTab("sheet")}>
            Fiche et couleurs{sheetDirty ? " •" : ""}
          </button>
          <button type="button" className="chip chip--small" aria-pressed={tab === "roster"} onClick={() => setTab("roster")}>
            Effectif ({c.pros} pros · {c.youths} espoirs){rosterDirty ? " •" : ""}
          </button>
        </div>
      </div>

      {/* Les deux onglets restent montés : leurs saisies survivent au passage de l'un à l'autre. */}
      <div className="admin__tab" hidden={tab !== "sheet"}>
        <SheetForm club={c} leagues={leagues} onSaved={saved} onDirty={setSheetDirty} />
      </div>
      <div className="admin__tab" hidden={tab !== "roster"}>
        <RosterForm club={c} onSaved={saved} onDirty={setRosterDirty} />
      </div>
    </section>
  );
}

// Ce que l'interface doit savoir des couleurs et du blason d'un club (clubs.js).
function overrideOf(detail) {
  const entry = {};
  if (detail.colors) entry.colors = detail.colors;
  if (detail.light !== null) entry.light = detail.light;
  if (detail.logo) entry.logo = detail.logo;
  return entry;
}

// --- Nouveau club ---------------------------------------------------------------------------

function CreateClubForm({ leagues, onCreated, onDirty, onBack }) {
  const open = leagues.filter((lg) => !lg.archived && lg.clubs < lg.max_clubs);
  const [form, setForm] = useState(() => ({
    name: "",
    league: open[0]?.code ?? "",
    nation: null,
    city: "",
    stadium: "",
    capacity: 8000,
    level: 9,
    wealth: 0.3,
    colors: DEFAULT_COLORS,
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));
  const dirty = Boolean(form.name || form.city || form.stadium);
  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);
  const league = leagues.find((lg) => lg.code === form.league);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const detail = await adminApi.createClub({
        ...form,
        capacity: Number(form.capacity),
        level: Number(form.level),
        wealth: Number(form.wealth),
      });
      setClubOverride(detail.name, overrideOf(detail));
      onCreated(detail);
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
            ← Clubs
          </button>
        )}
        <p className="eyebrow">Nouveau club</p>
        <h2 className="admin__name">{form.name || "Sans nom"}</h2>
        <p className="muted">
          Il jouera dans les nouvelles parties, avec des joueurs inventés tant que tu ne lui donnes pas d'effectif.
        </p>
      </div>
      <div className="admin__scroll admin__detail-body">
        <div className="admin__block">
          <div className="admin__fields">
            <label className="field admin__field">
              <span className="field__label">Nom</span>
              <input className="input" value={form.name} maxLength={100} required minLength={2} onChange={(e) => set("name", e.target.value)} autoFocus />
            </label>
            <label className="field admin__field">
              <span className="field__label">Championnat</span>
              <LeagueSelect leagues={leagues} value={form.league} onChange={(v) => set("league", v)} />
            </label>
            <label className="field admin__field">
              <span className="field__label">Pays</span>
              <NationSelect value={form.nation} onChange={(v) => set("nation", v)} empty={league?.nation ? "Celui du championnat" : "Aucun pays"} />
              <span className="muted admin__hint">Nationalité de ses joueurs inventés</span>
            </label>
            <label className="field admin__field">
              <span className="field__label">Ville</span>
              <input className="input" value={form.city} maxLength={100} required onChange={(e) => set("city", e.target.value)} />
            </label>
            <label className="field admin__field">
              <span className="field__label">Stade</span>
              <input className="input" value={form.stadium} maxLength={100} required onChange={(e) => set("stadium", e.target.value)} />
            </label>
            <label className="field admin__field">
              <span className="field__label">Capacité</span>
              <input className="input" type="number" min={1000} max={100000} step={500} value={form.capacity} onChange={(e) => set("capacity", e.target.value)} />
            </label>
            <label className="field admin__field">
              <span className="field__label">Niveau sportif (sur 20)</span>
              <input className="input" type="number" min={4} max={18} step={0.5} value={form.level} onChange={(e) => set("level", e.target.value)} />
              <span className="muted admin__hint">Top 14 : 8,5 à 14 · Pro D2 : 7,5 à 9,5</span>
            </label>
            <label className="field admin__field">
              <span className="field__label">Budget · {Math.round(Number(form.wealth) * 100)} %</span>
              <input type="range" min={0} max={1} step={0.05} value={form.wealth} onChange={(e) => set("wealth", e.target.value)} />
            </label>
          </div>
        </div>
        <div className="admin__block">
          <h3 className="eyebrow">Couleurs</h3>
          <div className="admin__colors admin__colors--row">
            {form.colors.map((color, i) => (
              <label key={i} className="admin__color">
                <input type="color" value={color} onChange={(e) => set("colors", form.colors.map((c, j) => (j === i ? e.target.value.toUpperCase() : c)))} />
                <span className="admin__mono">{color}</span>
                <span className="muted">{["Primaire", "Secondaire"][i]}</span>
              </label>
            ))}
          </div>
          <p className="muted admin__note">Le blason et une troisième couleur s'ajoutent une fois le club créé.</p>
        </div>
      </div>
      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        <button type="submit" className="button button--primary" disabled={busy || !form.league}>
          {busy ? "Création…" : "Créer le club"}
        </button>
      </div>
    </form>
  );
}

// --- Fiche, couleurs et blason ------------------------------------------------------------

const sheetOf = (club) => ({
  league: club.league,
  nation: club.nation,
  city: club.city,
  stadium: club.stadium,
  capacity: club.capacity,
  level: club.level,
  wealth: club.wealth,
  colors: club.colors,
  light: club.light,
});

function SheetForm({ club, leagues, onSaved, onDirty }) {
  const defaults = club.defaults ?? {};
  const [form, setForm] = useState(() => sheetOf(club));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const origin = defaultClubInfo(club.name);
  const colors = form.colors ?? origin.colors;
  const light = form.light ?? origin.light;

  const dirty = JSON.stringify(form) !== JSON.stringify(sheetOf(club));
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));
  const setColor = (i, value) => set("colors", colors.map((c, j) => (j === i ? value.toUpperCase() : c)));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const sameColors = JSON.stringify(form.colors) === JSON.stringify(origin.colors);
      const detail = await adminApi.saveClub(club.name, {
        ...form,
        capacity: Number(form.capacity),
        level: Number(form.level),
        wealth: Number(form.wealth),
        colors: sameColors ? null : form.colors,
        light: form.light === origin.light ? null : form.light,
        nation: club.created ? form.nation : null,
      });
      onSaved(detail);
      setForm(sheetOf(detail));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function logo(call) {
    setError(null);
    try {
      onSaved(await call());
    } catch (err) {
      setError(err);
    }
  }

  function upload(event) {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => logo(() => adminApi.uploadLogo(club.name, String(reader.result).split(",")[1]));
    reader.readAsDataURL(file);
  }

  const home = { pattern: "plain", base: colors[0], motif: colors[1] ?? "#FFFFFF", trim: colors[1] ?? "#FFFFFF" };
  const away = { pattern: "plain", base: colors[1] ?? "#FFFFFF", motif: colors[0], trim: colors[0] };

  return (
    <>
      <div className="admin__scroll admin__detail-body">
        <div className="admin__block">
          <h3 className="eyebrow">Fiche</h3>
          <p className="muted admin__note">Pour les nouvelles parties : les parties commencées gardent leur club.</p>
          <div className="admin__fields">
            <Field
              label="Championnat"
              origin={defaults.league}
              value={form.league}
              format={(code) => leagues.find((lg) => lg.code === code)?.name ?? code}
              hint="Dans une partie, la montée et la descente le font changer"
            >
              <LeagueSelect leagues={leagues} value={form.league} current={club.league} onChange={(v) => set("league", v)} />
            </Field>
            {club.created && (
              <label className="field admin__field">
                <span className="field__label">Pays</span>
                <NationSelect value={form.nation} onChange={(v) => set("nation", v)} empty="Celui du championnat" />
                <span className="muted admin__hint">Nationalité de ses joueurs inventés</span>
              </label>
            )}
            <Field label="Ville" origin={defaults.city} value={form.city}>
              <input className="input" value={form.city} maxLength={100} onChange={(e) => set("city", e.target.value)} />
            </Field>
            <Field label="Stade" origin={defaults.stadium} value={form.stadium}>
              <input className="input" value={form.stadium} maxLength={100} onChange={(e) => set("stadium", e.target.value)} />
            </Field>
            <Field label="Capacité" origin={defaults.capacity} value={Number(form.capacity)} hint="Plafonnée au plus grand stade constructible">
              <input className="input" type="number" min={1000} max={100000} step={500} value={form.capacity} onChange={(e) => set("capacity", e.target.value)} />
            </Field>
            <Field label="Niveau sportif (sur 20)" origin={defaults.level} value={Number(form.level)} hint="Niveau autour duquel les joueurs sont tirés">
              <input className="input" type="number" min={4} max={18} step={0.5} value={form.level} onChange={(e) => set("level", e.target.value)} />
            </Field>
            <Field
              label={`Budget · ${Math.round(Number(form.wealth) * 100)} %`}
              origin={defaults.wealth}
              value={Number(form.wealth)}
              format={(v) => `${Math.round(v * 100)} %`}
              hint="Trésorerie, staff et infrastructures de départ (0 % : club modeste)"
            >
              <input type="range" min={0} max={1} step={0.05} value={form.wealth} onChange={(e) => set("wealth", e.target.value)} />
            </Field>
          </div>
        </div>
        <div className="admin__block">
          <h3 className="eyebrow">Couleurs et blason</h3>
          <p className="muted admin__note">Changent tout de suite, dans toutes les parties.</p>
          <div className="admin__look">
            <div className="admin__jerseys">
              <JerseyFlat jersey={home} clubName={club.name} size={96} title="Domicile" />
              <JerseyFlat jersey={away} clubName={club.name} size={96} title="Extérieur" />
            </div>
            <div className="admin__colors">
              {colors.map((color, i) => (
                <label key={i} className="admin__color">
                  <input type="color" value={color} onChange={(e) => setColor(i, e.target.value)} />
                  <span className="admin__mono">{color}</span>
                  <span className="muted">{["Primaire", "Secondaire", "Troisième"][i]}</span>
                  {colors.length > 1 && (
                    <button type="button" className="admin__link" onClick={() => set("colors", colors.filter((_, j) => j !== i))}>
                      Retirer
                    </button>
                  )}
                </label>
              ))}
              <div className="admin__actions">
                {colors.length < 3 && (
                  <button type="button" className="button button--small" onClick={() => set("colors", [...colors, "#FFFFFF"])}>
                    Ajouter une couleur
                  </button>
                )}
                {form.colors && (
                  <button type="button" className="button button--small" onClick={() => set("colors", null)}>
                    Couleurs d'origine
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="admin__logo">
            <ClubCrest name={club.name} size={56} />
            <div className="admin__logo-text">
              <span>{club.logo ? "Blason envoyé depuis le backoffice" : origin.logo ? "Blason d'origine" : "Pas de blason : écusson à initiales"}</span>
              <span className="muted">PNG, JPEG ou WebP, carré de préférence, 512 Ko au plus.</span>
              <label className="admin__check">
                <input type="checkbox" checked={light} onChange={(e) => set("light", e.target.checked)} />
                Blason blanc (posé sur une pastille de la couleur du club)
              </label>
            </div>
            <div className="admin__actions">
              <label className="button button--small admin__file">
                Envoyer un blason
                <input type="file" accept="image/png,image/jpeg,image/webp" onChange={upload} />
              </label>
              {club.logo && (
                <button type="button" className="button button--small" onClick={() => logo(() => adminApi.deleteLogo(club.name))}>
                  Revenir au blason d'origine
                </button>
              )}
            </div>
          </div>
        </div>

      </div>

      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        <button type="button" className="button" disabled={!dirty || busy} onClick={() => setForm(sheetOf(club))}>
          Annuler
        </button>
        <button type="button" className="button button--primary" disabled={!dirty || busy} onClick={save}>
          {busy ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>
    </>
  );
}

function Field({ label, origin, value, format = (v) => v, hint, children }) {
  return (
    <label className="field admin__field">
      <span className="field__label">{label}</span>
      {children}
      <span className="muted admin__hint">
        {origin !== undefined && value !== origin ? <>D'origine : {format(origin)}</> : hint}
      </span>
    </label>
  );
}

// --- Effectif -----------------------------------------------------------------------------

const SOURCES = {
  backoffice: "Effectif retouché depuis le backoffice.",
  fichier: "Vrai effectif du jeu (data/rosters.json, d'après Wikipédia).",
  inventé: "Pas de vrai effectif : le jeu invente les joueurs. Ajoutes-en pour lui en donner un.",
};

const blank = () => ({ name: "", position: "PROP", nationality: null, international: false, born: null, photo: null });
const rosterOf = (club) => ({ pros: club.roster.pros, youths: club.roster.youths });

function RosterForm({ club, onSaved, onDirty }) {
  const [roster, setRoster] = useState(() => rosterOf(club));
  const [squad, setSquad] = useState("pros");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const confirm = useConfirm();

  const dirty = JSON.stringify(roster) !== JSON.stringify(rosterOf(club));
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const players = roster[squad];
  const update = (list) => setRoster((r) => ({ ...r, [squad]: list }));
  const edit = (i, field, value) => update(players.map((p, j) => (j === i ? { ...p, [field]: value } : p)));
  const counts = POSITION_ORDER.map((position) => [position, players.filter((p) => p.position === position).length]);

  async function run(call) {
    setBusy(true);
    setError(null);
    try {
      const detail = await call();
      onSaved(detail);
      setRoster(rosterOf(detail));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const save = () => {
    const clean = (list) => list.map((p) => ({ ...p, name: p.name.trim() })).filter((p) => p.name);
    return run(() => adminApi.saveRoster(club.name, { pros: clean(roster.pros), youths: clean(roster.youths) }));
  };

  const revert = () =>
    confirm.ask({
      eyebrow: club.name,
      title: club.created ? "Effacer l'effectif" : "Revenir à l'effectif du jeu",
      text: club.created
        ? "L'effectif saisi ici est effacé ; les nouvelles parties inventent les joueurs du club."
        : "L'effectif saisi ici est effacé ; les nouvelles parties reprennent celui de data/rosters.json.",
      confirmLabel: "Revenir",
      cautious: true,
      onConfirm: () => run(() => adminApi.resetRoster(club.name)),
    });

  return (
    <>
      {confirm.dialog}
      <div className="admin__roster-head">
        <p className="muted admin__note">
          {SOURCES[club.roster_source]} Pour les nouvelles parties ; le jeu garde 38 pros et 30 espoirs au plus et
          comble les postes vides.
        </p>
        <div className="admin__roster-tools">
          <div className="chips" role="group" aria-label="Groupe">
            <button type="button" className="chip chip--small" aria-pressed={squad === "pros"} onClick={() => setSquad("pros")}>
              Pros ({roster.pros.length})
            </button>
            <button type="button" className="chip chip--small" aria-pressed={squad === "youths"} onClick={() => setSquad("youths")}>
              Espoirs ({roster.youths.length})
            </button>
          </div>
          <span className="muted admin__counts">
            {counts.map(([position, n]) => `${POSITIONS[position].label} ${n}`).join(" · ")}
          </span>
        </div>
      </div>

      <div className="admin__scroll admin__roster">
        <table className="table admin__table">
          <thead>
            <tr>
              <th className="left">Nom</th>
              <th className="left">Poste</th>
              <th className="left">Nationalité</th>
              <th className="left">Né le</th>
              <th>International</th>
              <th aria-label="Retirer" />
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => (
              <tr key={i}>
                <td className="left">
                  <input className="input admin__cell" value={p.name} maxLength={100} placeholder="Prénom Nom" onChange={(e) => edit(i, "name", e.target.value)} />
                </td>
                <td className="left">
                  <select className="input admin__cell" value={p.position} onChange={(e) => edit(i, "position", e.target.value)}>
                    {POSITION_ORDER.map((position) => (
                      <option key={position} value={position}>
                        {POSITIONS[position].label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="left">
                  <select className="input admin__cell" value={p.nationality ?? ""} onChange={(e) => edit(i, "nationality", e.target.value || null)}>
                    <option value="">—</option>
                    {p.nationality && !NATIONALITIES[p.nationality] && <option value={p.nationality}>{p.nationality}</option>}
                    {Object.entries(NATIONALITIES).map(([code, label]) => (
                      <option key={code} value={code}>
                        {label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="left">
                  <input className="input admin__cell" type="date" value={p.born ?? ""} onChange={(e) => edit(i, "born", e.target.value || null)} />
                </td>
                <td>
                  <input type="checkbox" checked={p.international} aria-label="International" onChange={(e) => edit(i, "international", e.target.checked)} />
                </td>
                <td>
                  <button type="button" className="admin__link" onClick={() => update(players.filter((_, j) => j !== i))}>
                    Retirer
                  </button>
                </td>
              </tr>
            ))}
            {players.length === 0 && (
              <tr>
                <td colSpan={6} className="left muted">
                  Aucun joueur.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        <button type="button" className="button" onClick={() => update([blank(), ...players])}>
          Ajouter un joueur
        </button>
        {club.roster_source === "backoffice" && (
          <button type="button" className="button" disabled={busy} onClick={revert}>
            {club.created ? "Effacer l'effectif" : "Revenir à l'effectif du jeu"}
          </button>
        )}
        <span className="admin__spacer" />
        <button type="button" className="button" disabled={!dirty || busy} onClick={() => setRoster(rosterOf(club))}>
          Annuler
        </button>
        <button type="button" className="button button--primary" disabled={!dirty || busy} onClick={save}>
          {busy ? "Enregistrement…" : "Enregistrer l'effectif"}
        </button>
      </div>
    </>
  );
}
