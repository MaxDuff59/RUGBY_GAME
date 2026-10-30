import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { POSITIONS } from "../format.js";
import { chosenSlot } from "../save.js";
import { ActionError } from "./FullGame.jsx";

// Carrière de joueur (page de choix de carrière) : le joueur que l'on crée, son poste, et
// le club où il signe son premier contrat. `roles` : le choix entre les deux carrières ;
// `picker` : la liste des championnats et des clubs, dont le club choisi est `clubId`.
export default function StartHero({ roles, picker, clubId }) {
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [position, setPosition] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = firstName.trim() !== "" && lastName.trim() !== "" && position && clubId !== null && !submitting;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.startHero({ first_name: firstName.trim(), last_name: lastName.trim(), position, club_id: clubId });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  return (
    <form className="start start--career" onSubmit={handleSubmit}>
      <div>
        <p className="eyebrow">
          <Link to="/parties">Parties</Link> · Partie {chosenSlot()} · Nouvelle carrière
        </p>
        <h1 className="title">Crée ton joueur</h1>
        <p className="muted" style={{ margin: "8px 0 0" }}>
          18 ans, tout à prouver : tu commences loin des titulaires. Chaque match te rapporte de l'expérience, à placer
          dans tes attributs ; en direct, le jeu s'arrête sur tes actions.
        </p>
      </div>

      {roles}

      <div className="start-hero__names">
        <div className="field">
          <label htmlFor="hero-first">Prénom</label>
          <input
            id="hero-first"
            className="input"
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
            autoComplete="given-name"
            maxLength={50}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="hero-last">Nom</label>
          <input
            id="hero-last"
            className="input"
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
            autoComplete="family-name"
            maxLength={50}
            required
          />
        </div>
      </div>

      <div className="field field--wide">
        <span className="field__label">Poste</span>
        <div className="chips" role="group" aria-label="Poste">
          {Object.entries(POSITIONS).map(([key, { label }]) => (
            <button
              key={key}
              type="button"
              className="chip"
              aria-pressed={position === key}
              onClick={() => setPosition(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {picker}

      <ActionError error={error} />

      <div className="start__submit">
        <button type="submit" className="button button--primary" disabled={!canSubmit}>
          Signer mon premier contrat
        </button>
      </div>
    </form>
  );
}
