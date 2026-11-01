import { useCallback, useEffect, useMemo, useState } from "react";

import { adminApi } from "../adminApi.js";
import { formatDay, formatDayTime } from "../adminFormat.js";
import { useApi } from "../hooks/useApi.js";
import { useConfirm } from "./ConfirmDialog.jsx";

// Backoffice, onglet Relances : un groupe de comptes sans jeu complet (au bout des saisons
// gratuites, en cours d'essai, jamais joué), les destinataires à cocher, et le message,
// modifiable, avec son aperçu, un test envoyé à soi-même et l'envoi. Le brouillon de chaque
// groupe reste dans le navigateur.
const draftKey = (segment) => `relances:${segment}`;

function loadDraft(segment) {
  try {
    const saved = JSON.parse(localStorage.getItem(draftKey(segment.key)));
    if (saved?.subject && saved?.body) return { subject: saved.subject, body: saved.body, cta: saved.cta ?? "" };
  } catch {
    // Brouillon illisible : le message proposé.
  }
  return { subject: segment.subject, body: segment.body, cta: segment.cta };
}

export default function AdminMailing() {
  const mailing = useApi(useCallback(adminApi.mailing, []));
  const [key, setKey] = useState(null);
  const segments = mailing.data?.segments ?? [];
  const segment = segments.find((s) => s.key === key) ?? segments[0];

  if (!mailing.data && mailing.loading) return <p className="status">Chargement…</p>;
  if (mailing.error) return <p className="status status--error">{mailing.error.message}</p>;

  return (
    <Campaign
      key={segment.key}
      data={mailing.data}
      segment={segment}
      onSegment={setKey}
      // Rechargé sans repasser par « Chargement… » : la fiche et son message restent.
      onSent={async () => mailing.setData(await adminApi.mailing())}
    />
  );
}

