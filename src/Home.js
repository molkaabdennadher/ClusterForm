import { BrowserRouter as Router, Routes, Route, useNavigate } from "react-router-dom";
import { useState } from "react";
import DistantConfig from "./DistantConfig";
import DistantConfigVir from "./DistantConfig";
import FormulaireVir from "./formulaire";
import ClusterVir from "./ClusterVir";
import "./Home.css"; // Importation du fichier CSS

function App() {
  const [step, setStep] = useState(1);
  const [platform, setPlatform] = useState("");
  const [option, setOption] = useState("");
  const [mode, setMode] = useState("");
  const navigate = useNavigate();

  const handlePlatformSelect = (value) => {
    setPlatform(value);
    setStep(2);
  };

  const handleOptionSelect = (value) => {
    setOption(value);
    setStep(3);
  };

  const handleModeSelect = (value) => {
    setMode(value);
  };

  const handleSubmit = () => {
    if (platform === "Proxmox" && option === "Virtual Machine") {
      navigate("/DistantConfig");
    } else if (platform === "Proxmox") {
      navigate("/formulaire");
    } else if (platform === "VirtualBox" && option === "Virtual Machine") {
      if (mode === "Local mode") {
        navigate("/formulaire", { state: { mode: "local" } });
      } else if (mode === "Distant mode") {
        navigate("/DistantConfig", { state: { mode: "distant" } });
      }
    } else if (platform === "VirtualBox" && option === "Cluster") {
      navigate("/ClusterVir");
    } else {
      alert(`VM created in ${mode} mode on ${platform} (${option})`);
    }
  };

  return (
    <div className="flex items-center justify-center h-screen bg-gradient-to-r from-green-200 to-teal-300">
      <div className="bg-white p-10 rounded-lg shadow-xl w-3/4 max-w-4xl">
        {/* Progress Bar */}
        <div className="relative pt-1 mb-10">
          <div className="flex mb-2 items-center justify-between">
            <div>
              <span className="text-xs font-semibold inline-block py-1 px-2 uppercase rounded-full text-teal-600 bg-teal-200">
                Step {step} of 3
              </span>
            </div>
          </div>
          <div className="overflow-hidden h-2 mb-4 text-xs flex rounded bg-teal-200">
            <div
              style={{ width: `${(step / 3) * 100}%` }}
              className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-teal-500"
            ></div>
          </div>
        </div>

        {step === 1 && (
          <div className="text-center">
            <h1 className="text-5xl font-bold text-teal-600 mb-10">Welcome!</h1>
            <div className="flex justify-around">
              <div
                className="text-center cursor-pointer"
                onClick={() => handlePlatformSelect("Proxmox")}
              >
                <img
                  src="https://forum.proxmox.com/styles/uix/images/Proxmox-logo-stacked-white-background-1200.png"
                  alt="Proxmox"
                  className="w-32 mx-auto"
                />
                <label className="block mt-2">Proxmox</label>
              </div>
              <div
                className="text-center cursor-pointer"
                onClick={() => handlePlatformSelect("VirtualBox")}
              >
                <img
                  src="https://upload.wikimedia.org/wikipedia/commons/d/d5/Virtualbox_logo.png"
                  alt="VirtualBox"
                  className="w-32 mx-auto"
                />
                <label className="block mt-2">VirtualBox</label>
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="text-center">
            <h1 className="text-5xl font-bold text-teal-600 mb-10">Welcome!</h1>
            <p className="text-lg text-gray-600 mb-6">You want to create:</p>
            <div className="space-y-4">
              <div className="flex items-center">
                <input
                  type="radio"
                  id="cluster"
                  name="option"
                  value="Cluster"
                  checked={option === "Cluster"}
                  onChange={(e) => handleOptionSelect(e.target.value)}
                  className="mr-2"
                />
                <label htmlFor="cluster" className="text-lg">
                  A Cluster
                </label>
              </div>
              <div className="flex items-center">
                <input
                  type="radio"
                  id="vm"
                  name="option"
                  value="Virtual Machine"
                  checked={option === "Virtual Machine"}
                  onChange={(e) => handleOptionSelect(e.target.value)}
                  className="mr-2"
                />
                <label htmlFor="vm" className="text-lg">
                  A Virtual Machine
                </label>
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="text-center">
            <h1 className="text-5xl font-bold text-teal-600 mb-10">Welcome!</h1>
            <p className="text-lg text-gray-600 mb-6">
              You want to create your VM:
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
                <label htmlFor="local" className="text-lg">
                  Local mode
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
                <label htmlFor="distant" className="text-lg">
                  Distant mode
                </label>
              </div>
            </div>
            <button
              onClick={handleSubmit}
              className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600 mt-10"
              disabled={!mode}
            >
              Connect
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;