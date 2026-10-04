import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout.jsx";
import StartCareer from "./pages/StartCareer.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/start" element={<StartCareer />} />
      <Route element={<Layout />}>
        <Route index element={<p className="status">Les pages arrivent.</p>} />
      </Route>
    </Routes>
  );
}
