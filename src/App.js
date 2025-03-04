import { BrowserRouter as Router, Routes, Route, useLocation } from "react-router-dom";
import Home from "./Home";
import Formulaire from "./formulaire";
import Dashboard from "./Dashboard";
import DistantConfig from "./DistantConfig";
import DistantConfigVir from "./DistantConfigVir";
import FormulaireVir from "./formulaireVir";
import ClusterVir from "./ClusterVir";
import ClusterformVir from "./ClusterformVir";
import PreviousButton from './PreviousButton'; 
import ClusterDashVir from "./ClusterDashVir";


function App() {
  return (
    <Router>
      <MainLayout />
    </Router>
  );
}

function MainLayout() {
  const location = useLocation();
  const hidePreviousButton = location.pathname === "/"; // Cache le bouton sur la page d'accueil

  return (
    <div className="p-4">
      {!hidePreviousButton && <PreviousButton />} {/* Affiche le bouton sauf sur Home */}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/formulaire" element={<Formulaire />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/DistantConfig" element={<DistantConfig />} />
        <Route path="/formulaireVir" element={<FormulaireVir />} />
        <Route path="/DistantConfigVir" element={<DistantConfigVir />} />
        <Route path="/ClusterVir" element={<ClusterVir />} />
        <Route path="/ClusterformVir" element={<ClusterformVir />} />
        <Route path="/ClusterDashVir" element={<ClusterDashVir />} />

        
      </Routes>
    </div>
  );
}

export default App;
