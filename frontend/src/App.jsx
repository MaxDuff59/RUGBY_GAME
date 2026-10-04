import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout.jsx";
import Calendar from "./pages/Calendar.jsx";
import Club from "./pages/Club.jsx";
import Facilities from "./pages/Facilities.jsx";
import Finances from "./pages/Finances.jsx";
import Squad from "./pages/Squad.jsx";
import Staff from "./pages/Staff.jsx";
import StartCareer from "./pages/StartCareer.jsx";
import Transfers from "./pages/Transfers.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/start" element={<StartCareer />} />
      <Route element={<Layout />}>
        <Route index element={<Club />} />
        <Route path="/calendrier" element={<Calendar />} />
        <Route path="/effectif" element={<Squad />} />
        <Route path="/staff" element={<Staff />} />
        <Route path="/transferts" element={<Transfers />} />
        <Route path="/infrastructures" element={<Facilities />} />
        <Route path="/finances" element={<Finances />} />
      </Route>
    </Routes>
  );
}
