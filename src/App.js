import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Home from "./Home";
import Formulaire from "./formulaire";
import Dashboard from "./Dashboard";
import DistantConfig from "./DistantConfig"; // 🔽 Ajouter cette importation

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/formulaire" element={<Formulaire />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/distant" element={<DistantConfig />} /> {/* 🔽 Nouvelle Route */}
      </Routes>
    </Router>
  );
}

export default App;
