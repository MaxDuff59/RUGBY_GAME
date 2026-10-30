import { useEffect } from "react";
import { Route, Routes, useNavigate, useOutletContext } from "react-router-dom";

import { UNAUTHORIZED_EVENT } from "./api.js";
import Layout from "./components/Layout.jsx";
import Academy from "./pages/Academy.jsx";
import Admin from "./pages/Admin.jsx";
import Calendar from "./pages/Calendar.jsx";
import Club from "./pages/Club.jsx";
import Facilities from "./pages/Facilities.jsx";
import Finances from "./pages/Finances.jsx";
import FreeMatch from "./pages/FreeMatch.jsx";
import Hero from "./pages/Hero.jsx";
import Internationals from "./pages/Internationals.jsx";
import Journal from "./pages/Journal.jsx";
import Login from "./pages/Login.jsx";
import Match from "./pages/Match.jsx";
import Medical from "./pages/Medical.jsx";
import Player from "./pages/Player.jsx";
import Saves from "./pages/Saves.jsx";
import Selection from "./pages/Selection.jsx";
import Social from "./pages/Social.jsx";
import Squad from "./pages/Squad.jsx";
import SquadList from "./pages/SquadList.jsx";
import Staff from "./pages/Staff.jsx";
import Training from "./pages/Training.jsx";
import Honours from "./pages/Honours.jsx";
import StartCareer from "./pages/StartCareer.jsx";
import StartCompetition from "./pages/StartCompetition.jsx";
import Transfers from "./pages/Transfers.jsx";
import { leaveSlot } from "./save.js";

export default function App() {
  const navigate = useNavigate();
  // Session absente ou expirée (l'API a répondu 401) : retour à la connexion.
  useEffect(() => {
    const toLogin = () => {
      leaveSlot();
      navigate("/connexion", { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, toLogin);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, toLogin);
  }, [navigate]);

  return (
    <Routes>
      <Route path="/connexion" element={<Login />} />
      <Route path="/parties" element={<Saves />} />
      <Route path="/start" element={<StartCareer />} />
      <Route path="/match-libre" element={<FreeMatch />} />
      <Route path="/competition" element={<StartCompetition />} />
      <Route path="/backoffice" element={<Admin />} />
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="/journal" element={<Journal />} />
        <Route path="/reseaux" element={<Social />} />
        <Route path="/calendrier" element={<Calendar />} />
        <Route path="/international" element={<Internationals />} />
        <Route path="/liste" element={<SquadList />} />
        <Route path="/match" element={<Match />} />
        <Route path="/effectif" element={<Squad />} />
        <Route path="/joueurs/:playerId" element={<Player />} />
        <Route path="/medical" element={<Medical />} />
        <Route path="/formation" element={<Academy />} />
        <Route path="/staff" element={<Staff />} />
        <Route path="/entrainement" element={<Training />} />
        <Route path="/palmares" element={<Honours />} />
        <Route path="/transferts" element={<Transfers />} />
        <Route path="/infrastructures" element={<Facilities />} />
        <Route path="/finances" element={<Finances />} />
      </Route>
    </Routes>
  );
}

// L'accueil dépend de la carrière : le tableau de bord du club, celui du sélectionneur,
// ou celui du joueur incarné.
function Home() {
  const { career } = useOutletContext();
  if (career.kind === "player") return <Hero />;
  return career.kind === "nation" ? <Selection /> : <Club />;
}
