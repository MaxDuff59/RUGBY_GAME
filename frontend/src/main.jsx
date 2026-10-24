import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.jsx";
import { loadClubOverrides } from "./clubs.js";
import "./styles.css";

// Couleurs des clubs retouchées depuis le backoffice, avant le premier affichage.
loadClubOverrides().then(() =>
  createRoot(document.getElementById("root")).render(
    <StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </StrictMode>,
  ),
);
