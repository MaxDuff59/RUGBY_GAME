import { useCallback, useEffect, useState } from "react";

import { api } from "../api.js";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import Level from "../components/Level.jsx";
import { STAFF_ROLES, formatMoney, formatStaffEffect } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { useSort } from "../hooks/useSort.js";

// Le staff : un poste par ligne à gauche ; à droite, le titulaire et les candidats du
// poste choisi. Sur téléphone, ce panneau s'ouvre sous le poste touché.
export default function Staff() {
  const { data, error, loading, setData } = useApi(useCallback(api.getStaff, []));
  // Téléphone : la liste arrive repliée, chaque poste s'ouvre au toucher.
  const [selectedRole, setSelectedRole] = useState(() =>
    window.matchMedia(PHONE_QUERY).matches ? null : Object.keys(STAFF_ROLES)[0],
  );
  const [actionError, setActionError] = useState(null);
  const confirm = useConfirm();
  const phone = useMediaQuery(PHONE_QUERY);
  // Le poste qu'on vient d'ouvrir remonte en haut de l'écran, candidats visibles dessous.
  useEffect(() => {
    if (phone && selectedRole) {
      document.getElementById(`staff-${selectedRole}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [phone, selectedRole]);
  const candidateSort = useSort(data?.candidates ?? [], { key: "level", dir: "desc" });

  async function act(call) {
    setActionError(null);
    try {
      setData(await call());
    } catch (err) {
      setActionError(err);
    }
  }

  function fire(slot) {
    const role = STAFF_ROLES[slot.role];
    confirm.ask({
      eyebrow: `Staff · ${role.label}`,
      title: `Licencier ${slot.member.name}`,
      text: `${role.scope}. Le poste reste vacant jusqu'à une nouvelle embauche, et l'équipe perd son apport dès le prochain match.`,
      rows: [
        { label: "Indemnité de licenciement", value: formatMoney(slot.severance), hint: "la moitié du salaire annuel" },
        { label: "Salaire libéré", value: formatMoney(slot.member.wage), hint: "par saison" },
        { label: "Trésorerie", from: formatMoney(data.balance), to: formatMoney(data.balance - slot.severance) },
      ],
      confirmLabel: "Licencier",
      onConfirm: async () => setData(await api.fireStaff(slot.member.id)),
    });
  }

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  // Poste replié sur téléphone (null) : à l'ordinateur, on revient au premier.
  const activeRole = selectedRole ?? (phone ? null : Object.keys(STAFF_ROLES)[0]);
  const selectedSlot = data.slots.find((slot) => slot.role === activeRole);
  const candidates = candidateSort.rows.filter((c) => c.role === activeRole);
  // Téléphone : un second toucher sur le poste ouvert le replie.
  const toggleRole = (role) => setSelectedRole((current) => (current === role ? null : role));

  // Le poste choisi : son titulaire (et le licenciement), puis les candidats.
  const sortKeys = [
    ["level", "Niveau", "desc"],
    ["wage", "Salaire", "asc"],
    ["name", "Nom", "asc"],
  ];
  const panel = selectedSlot && (
    <div className="staff-panel">
      <div className="staff-panel__holder">
        {selectedSlot.member ? (
          <>
            <div>
              <p className="staff-panel__label">Titulaire</p>
              <p className="staff-panel__name">{selectedSlot.member.name}</p>
              <span className="muted">
                {formatMoney(selectedSlot.member.wage)} par saison · indemnité {formatMoney(selectedSlot.severance)}
              </span>
            </div>
            <button type="button" className="button button--small button--danger" onClick={() => fire(selectedSlot)}>
              Licencier
            </button>
          </>
        ) : (
          <div>
            <p className="staff-panel__label">Poste vacant</p>
            <span className="muted">Embauche un candidat ci-dessous : l'équipe en profite dès le prochain match.</span>
          </div>
        )}
      </div>

      <div className="staff-panel__head">
        <p className="staff-panel__label">Candidats · {candidates.length}</p>
        <div className="segmented segmented--sm" role="group" aria-label="Trier les candidats">
          {sortKeys.map(([key, label, first]) => (
            <button
              key={key}
              type="button"
              aria-pressed={candidateSort.sort?.key === key}
              onClick={() => candidateSort.toggle(key, first)}
            >
              {label}
              {candidateSort.sort?.key === key && (candidateSort.sort.dir === "asc" ? " ↑" : " ↓")}
            </button>
          ))}
        </div>
      </div>

      <ul className="staff-candidates">
        {candidates.map((candidate) => (
          <li key={candidate.id} className="staff-candidate">
            <span className="staff-candidate__main">
              <span className="staff-candidate__name">{candidate.name}</span>
              <span className="staff-candidate__level">
                <Level value={candidate.level} />
                <Effect role={candidate.role} value={candidate.effect} />
              </span>
            </span>
            <span className="num staff-candidate__wage">{formatMoney(candidate.wage)}</span>
            <button
              type="button"
              className="button button--small button--primary"
              disabled={selectedSlot.member !== null}
              title={selectedSlot.member ? "Licencie d'abord le titulaire" : undefined}
              onClick={() => act(() => api.hireStaff(candidate.id))}
            >
              Embaucher
            </button>
          </li>
        ))}
        {candidates.length === 0 && <li className="muted staff-candidate">Personne de disponible à ce poste.</li>}
      </ul>
      {selectedSlot.member && candidates.length > 0 && (
        <p className="staff-note muted">Le poste est pourvu : licencie le titulaire pour embaucher.</p>
      )}
    </div>
  );

  return (
    <>
      <header className="page-head">
        <h1 className="title">Staff</h1>
        <div className="stat">
          <span className="big-num">{formatMoney(data.balance)}</span>
          <span className="muted">trésorerie</span>
        </div>
      </header>

      {actionError && <p className="status--error">{actionError.message}</p>}
      {confirm.dialog}

      {phone ? (
        <section className="section">
          <h2 className="eyebrow">Ton staff · touche un poste pour ses candidats</h2>
          <ul className="staff-list card">
            {data.slots.map((slot) => (
              <li key={slot.role} id={`staff-${slot.role}`}>
                <SlotRow slot={slot} selected={slot.role === activeRole} onSelect={toggleRole} />
                {slot.role === activeRole && panel}
              </li>
            ))}
          </ul>
          <p className="staff-note muted">{NOTE}</p>
        </section>
      ) : (
        <div className="two-col fill staff-cols">
          <section className="section">
            <h2 className="eyebrow">Ton staff</h2>
            <div className="card staff-scroll">
              <ul className="staff-list">
                {data.slots.map((slot) => (
                  <li key={slot.role}>
                    <SlotRow slot={slot} selected={slot.role === activeRole} onSelect={setSelectedRole} />
                  </li>
                ))}
              </ul>
              <p className="staff-note muted">{NOTE}</p>
            </div>
          </section>
          <section className="section">
            <h2 className="eyebrow">{STAFF_ROLES[activeRole].label}</h2>
            <div className="card staff-scroll">{panel}</div>
          </section>
        </div>
      )}
    </>
  );
}

const NOTE =
  "Salaires par saison. Un entraîneur de 3 étoiles ne change rien au jeu ; un poste vacant coûte plus cher " +
  "qu'un entraîneur médiocre. Licencier coûte la moitié du salaire annuel.";

// Un poste du staff : intitulé et rôle, titulaire et salaire, niveau et effet.
function SlotRow({ slot, selected, onSelect }) {
  const role = STAFF_ROLES[slot.role];
  return (
    <button
      type="button"
      className={`staff-slot${slot.member ? "" : " staff-slot--vacant"}`}
      aria-pressed={selected}
      onClick={() => onSelect(slot.role)}
    >
      <span className="staff-slot__main">
        <span className="staff-slot__role">{role.label}</span>
        <span className="staff-slot__scope">{role.scope}</span>
        <span className="staff-slot__member">
          {slot.member ? (
            <>
              {slot.member.name} <span className="muted">· {formatMoney(slot.member.wage)}</span>
            </>
          ) : (
            <span className="staff-slot__vacant">Poste vacant · à pourvoir</span>
          )}
        </span>
      </span>
      <span className="staff-slot__level">
        {slot.member && <Level value={slot.member.level} />}
        <Effect role={slot.role} value={slot.effect} />
      </span>
      <span className="staff-slot__chevron" aria-hidden="true">
        ›
      </span>
    </button>
  );
}

// Ce que le poste apporte au club : en vert quand il aide, en rouge quand il coûte.
function Effect({ role, value }) {
  // Kiné et médecin réduisent une durée ou un risque : la baisse est une bonne nouvelle.
  const good = role === "PHYSIO" || role === "DOCTOR" ? -value : value;
  const tone = good > 0.0005 ? " staff-effect--up" : good < -0.0005 ? " staff-effect--down" : "";
  return <div className={`staff-effect${tone}`}>{formatStaffEffect(role, value)}</div>;
}
