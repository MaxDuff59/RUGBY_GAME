import { useCallback, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useApi } from "../hooks/useApi.js";

// Écran de connexion : une adresse e-mail et un mot de passe, pour se connecter ou
// créer son compte. Les parties sont rangées par compte ; une fois connecté, on
// arrive sur ses parties.
export default function Login() {
  const navigate = useNavigate();
  const me = useApi(useCallback(api.me, []));
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Déjà connecté : directement aux parties.
  if (me.data) return <Navigate to="/parties" replace />;
  if (me.loading) return <p className="status">Chargement…</p>;
  if (me.error && me.error.status !== 401) {
    return (
      <p className="status status--error">
        Impossible de joindre l'API ({me.error.message}). Lance-la avec
        <code> uv run uvicorn api.main:app --reload</code> dans backend/.
      </p>
    );
  }

  const registering = mode === "register";
  const canSubmit = email.trim() !== "" && password.length >= (registering ? 8 : 1) && !submitting;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await (registering ? api.register : api.login)(email.trim(), password);
      navigate("/parties", { replace: true });
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  return (
    <div className="start login">
      <header className="page-head">
        <div>
          <p className="eyebrow">Rugby Manager</p>
          <h1 className="title">{registering ? "Créer un compte" : "Connexion"}</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            {registering
              ? "Tes parties te suivent d'un appareil à l'autre."
              : "Retrouve tes parties, où que tu joues."}
          </p>
        </div>
      </header>

      <form className="card card--padded login__form" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="email">Adresse e-mail</label>
          <input
            id="email"
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoFocus
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Mot de passe</label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete={registering ? "new-password" : "current-password"}
            minLength={registering ? 8 : undefined}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {registering && <span className="muted">8 caractères minimum.</span>}
        </div>

        {error && <p className="status--error login__error">{error.message}</p>}

        <div className="login__actions">
          <button type="submit" className="button button--primary" disabled={!canSubmit}>
            {submitting ? "Un instant…" : registering ? "Créer mon compte" : "Se connecter"}
          </button>
          <button
            type="button"
            className="button"
            disabled={submitting}
            onClick={() => {
              setMode(registering ? "login" : "register");
              setError(null);
            }}
          >
            {registering ? "J'ai déjà un compte" : "Créer un compte"}
          </button>
        </div>
      </form>
    </div>
  );
}
