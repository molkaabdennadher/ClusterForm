import React, { useState } from "react"; 
import { useNavigate, useLocation } from "react-router-dom";
import { redirectToPage } from "./redirectLogic";

const ModeSelection = ({ onModeSelect, onSubmit, onPrevious }) => {
  const location = useLocation();
  const navigate = useNavigate();
  
  // Vérifier si location.state existe et récupérer les valeurs
  const selectedOption = location.state?.selectedOption || ""; 
  const hypervisor = location.state?.hypervisor || ""; 
  console.log(`Option: ${selectedOption}, Hyperviseur: ${hypervisor}`);

  const [mode, setMode] = useState(""); 

  // Fonction pour gérer le changement de mode
  const handleModeSelect = (selectedMode) => {
    setMode(selectedMode);
    console.log(`Mode sélectionné: ${selectedMode}`);
  
    if (selectedOption && selectedMode && hypervisor) {
      redirectToPage(navigate, selectedOption, selectedMode, hypervisor);
    } else {
      console.error("Une des valeurs nécessaires n'est pas définie pour la redirection.");
    }
  };
  

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="bg-white p-10 rounded-lg shadow-xl w-3/4 max-w-4xl">
        <h1 className="text-5xl font-bold text-teal-600 mb-10">Welcome !</h1>
        <p className="text-lg text-gray-600 mb-6">
          Choose a mode to create your {selectedOption} :
        </p>

        <div className="space-y-4">
          <div className="flex items-center">
            <input
              type="radio"
              id="local"
              name="mode"
              value="Local mode"
              checked={mode === "Local mode"}
              onChange={(e) => handleModeSelect(e.target.value)}
              className="mr-2"
            />
            <label htmlFor="local" className="text-lg cursor-pointer">
              Local Mode
            </label>
          </div>

          <div className="flex items-center">
            <input
              type="radio"
              id="distant"
              name="mode"
              value="Distant mode"
              checked={mode === "Distant mode"}
              onChange={(e) => handleModeSelect(e.target.value)}
              className="mr-2"
            />
            <label htmlFor="distant" className="text-lg cursor-pointer">
              Distant Mode
            </label>
          </div>
        </div>

        {/* Boutons Précédent et Suivant */}
        <div className="flex justify-between mt-10">
          <button
            onClick={onPrevious}
            className="bg-gray-500 text-white p-2 rounded-lg shadow-md hover:bg-gray-600"
          >
            Back
          </button>
          <button
            onClick={onSubmit}
            className="bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};

export default ModeSelection;
