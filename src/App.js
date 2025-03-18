import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import HypSelect from './HypSelect';
import AjoutServProx from './AjoutServProx';
import OptionSelect from './OptionSelect';
import ModeSelect from './ModeSelect';
import DistantConfig from './DistantConfig';
import Formulaire from "./formulaire";
import Dashboard from "./Dashboard";
import CloneTemplate from "./CloneTemplate";
import FormulaireVir from "./formulaireVir";
import DistantConfigVir from "./DistantConfigVir";
import ClusterVir from "./ClusterVir";
import ClusterformVir from "./ClusterformVir";
import ClusterDashVir from "./ClusterDashVir";

const App = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<HypSelect />} />
        <Route path="/ajout-serveur-proxmox" element={<AjoutServProx />} />

        <Route path="/option-select" element={<OptionSelect />} />

        <Route path="/mode-select" element={<ModeSelect />} />
        <Route path="/DistantConfig" element={<DistantConfig />} />
        <Route path="/formulaire" element={<Formulaire />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/CloneTemplate" element={<CloneTemplate />} />

        {/* Routes pour VirtualBox */}
        <Route path="/formulaireVir" element={<FormulaireVir />} />
        <Route path="/DistantConfigVir" element={<DistantConfigVir />} />
        <Route path="/ClusterVir" element={<ClusterVir />} />
        <Route path="/ClusterformVir" element={<ClusterformVir />} />
        <Route path="/ClusterDashVir" element={<ClusterDashVir />} />
      </Routes>
    </Router>
  );
};

export default App;
