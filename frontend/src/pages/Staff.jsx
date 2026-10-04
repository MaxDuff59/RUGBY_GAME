import { useCallback, useState } from "react";

import { api } from "../api.js";
import Level from "../components/Level.jsx";
import SortHeader from "../components/SortHeader.jsx";
import { STAFF_ROLES, formatMoney } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";

// Le staff : un poste par ligne à gauche ; à droite, les candidats du poste choisi.
export default function Staff() {
  const { data, error, loading, setData } = useApi(useCallback(api.getStaff, []));
  const [selectedRole, setSelectedRole] = useState(Object.keys(STAFF_ROLES)[0]);
  const [actionError, setActionError] = useState(null);
  const candidateSort = useSort(data?.candidates ?? [], { key: "level", dir: "desc" });

  async function act(call) {
    setActionError(null);
    try {
      setData(await call());
    } catch (err) {
      setActionError(err);
    }
  }

  if (loading) return <p className="status">Chargement…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const selectedSlot = data.slots.find((slot) => slot.role === selectedRole);
  const candidates = candidateSort.rows.filter((c) => c.role === selectedRole);
  const header = (key, label, first = "desc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={candidateSort.sort} onToggle={candidateSort.toggle} first={first} left={left} />
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

      <div className="two-col">
        <section className="section">
          <h2 className="eyebrow">Ton staff</h2>
          <div className="card table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col" className="left">Poste</th>
                  <th scope="col" className="left">Titulaire</th>
                  <th scope="col" className="left">Niveau</th>
                  <th scope="col">Salaire</th>
                  <th scope="col"></th>
                </tr>
              </thead>
              <tbody>
                {data.slots.map((slot) => (
                  <tr
                    key={slot.role}
                    className={slot.role === selectedRole ? "table__row--selected" : "table__row--clickable"}
                    onClick={() => setSelectedRole(slot.role)}
                  >
                    <td className="left">
                      <div style={{ fontWeight: 600 }}>{STAFF_ROLES[slot.role].label}</div>
                      <div className="muted">{STAFF_ROLES[slot.role].scope}</div>
                    </td>
                    <td className="left">{slot.member ? slot.member.name : <span className="muted">Poste vacant</span>}</td>
                    <td className="left">{slot.member && <Level value={slot.member.level} />}</td>
                    <td>{slot.member && formatMoney(slot.member.wage)}</td>
                    <td>
                      {slot.member && (
                        <button
                          type="button"
                          className="button button--small"
                          onClick={(event) => {
                            event.stopPropagation();
                            if (window.confirm(`Licencier ${slot.member.name} ? Indemnité : ${formatMoney(slot.severance)}.`)) {
                              act(() => api.fireStaff(slot.member.id));
                            }
                          }}
                        >
                          Licencier
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="table__note">
              Salaires par saison. Licencier coûte la moitié du salaire annuel. Clique sur un poste
              pour voir les candidats.
            </p>
          </div>
        </section>

        <section className="section">
          <h2 className="eyebrow">Candidats · {STAFF_ROLES[selectedRole].label}</h2>
          <div className="card table-wrap">
            <table className="table">
              <thead>
                <tr>
                  {header("name", "Nom", "asc", true)}
                  {header("level", "Niveau", "desc", true)}
                  {header("wage", "Salaire")}
                  <th scope="col"></th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((candidate) => (
                  <tr key={candidate.id}>
                    <td className="left" style={{ fontWeight: 600 }}>{candidate.name}</td>
                    <td className="left"><Level value={candidate.level} /></td>
                    <td>{formatMoney(candidate.wage)}</td>
                    <td>
                      <button
                        type="button"
                        className="button button--small button--primary"
                        disabled={selectedSlot.member !== null}
                        title={selectedSlot.member ? "Licencie d'abord le titulaire" : undefined}
                        onClick={() => act(() => api.hireStaff(candidate.id))}
                      >
                        Embaucher
                      </button>
                    </td>
                  </tr>
                ))}
                {candidates.length === 0 && (
                  <tr>
                    <td colSpan={4} className="left muted">Personne de disponible à ce poste.</td>
                  </tr>
                )}
              </tbody>
            </table>
            <p className="table__note">
              {selectedSlot.member
                ? "Le poste est pourvu : licencie le titulaire pour embaucher."
                : "Le poste est vacant : tu peux embaucher."}
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
