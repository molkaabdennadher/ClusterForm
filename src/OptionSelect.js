import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

const OptionSelect = () => {
  const navigate = useNavigate();
  const location = useLocation(); // Récupère l'état passé avec navigate()
  const [selection, setSelection] = useState(""); // Gère la sélection
  const [error, setError] = useState(""); // Gère l'erreur
  const { hypervisor } = location.state || {}; 
  console.log("Hypervisor reçu :", hypervisor);  // Debug
  
  // Gestion du changement de sélection
  const handleSelectionChange = (e) => {
    setSelection(e.target.value); // Met à jour la sélection
    setError(""); // Efface toute erreur précédente
  };

  // Gestion du bouton suivant
  const handleNext = () => {
    if (!selection) {
      setError("Veuillez sélectionner une option."); // Gérer l'erreur si aucune option n'est choisie
      return;
    }
  
    if (hypervisor === "Proxmox") {
      if (selection === "Cluster") {
        navigate("/ajout-serveur-proxmox", { state: { hypervisor, selectedOption: selection } });
      } else {
        navigate("/ajout-serveur-proxmox", { state: { hypervisor, selectedOption: selection } });
      }
    } else if (hypervisor === "VirtualBox") {
      if (selection === "Cluster") {
        navigate("/mode-select", { state: { hypervisor, selectedOption: selection } });
      } else {
        navigate("/mode-select", { state: { hypervisor, selectedOption: selection } });
      }
    }
  };
  
  

  // Fonction pour revenir à la page précédente
  const handlePrevious = () => {
    navigate(-1); // Reviens à la page précédente
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="bg-white p-10 rounded-lg shadow-xl w-3/4 max-w-4xl">
        <h1 className="text-5xl font-bold text-teal-600 mb-10">Welcome !</h1>
        <p className="text-lg text-gray-600 mb-6">you want to create :</p>

        {/* Affichage en fonction de l'hyperviseur sélectionné */}
        {hypervisor === "Proxmox" && <p>You chose Proxmox</p>}
        {hypervisor === "VirtualBox" && <p>You chose VirtualBox</p>}

        <div className="space-y-4">
          <div className="flex items-center">
            <input
              type="radio"
              id="cluster"
              name="option"
              value="Cluster"
              checked={selection === "Cluster"}
              onChange={handleSelectionChange}
              className="mr-2"
            />
            <label htmlFor="cluster" className="text-lg cursor-pointer">
              A Cluster
            </label>
          </div>

          <div className="flex items-center">
            <input
              type="radio"
              id="vm"
              name="option"
              value="Virtual Machine"
              checked={selection === "Virtual Machine"}
              onChange={handleSelectionChange}
              className="mr-2"
            />
            <label htmlFor="vm" className="text-lg cursor-pointer">
              A Vitual Machine 
            </label>
          </div>
        </div>

        {/* Affichage de l'erreur si nécessaire */}
        {error && <p className="text-red-500 mt-4">{error}</p>}

        {/* Boutons Précédent et Suivant */}
        <div className="flex justify-between mt-10">
          <button
            onClick={handlePrevious} // Utilisation de la nouvelle fonction handlePrevious
            className="bg-gray-500 text-white p-2 rounded-lg shadow-md hover:bg-gray-600"
          >
            Back
          </button>
          <button
            onClick={handleNext}
            className="bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
            disabled={!selection} // Désactive le bouton si aucune option n'est sélectionnée
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};

export default OptionSelect;
