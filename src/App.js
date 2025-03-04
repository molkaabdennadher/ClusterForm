import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Home from "./Home";
import Formulaire from "./formulaire";
import Dashboard from "./Dashboard";
import DistantConfig from "./DistantConfig";
import ClusterVir from "./ClusterVir";
import ClusterformVir from "./ClusterformVir";
import ClusterDashVir from "./ClusterDashVir";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/formulaire" element={<Formulaire />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/DistantConfig" element={<DistantConfig />} />
        <Route path="/ClusterVir" element={<ClusterVir />} />
        <Route path="/ClusterformVir" element={<ClusterformVir />} />
        <Route path="/ClusterDashVir" element={<ClusterDashVir />} />
      </Routes>
    </Router>
  );
}

export default App;
