import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Home.css"; // Importation du fichier CSS

const Home = () => {
  const [mode, setMode] = useState("");
  const navigate = useNavigate();

  const handleConnect = () => {
    if (mode === "distant") {
      navigate("/distant");
    } else if (mode === "local") {
      navigate("/formulaire", { state: { mode: "local" } });
    } else {
      alert("Veuillez choisir un mode avant de continuer.");
    }
  };

  return (
    <div className="home-container">
      <h1 className="home-title">Welcome!</h1>
      <p className="home-subtitle">You want to create your VM:</p>

      <div className="radio-group">
        <label className="radio-label">
          <input
            type="radio"
            value="local"
            checked={mode === "local"}
            onChange={() => setMode("local")}
            className="radio-input"
          />
          Local mode
        </label>

        <label className="radio-label">
          <input
            type="radio"
            value="distant"
            checked={mode === "distant"}
            onChange={() => setMode("distant")}
            className="radio-input"
          />
          Distant mode
        </label>
      </div>

      <button className="connect-button" onClick={handleConnect}>
        Connect
      </button>
    </div>
  );
};

export default Home;
