import { useCallback, useMemo, useState } from "react";

import { adminApi } from "../adminApi.js";
import { formatDay, formatDayTime } from "../adminFormat.js";
import { formatLongDate, formatSavedAt } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import ClubCrest from "./ClubCrest.jsx";
import { useConfirm } from "./ConfirmDialog.jsx";

// Backoffice, onglet Comptes : la liste (recherche, filtres par formule) et la fiche du
// compte choisi, avec ses parties, la formule à offrir ou retirer, et ses saisons gratuites.
const FILTERS = [
  { key: "all", label: "Tous", keep: () => true },
  { key: "full", label: "Version complète", keep: (u) => u.premium },
  { key: "paid", label: "Payée", keep: (u) => u.premium_source === "stripe" },
  { key: "free", label: "Gratuits", keep: (u) => !u.premium },
  { key: "done", label: "Au bout des saisons", keep: (u) => u.seasons_left === 0 },
];

export default function AdminAccounts() {
  const users = useApi(useCallback(adminApi.users, []));
  const phone = useMediaQuery(PHONE_QUERY);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(null);

  const shown = useMemo(() => {
    const { keep } = FILTERS.find((f) => f.key === filter);
    const needle = query.trim().toLowerCase();
    return (users.data ?? []).filter((u) => keep(u) && (!needle || u.email.includes(needle)));
  }, [users.data, query, filter]);

  // Une action sur la fiche met aussi la ligne de la liste à jour.
  const replace = (account) =>
    users.setData(users.data.map((u) => (u.id === account.id ? { ...u, ...account } : u)));

  if (users.loading) return <p className="status">Chargement des comptes…</p>;
  if (users.error) return <p className="status status--error">{users.error.message}</p>;

  const list = (
    <section className="card admin__panel">
      <div className="admin__tools">
        <input
          className="input"
          type="search"
          placeholder="Rechercher une adresse"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="chips chips--scroll" role="group" aria-label="Formule">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" className="chip chip--small" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
              {f.label} <span className="chip__count">{(users.data ?? []).filter(f.keep).length}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="admin__scroll">
        <table className="table admin__table">
          <thead>
            <tr>
              <th className="left">Compte</th>
              <th className="admin__wide">Inscrit</th>
              <th className="admin__wide">Dernière connexion</th>
              <th>Parties</th>
              <th>Saisons</th>
              <th>Formule</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((u) => (
              <tr
                key={u.id}
                className={`admin__row${selected === u.id ? " admin__row--on" : ""}`}
                onClick={() => setSelected(u.id)}
              >
                <td className="left admin__email">
                  {u.email}
                  {u.admin && <span className="admin__tag">admin</span>}
                </td>
                <td className="admin__wide">{formatDay(u.created_at)}</td>
                <td className="admin__wide">{formatDayTime(u.last_login_at)}</td>
                <td>{u.saves}</td>
                <td>{u.seasons_played}</td>
                <td>
                  <PlanBadge account={u} />
                </td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr>
                <td colSpan={6} className="left muted">
                  Aucun compte ne correspond.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );

  const detail = selected ? (
    <AccountCard key={selected} id={selected} onChange={replace} onBack={phone ? () => setSelected(null) : null} />
  ) : (
    <section className="card admin__panel admin__empty">
      <p className="muted">Choisis un compte pour voir ses parties et sa formule.</p>
    </section>
  );

  if (phone) return <div className="admin__split">{selected ? detail : list}</div>;
  return (
    <div className="admin__split">
      {list}
      {detail}
    </div>
  );
}

function AccountCard({ id, onChange, onBack }) {
  const account = useApi(useCallback(() => adminApi.user(id), [id]));
  const confirm = useConfirm();
  const [error, setError] = useState(null);

  async function run(call) {
    setError(null);
    try {
      const updated = await call();
      account.setData(updated);
      onChange(updated);
    } catch (err) {
      setError(err);
    }
  }

  if (account.loading) return <section className="card admin__panel admin__empty"><p className="muted">Chargement…</p></section>;
  if (account.error) return <section className="card admin__panel admin__empty"><p className="status--error">{account.error.message}</p></section>;
  const a = account.data;

  const grant = () =>
    confirm.ask({
      eyebrow: a.email,
      title: "Offrir la version complète",
      text: "Le compte passe en version complète sans paiement : parties et saisons sans limite.",
      confirmLabel: "Offrir",
      onConfirm: () => run(() => adminApi.setPremium(a.id, true)),
    });
  const revoke = () =>
    confirm.ask({
      eyebrow: a.email,
      title: "Retirer la version complète",
      text:
        a.premium_source === "stripe"
          ? "Ce compte a payé : retirer la formule ne le rembourse pas (à faire chez Stripe)."
          : "Le compte redevient gratuit : une partie, et les saisons qu'il lui reste.",
      confirmLabel: "Retirer",
      cautious: true,
      onConfirm: () => run(() => adminApi.setPremium(a.id, false)),
    });

  return (
    <section className="card admin__panel admin__detail">
      {confirm.dialog}
      <div className="admin__detail-head">
        {onBack && (
          <button type="button" className="admin__link" onClick={onBack}>
            ← Comptes
          </button>
        )}
        <p className="eyebrow">Compte n° {a.id}</p>
        <h2 className="admin__name admin__name--plain">{a.email}</h2>
        <p className="muted">
          Inscrit le {formatDay(a.created_at)} · dernière connexion {formatDayTime(a.last_login_at)}
        </p>
      </div>

      <div className="admin__scroll admin__detail-body">
        <div className="admin__block">
          <h3 className="eyebrow">Formule</h3>
          <dl className="admin__facts">
            <div>
              <dt>Formule</dt>
              <dd>
                <PlanBadge account={a} />
              </dd>
            </div>
            {a.premium && (
              <div>
                <dt>{a.premium_source === "stripe" ? "Payée le" : "Offerte le"}</dt>
                <dd>{formatDayTime(a.premium_at)}</dd>
              </div>
            )}
            {a.payment_ref && a.premium_source === "stripe" && (
              <div>
                <dt>Paiement Stripe</dt>
                <dd className="admin__mono">{a.payment_ref}</dd>
              </div>
            )}
            <div>
              <dt>Saisons commencées</dt>
              <dd>
                {a.seasons_played}
                {a.seasons_left !== null && <span className="muted"> · {a.seasons_left} gratuite{a.seasons_left > 1 ? "s" : ""} restante{a.seasons_left > 1 ? "s" : ""}</span>}
              </dd>
            </div>
          </dl>
          <div className="admin__actions">
            {a.premium ? (
              <button type="button" className="button" onClick={revoke}>
                Retirer la version complète
              </button>
            ) : (
              <button type="button" className="button button--primary" onClick={grant}>
                Offrir la version complète
              </button>
            )}
            {!a.premium && a.seasons_played > 0 && (
              <button type="button" className="button" onClick={() => run(() => adminApi.resetSeasons(a.id))}>
                Rendre les saisons gratuites
              </button>
            )}
          </div>
          {error && <p className="status--error">{error.message}</p>}
        </div>

        <div className="admin__block">
          <h3 className="eyebrow">Parties ({a.slots.length})</h3>
          {a.slots.length === 0 && <p className="muted">Aucune partie.</p>}
          <ul className="admin__slots">
            {a.slots.map((save) => (
              <li key={save.slot} className="admin__slot">
                <span className="eyebrow">Partie {save.slot}</span>
                <span className="with-crest admin__slot-club">
                  {save.club_name && !save.outdated && <ClubCrest name={save.club_name} size={24} />}
                  {save.outdated ? "Ancien format" : (save.club_name ?? "Carrière à choisir")}
                </span>
                {save.manager_name && (
                  <span>
                    {save.manager_name} · {save.league_name}
                  </span>
                )}
                {save.season_year && (
                  <span className="muted">
                    Saison {save.season_year}-{String(save.season_year + 1).slice(2)} · {formatLongDate(save.game_date)}
                  </span>
                )}
                <span className="muted">Sauvegardée {formatSavedAt(save.saved_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

// Formule d'un compte : « Complète » (payée ou offerte) ou « Gratuit ».
export function PlanBadge({ account }) {
  if (!account.premium) return <span className="admin__plan">Gratuit</span>;
  return (
    <span className="admin__plan admin__plan--full">
      {account.premium_source === "stripe" ? "Complète · payée" : "Complète · offerte"}
    </span>
  );
}
