import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const HypervisorSelection = ({ onPrevious }) => {
  const [hypervisor, setHypervisor] = useState(null);  // Utilisation de useState pour stocker le choix
  const navigate = useNavigate();

  const handleProxmoxSelect = () => {
    navigate("/option-select", { state: { hypervisor: "Proxmox" } });
  };
  const handleVirtualBoxSelect = () => {
    navigate("/option-select", { state: { hypervisor: "VirtualBox" } });
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <h1 className="text-5xl font-bold text-teal-600 mb-10">Welcome!</h1>
      <div className="flex justify-center gap-12">
        {/* Proxmox Option */}
        <div
          className="flex flex-col items-center p-6 bg-white shadow-lg rounded-lg cursor-pointer transform transition-all hover:scale-105 hover:shadow-xl"
          onClick={handleProxmoxSelect}
        >
          <img
            src="https://forum.proxmox.com/styles/uix/images/Proxmox-logo-stacked-white-background-1200.png"
            alt="Proxmox"
            className="w-32 h-32 mb-4"
          />
          <label className="font-semibold text-lg text-gray-700">Proxmox</label>
        </div>

        {/* VirtualBox Option */}
        <div
          className="flex flex-col items-center p-6 bg-white shadow-lg rounded-lg cursor-pointer transform transition-all hover:scale-105 hover:shadow-xl"
          onClick={handleVirtualBoxSelect}
        >
          <img
            src="https://upload.wikimedia.org/wikipedia/commons/d/d5/Virtualbox_logo.png"
            alt="VirtualBox"
            className="w-32 h-32 mb-4"
          />
          <label className="font-semibold text-lg text-gray-700">VirtualBox</label>
        </div>
      </div>

      {/* Option for going back */}
      {onPrevious && (
        <button
          className="mt-8 text-teal-600 font-semibold hover:text-teal-800"
          onClick={onPrevious}
        >
          Go Back
        </button>
      )}
    </div>
  );
};

export default HypervisorSelection;
