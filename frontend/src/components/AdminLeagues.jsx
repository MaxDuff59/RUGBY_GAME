import { useCallback, useState } from "react";

import { adminApi } from "../adminApi.js";
import { NATIONALITIES } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import ClubCrest from "./ClubCrest.jsx";

// Backoffice, onglet Championnats : ceux du jeu (seuls leurs clubs changent, depuis l'onglet
// Clubs) et ceux créés ici, avec leur formule et leur calendrier. Un championnat sous son
// minimum de clubs reste hors des nouvelles parties ; archivé, il en sort mais les parties
// qui le jouent le gardent.

export const PLAYOFFS = {
  top4: "4 qualifiés : demies, finale",
  top6: "6 qualifiés : barrages, demies, finale",
  top8: "8 qualifiés : quarts, demies, finale",
  super6: "6 qualifiés façon Super Rugby",
};

const blank = {
  name: "",
  short_name: "",
  country: "",
  nation: null,
  playoffs: "top6",
  neutral_final: true,
  calendar: "prod2",
  prize_factor: 0.2,
  archived: false,
};

const formOf = (lg) => ({
  name: lg.name,
  short_name: lg.short_name,
  country: lg.country,
  nation: lg.nation,
  playoffs: lg.playoffs,
  neutral_final: lg.neutral_final,
  calendar: lg.calendar,
  prize_factor: lg.prize_factor,
  archived: lg.archived,
});