function Campaign({ data, segment, onSegment, onSent }) {
  const confirm = useConfirm();
  const [message, setMessage] = useState(() => loadDraft(segment));
  const [picked, setPicked] = useState(() => new Set(segment.recipients.map((r) => r.id)));
  const [view, setView] = useState("edit");
  const [preview, setPreview] = useState(null);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const full = { segment: segment.key, ...message };
  const edited = message.subject !== segment.subject || message.body !== segment.body || message.cta !== segment.cta;
  const ready = message.subject.trim() && message.body.trim();
  const chosen = segment.recipients.filter((r) => picked.has(r.id));
  const allPicked = chosen.length === segment.recipients.length && chosen.length > 0;

  useEffect(() => {
    if (edited) localStorage.setItem(draftKey(segment.key), JSON.stringify(message));
    else localStorage.removeItem(draftKey(segment.key));
  }, [edited, message, segment.key]);

  // L'aperçu se refait quand on l'ouvre, et à chaque retouche pendant qu'il est ouvert.
  useEffect(() => {
    if (view !== "preview" || !ready) return undefined;
    let live = true;
    const timer = setTimeout(() => {
      adminApi
        .mailPreview({ segment: segment.key, ...message })
        .then((out) => live && setPreview(out))
        .catch((err) => live && setError(err));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [view, ready, message, segment.key]);

  const set = (field, value) => setMessage((m) => ({ ...m, [field]: value }));
  const toggle = (id) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  async function sendTest() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const out = await adminApi.mailTest(full);
      setNotice(`Test envoyé à ${out.to[0]}.`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const send = () =>
    confirm.ask({
      eyebrow: segment.label,
      title: `Envoyer à ${chosen.length} compte${chosen.length > 1 ? "s" : ""}`,
      text: `« ${message.subject} » part tout de suite. Ces comptes ne seront plus relancés pendant ${data.cooldown_days} jours.`,
      confirmLabel: "Envoyer",
      cautious: true,
      onConfirm: async () => {
        setError(null);
        const out = await adminApi.mailSend(full, chosen.map((r) => r.id));
        setNotice(
          out.error
            ? `${out.sent} mail${out.sent > 1 ? "s" : ""} parti${out.sent > 1 ? "s" : ""}, puis : ${out.error}`
            : `${out.sent} mail${out.sent > 1 ? "s" : ""} envoyé${out.sent > 1 ? "s" : ""}.`,
        );
        await onSent();
      },
    });

  const recipients = (
    <section className="card admin__panel">
      <div className="admin__tools">
        <div className="chips chips--scroll" role="group" aria-label="Groupe">
          {data.segments.map((s) => (
            <button key={s.key} type="button" className="chip chip--small" aria-pressed={s.key === segment.key} onClick={() => onSegment(s.key)}>
              {s.label} <span className="chip__count">{s.recipients.length}</span>
            </button>
          ))}
        </div>
        <p className="muted admin__note-line">{segment.description}</p>
      </div>
      <div className="admin__scroll">
        <table className="table admin__table">
          <thead>
            <tr>
              <th className="left admin__pick">
                <input
                  type="checkbox"
                  aria-label="Tout cocher"
                  checked={allPicked}
                  disabled={!segment.recipients.length}
                  onChange={() => setPicked(allPicked ? new Set() : new Set(segment.recipients.map((r) => r.id)))}
                />
              </th>
              <th className="left">Compte</th>
              <th className="admin__wide">Inscrit</th>
              <th>Saisons</th>
              <th className="admin__wide">Dernier mail</th>
            </tr>
          </thead>
          <tbody>
            {segment.recipients.map((r) => (
              <tr key={r.id} className="admin__row" onClick={() => toggle(r.id)}>
                <td className="left admin__pick">
                  <input type="checkbox" aria-label={r.email} checked={picked.has(r.id)} onChange={() => toggle(r.id)} onClick={(e) => e.stopPropagation()} />
                </td>
                <td className="left admin__email">{r.email}</td>
                <td className="admin__wide">{formatDay(r.created_at)}</td>
                <td>{r.seasons_played}</td>
                <td className="admin__wide">{formatDay(r.last_mail_at)}</td>
              </tr>
            ))}
            {segment.recipients.length === 0 && (
              <tr>
                <td colSpan={5} className="left muted">
                  Personne à relancer dans ce groupe.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <div className="admin__mail-history">
          <h3 className="eyebrow">Derniers envois</h3>
          {data.history.length === 0 && <p className="muted">Aucune relance envoyée.</p>}
          <ul>
            {data.history.map((h) => (
              <li key={h.batch}>
                <span>{h.subject}</span>
                <span className="muted">
                  {formatDayTime(h.sent_at)} · {data.segments.find((s) => s.key === h.segment)?.label ?? h.segment} · {h.count} compte{h.count > 1 ? "s" : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="muted admin__mail-foot">
        {segment.resting > 0 && `${segment.resting} relancé${segment.resting > 1 ? "s" : ""} il y a moins de ${data.cooldown_days} jours, laissé${segment.resting > 1 ? "s" : ""} de côté · `}
        {data.opted_out} désinscrit{data.opted_out > 1 ? "s" : ""} · comptes complets et invités exclus
      </p>
    </section>
  );

  const editor = (
    <section className="card admin__panel">
      {confirm.dialog}
      <div className="admin__panel-head">
        <h2 className="eyebrow">Message</h2>
        <div className="chips" role="group" aria-label="Vue">
          <button type="button" className="chip chip--small" aria-pressed={view === "edit"} onClick={() => setView("edit")}>
            Rédiger
          </button>
          <button type="button" className="chip chip--small" aria-pressed={view === "preview"} onClick={() => setView("preview")}>
            Aperçu
          </button>
        </div>
      </div>

      {!data.configured && (
        <p className="admin__mail-warn">
          L'envoi n'est pas configuré : ajoute <code>RESEND_API_KEY</code> et <code>MAIL_FROM</code> aux variables du serveur.
        </p>
      )}

      {view === "edit" ? (
        <div className="admin__scroll admin__mail-form">
          <label className="field admin__field">
            <span className="field__label">Objet</span>
            <input className="input" value={message.subject} maxLength={200} onChange={(e) => set("subject", e.target.value)} />
          </label>
          <label className="field admin__field admin__mail-body">
            <span className="field__label">Texte</span>
            <textarea className="input admin__textarea" value={message.body} maxLength={5000} onChange={(e) => set("body", e.target.value)} />
            <span className="muted">
              Une ligne vide sépare les paragraphes. Remplacés pour chaque compte : {data.placeholders.join(", ")}.
            </span>
          </label>
          <label className="field admin__field">
            <span className="field__label">Bouton</span>
            <input className="input" value={message.cta} maxLength={60} placeholder="Sans bouton" onChange={(e) => set("cta", e.target.value)} />
            <span className="muted">Mène à l'écran des parties. Le lien de désinscription s'ajoute de lui-même.</span>
          </label>
        </div>
      ) : (
        <div className="admin__mail-preview">
          {preview ? (
            <>
              <p className="muted">
                <strong>{preview.subject}</strong> · exemple rempli pour {preview.example}
                {data.sender && ` · de ${data.sender}`}
              </p>
              <iframe title="Aperçu du mail" srcDoc={preview.html} sandbox="" />
            </>
          ) : (
            <p className="muted">Préparation de l'aperçu…</p>
          )}
        </div>
      )}

      <div className="admin__footer">
        {error && <p className="status--error">{error.message}</p>}
        {!error && notice && <p className="muted admin__mail-notice">{notice}</p>}
        {edited && (
          <button type="button" className="button" onClick={() => setMessage({ subject: segment.subject, body: segment.body, cta: segment.cta })}>
            Message proposé
          </button>
        )}
        <button type="button" className="button" disabled={!data.configured || !ready || busy} onClick={sendTest}>
          M'envoyer un test
        </button>
        <button type="button" className="button button--primary" disabled={!data.configured || !ready || busy || !chosen.length} onClick={send}>
          Envoyer à {chosen.length} compte{chosen.length > 1 ? "s" : ""}
        </button>
      </div>
    </section>
  );

  return (
    <div className="admin__split admin__split--mail">
      {recipients}
      {editor}
    </div>
  );
}
