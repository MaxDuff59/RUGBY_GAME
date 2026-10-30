import { useCallback, useState } from "react";

import { api } from "../api.js";
import { formatInteger, formatShortDate } from "../format.js";
import { useApi } from "../hooks/useApi.js";

// Les voix du fil (engine/social.py), dans l'ordre des filtres.
const VOICES = {
  media: { label: "Médias", one: "Média" },
  journalist: { label: "Journalistes", one: "Journaliste" },
  fan: { label: "Supporters", one: "Supporter" },
  rival: { label: "Adversaires", one: "Supporter adverse" },
};
const FILTERS = [
  { key: "all", label: "Tout", keep: () => true },
  { key: "media", label: "Médias", keep: (post) => post.voice === "media" },
  { key: "journalist", label: "Journalistes", keep: (post) => post.voice === "journalist" },
  { key: "fans", label: "Supporters", keep: (post) => post.voice === "fan" || post.voice === "rival" },
];

const compact = (n) => (n >= 10000 ? `${formatInteger(Math.round(n / 1000))} k` : formatInteger(n));
const initials = (name) =>
  name
    .split(" · ")[0]
    .split(" ")
    .filter((word) => /^[A-ZÀ-Ý]/.test(word))
    .slice(0, 2)
    .map((word) => word[0])
    .join("");

// Carrière de joueur : ce que les réseaux disent du joueur incarné. À gauche son compte
// (abonnés, avis des supporters), à droite le fil : médias, journalistes, supporters de
// son club et de l'adversaire, du plus récent au plus ancien.
export default function Social() {
  const social = useApi(useCallback(api.getHeroSocial, []));
  const [filter, setFilter] = useState("all");

  if (social.loading) return <p className="status">Chargement…</p>;
  if (social.error) return <p className="status status--error">{social.error.message}</p>;

  const { name, handle, followers, gain, posts } = social.data;
  const fans = posts.filter((post) => post.voice === "fan");
  const praise = fans.filter((post) => post.tone === "praise").length;
  const critics = fans.filter((post) => post.tone === "critic").length;
  const shown = posts.filter(FILTERS.find((entry) => entry.key === filter).keep);

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Réseaux</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Ce que les médias, les journalistes et les supporters disent de toi.
          </p>
        </div>
      </header>

      <div className="social fill">
        <aside className="card card--padded social__profile">
          <div className="social__me">
            <span className="social__avatar social__avatar--me" aria-hidden="true">
              {initials(name)}
            </span>
            <div>
              <div className="social__name">{name}</div>
              <span className="muted">@{handle}</span>
            </div>
          </div>
          <div className="social__followers">
            <span className="social__count num">{compact(followers)}</span>
            <span className="muted">
              abonnés
              {gain > 0 && <span className="social__gain"> +{formatInteger(gain)} au dernier match</span>}
            </span>
          </div>
          <dl className="facts__list">
            <dt>Mentions</dt>
            <dd>{formatInteger(posts.length)}</dd>
            <dt>Supporters</dt>
            <dd>
              {fans.length
                ? `${Math.round((praise / fans.length) * 100)} % d'avis positifs`
                : "Ils attendent de te voir jouer"}
            </dd>
          </dl>
          {fans.length > 0 && (
            <span className="social__mood" aria-hidden="true">
              <span className="social__mood--praise" style={{ flexGrow: praise }} />
              <span className="social__mood--neutral" style={{ flexGrow: fans.length - praise - critics }} />
              <span className="social__mood--critic" style={{ flexGrow: critics }} />
            </span>
          )}
        </aside>

        <section className="section">
          <div className="section__head">
            <div className="chips" role="group" aria-label="Voix">
              {FILTERS.map((entry) => (
                <button
                  key={entry.key}
                  type="button"
                  className="chip"
                  aria-pressed={filter === entry.key}
                  onClick={() => setFilter(entry.key)}
                >
                  {entry.label}
                </button>
              ))}
            </div>
            <span className="muted">{formatInteger(shown.length)} publications</span>
          </div>
          <div className="card social__feed">
            <ul>
              {shown.map((post, index) => (
                <li key={`${post.date}-${post.time}-${index}`} className="social-post">
                  <span className={`social__avatar social__avatar--${post.voice}`} aria-hidden="true">
                    {initials(post.author)}
                  </span>
                  <div className="social-post__body">
                    <div className="social-post__head">
                      <strong>{post.author}</strong>
                      {post.verified && (
                        <span className="social-post__verified" title={`${VOICES[post.voice].one} vérifié`}>
                          ✓
                        </span>
                      )}
                      <span className="muted">
                        @{post.handle} · {formatShortDate(post.date)} {post.time}
                      </span>
                    </div>
                    <p className="social-post__text">{post.text}</p>
                    <div className="social-post__stats muted">
                      <span title="Partages">↻ {compact(post.reposts)}</span>
                      <span title="J'aime">♥ {compact(post.likes)}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
            {shown.length === 0 && <p className="table__note">Rien pour l'instant.</p>}
          </div>
        </section>
      </div>
    </>
  );
}