export default function AdminLeagues() {
  const leagues = useApi(useCallback(adminApi.leagues, []));
  const clubs = useApi(useCallback(adminApi.clubs, []));
  const phone = useMediaQuery(PHONE_QUERY);
  // Code du championnat ouvert, "new" pour en créer un, null : aucun.
  const [selected, setSelected] = useState(null);

  if (leagues.loading) return <p className="status">Chargement des championnats…</p>;
  if (leagues.error) return <p className="status status--error">{leagues.error.message}</p>;
  const builtIn = leagues.data.filter((lg) => !lg.custom);
  const current = leagues.data.find((lg) => lg.code === selected);

  const list = (
    <section className="card admin__panel">
      <div className="admin__panel-head">
        <h2 className="eyebrow">Championnats</h2>
        <button type="button" className="button button--primary button--small" onClick={() => setSelected("new")}>
          Nouveau championnat
        </button>
      </div>
      <div className="admin__scroll">
        <table className="table admin__table">
          <thead>
            <tr>
              <th className="left">Championnat</th>
              <th>Clubs</th>
              <th className="left admin__wide">Formule</th>
              <th className="left">Dans les nouvelles parties</th>
            </tr>
          </thead>
          <tbody>
            {leagues.data.map((lg) => (
              <tr
                key={lg.code}
                className={`admin__row${selected === lg.code ? " admin__row--on" : ""}`}
                onClick={() => setSelected(lg.code)}
              >
                <td className="left">
                  <span className="admin__crests">
                    {(clubs.data ?? [])
                      .filter((c) => c.league === lg.code)
                      .slice(0, 3)
                      .map((c) => (
                        <ClubCrest key={c.name} name={c.name} size={18} />
                      ))}
                  </span>
                  {lg.name}
                  {lg.custom && <span className="admin__tag">créé</span>}
                </td>
                <td>
                  {lg.clubs}/{lg.max_clubs}
                </td>
                <td className="left admin__wide">{PLAYOFFS[lg.playoffs]}</td>
                <td className="left">
                  <LeagueStatus league={lg} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );

  let detail;
  if (selected === "new") {
    detail = (
      <LeagueForm
        key="new"
        builtIn={builtIn}
        onBack={phone ? () => setSelected(null) : null}
        onSaved={(list, form) => {
          leagues.setData(list);
          setSelected(list.find((lg) => lg.custom && lg.name === form.name)?.code ?? null);
        }}
      />
    );
  } else if (current?.custom) {
    detail = (
      <LeagueForm
        key={current.code}
        league={current}
        builtIn={builtIn}
        onBack={phone ? () => setSelected(null) : null}
        onSaved={(list) => leagues.setData(list)}
      />
    );
  } else if (current) {
    detail = <BuiltInLeague league={current} onBack={phone ? () => setSelected(null) : null} />;
  } else {
    detail = (
      <section className="card admin__panel admin__empty">
        <p className="muted">Choisis un championnat, ou crée-en un. Ses clubs se placent depuis l'onglet Clubs.</p>
      </section>
    );
  }

  if (phone) return <div className="admin__split">{selected ? detail : list}</div>;
  return (
    <div className="admin__split">
      {list}
      {detail}
    </div>
  );
}

function LeagueStatus({ league }) {
  if (league.archived) return <span className="admin__warn">Archivé</span>;
  if (!league.ready) return <span className="admin__warn">Incomplet : {league.min_clubs} clubs min.</span>;
  return <span className="admin__plan admin__plan--full">Oui</span>;
}

function Roles({ league }) {
  const roles = [];
  if (league.europe) roles.push("Ses huit premiers jouent la Coupe d'Europe, les suivants le Challenge européen.");
  if (league.promotion === "up") roles.push("Son champion monte en Top 14.");
  if (league.promotion === "down") roles.push("Son dernier descend en Pro D2.");
  if (!roles.length) return null;
  return (
    <ul className="admin__roles">
      {roles.map((role) => (
        <li key={role}>{role}</li>
      ))}
    </ul>
  );
}

function BuiltInLeague({ league, onBack }) {
  return (
    <section className="card admin__panel admin__detail">
      <div className="admin__detail-head">
        {onBack && (
          <button type="button" className="admin__link" onClick={onBack}>
            ← Championnats
          </button>
        )}
        <p className="eyebrow">Championnat du jeu · {league.country}</p>
        <h2 className="admin__name">{league.name}</h2>
        <p className="muted">
          Sa formule et son calendrier sont ceux du jeu. Ses clubs changent depuis l'onglet Clubs (champ « Championnat »
          de la fiche), pour les nouvelles parties.
        </p>
      </div>
      <div className="admin__scroll admin__detail-body">
        <div className="admin__block">
          <dl className="admin__facts">
            <div>
              <dt>Clubs</dt>
              <dd>
                {league.clubs} (de {league.min_clubs} à {league.max_clubs})
              </dd>
            </div>
            <div>
              <dt>Phases finales</dt>
              <dd>{PLAYOFFS[league.playoffs]}</dd>
            </div>
            <div>
              <dt>Finale</dt>
              <dd>{league.neutral_final ? "Terrain neutre" : "Chez le mieux classé"}</dd>
            </div>
            <div>
              <dt>Nouvelles parties</dt>
              <dd>
                <LeagueStatus league={league} />
              </dd>
            </div>
          </dl>
          <Roles league={league} />
        </div>
      </div>
    </section>
  );
}

function LeagueForm({ league, builtIn, onSaved, onBack }) {
  const [form, setForm] = useState(() => (league ? formOf(league) : blank));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));
  const dirty = !league || JSON.stringify(form) !== JSON.stringify(formOf(league));

  async function save(event, changes = {}) {
    event?.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...form, ...changes, short_name: form.short_name || form.name, prize_factor: Number(form.prize_factor) };
    try {
      const list = league ? await adminApi.saveLeague(league.code, body) : await adminApi.createLeague(body);
      onSaved(list, body);
      if (league) setForm(formOf(list.find((lg) => lg.code === league.code)));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card admin__panel admin__detail" onSubmit={save}>
      <div className="admin__detail-head">
        {onBack && (
          <button type="button" className="admin__link" onClick={onBack}>
            ← Championnats
          </button>
        )}
        <p className="eyebrow">{league ? `Championnat créé · ${league.code}` : "Nouveau championnat"}</p>
        <h2 className="admin__name">{form.name || "Sans nom"}</h2>
        {league ? (
          <p className="muted">
            {league.clubs} club{league.clubs > 1 ? "s" : ""} · <LeagueStatus league={league} /> · ses clubs se placent depuis
            l'onglet Clubs.
          </p>
        ) : (
          <p className="muted">Il naît vide : place-y des clubs (ou crées-en) depuis l'onglet Clubs.</p>
        )}
      </div>
      <div className="admin__scroll admin__detail-body">
        <div className="admin__block">
          <div className="admin__fields">
            <label className="field admin__field">
              <span className="field__label">Nom</span>
              <input className="input" value={form.name} required minLength={2} maxLength={60} onChange={(e) => set("name", e.target.value)} />
            </label>
            <label className="field admin__field">
              <span className="field__label">Nom court</span>
              <input className="input" value={form.short_name} maxLength={30} placeholder={form.name} onChange={(e) => set("short_name", e.target.value)} />
              <span className="muted admin__hint">Dans les classements et les fiches</span>
            </label>
            <label className="field admin__field">
              <span className="field__label">Pays</span>
              <input className="input" value={form.country} maxLength={60} onChange={(e) => set("country", e.target.value)} />
            </label>
            <label className="field admin__field">
              <span className="field__label">Nationalité des joueurs inventés</span>
              <select className="input" value={form.nation ?? ""} onChange={(e) => set("nation", e.target.value || null)}>
                <option value="">Aucune</option>
                {Object.entries(NATIONALITIES).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
              <span className="muted admin__hint">Pour ses clubs créés sans pays</span>
            </label>
            <label className="field admin__field">
              <span className="field__label">Phases finales</span>
              <select className="input" value={form.playoffs} onChange={(e) => set("playoffs", e.target.value)}>
                {Object.entries(PLAYOFFS).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field admin__field">
              <span className="field__label">Calendrier</span>
              <select className="input" value={form.calendar} onChange={(e) => set("calendar", e.target.value)}>
                {builtIn.map((lg) => (
                  <option key={lg.code} value={lg.code}>
                    Comme le {lg.short_name}
                  </option>
                ))}
              </select>
              <span className="muted admin__hint">Date de reprise et trêves</span>
            </label>
            <label className="field admin__field">
              <span className="field__label">Primes des phases finales · {Math.round(Number(form.prize_factor) * 100)} %</span>
              <input type="range" min={0} max={1} step={0.05} value={form.prize_factor} onChange={(e) => set("prize_factor", e.target.value)} />
              <span className="muted admin__hint">Par rapport à celles du Top 14</span>
            </label>
            <label className="admin__check admin__field">
              <input type="checkbox" checked={form.neutral_final} onChange={(e) => set("neutral_final", e.target.checked)} />
              Finale sur terrain neutre
            </label>
          </div>
          <p className="muted admin__note">
            Les championnats créés ne montent ni ne descendent, et ne jouent pas la Coupe d'Europe.
          </p>
        </div>
      </div>
      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        {league && (
          <button type="button" className="button" disabled={busy} onClick={() => save(null, { archived: !league.archived })}>
            {league.archived ? "Désarchiver" : "Archiver"}
          </button>
        )}
        <span className="admin__spacer" />
        <button type="submit" className="button button--primary" disabled={busy || !dirty}>
          {busy ? "Enregistrement…" : league ? "Enregistrer" : "Créer le championnat"}
        </button>
      </div>
    </form>
  );
}
