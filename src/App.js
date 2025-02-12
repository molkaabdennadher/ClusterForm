import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Formulaire from './formulaire';
import Dashboard from './Dashboard';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Formulaire />} />
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>
    </Router>
  );
}

export default App;
