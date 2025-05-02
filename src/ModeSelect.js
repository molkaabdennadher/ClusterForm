import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";

const ModeSelection = ({ onPrevious }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [selectedMode, setSelectedMode] = useState("");
  
  // Get the data passed from previous component
  const { hypervisor, selectedOption } = location.state || {};

  // Verification of required data
  useEffect(() => {
    if (!hypervisor || !selectedOption) {
      console.error("Missing required data:", location.state);
      navigate("/", {
        state: {
          error: "missing_required_data",
          missing: {
            hypervisor: !hypervisor,
            selectedOption: !selectedOption
          }
        },
        replace: true
      });
    }
  }, [hypervisor, selectedOption, navigate]);

  const handleModeSelect = (mode) => {
    setSelectedMode(mode);
    
    // Prepare navigation state with all necessary data
    const navigationState = {
      hypervisor,
      selectedOption,
      mode
    };

    // Navigate based on the selected mode
    if (mode === "Distant mode") {
      navigate("/DistantConfigVir", { state: navigationState });
    } else if (mode === "Local mode") {
      // For local mode, navigate directly to the appropriate component
      if (selectedOption === "Cluster") {
        navigate("/ClusterVir", { state: navigationState });
      } else if (selectedOption === "Virtual Machine") {
        navigate("/formulaireVir", { state: navigationState });
      }
    }
  };

  const handleBack = () => {
    onPrevious?.() || navigate(-1);
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="bg-white p-10 rounded-lg shadow-xl w-3/4 max-w-4xl">
        <h1 className="text-5xl font-bold text-teal-600 mb-10">Welcome!</h1>
        <p className="text-lg text-gray-600 mb-6">
          Choose a mode to create your {selectedOption}:
        </p>

        <div className="space-y-4">
          {["Local mode", "Distant mode"].map((mode) => (
            <div key={mode} className="flex items-center">
              <input
                type="radio"
                id={mode.toLowerCase().replace(" ", "-")}
                name="mode"
                value={mode}
                checked={selectedMode === mode}
                onChange={() => handleModeSelect(mode)}
                className="mr-2"
              />
              <label 
                htmlFor={mode.toLowerCase().replace(" ", "-")} 
                className="text-lg cursor-pointer"
              >
                {mode}
              </label>
            </div>
          ))}
        </div>

        <div className="flex justify-between mt-10">
          <button
            onClick={handleBack}
            className="bg-gray-500 text-white p-2 rounded-lg shadow-md hover:bg-gray-600"
          >
            Back
          </button>
        </div>
      </div>
    </div>
  );
};

export default ModeSelection;