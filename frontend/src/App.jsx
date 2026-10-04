import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout.jsx";
import Club from "./pages/Club.jsx";
import Squad from "./pages/Squad.jsx";
import StartCareer from "./pages/StartCareer.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/start" element={<StartCareer />} />
      <Route element={<Layout />}>
        <Route index element={<Club />} />
        <Route path="/effectif" element={<Squad />} />
      </Route>
    </Routes>
  );
}
