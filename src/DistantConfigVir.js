import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Tooltip } from "react-tooltip";

const DistantConfigVir = () => {
  const location = useLocation();
  const navigate = useNavigate();
  
  // Get data from location state
  const { hypervisor, selectedOption } = location.state || {};
  
  const [formData, setFormData] = useState({
    remote_ip: "192.168.0.27",
    remote_user: "User",
    remote_password: "amiria123",
    mail: "",
    remote_os: "Windows",
    hypervisor: hypervisor || "VirtualBox"
  });

  useEffect(() => {
    // Debug current state
    console.log("Current location state:", location.state);
    
    if (!location.state || (!location.state.hypervisor && !location.state.selectedOption)) {
      console.error("Missing required navigation data");
    }
  }, [location.state]);

  const handleSubmit = () => {
    if (!formData.remote_ip || !formData.remote_user || !formData.remote_password) {
      alert("Please fill all required fields!");
      return;
    }

    // Get the selectedOption from location state
    const option = selectedOption || location.state?.option;
    
    if (!option) {
      console.error("No option provided in state");
      alert("Configuration error: Missing option selection");
      return;
    }

    // Create navigation state with all required data
    const navigationState = {
      ...formData,
      mode: "distant",
      // Preserve the original hypervisor and selectedOption values
      hypervisor: hypervisor || formData.hypervisor,
      selectedOption: option
    };

    console.log("Navigation state:", navigationState);

    // Navigate based on the selected option
    if (option === "Cluster") {
      navigate("/ClusterVir", { state: navigationState });
    } else if (option === "Virtual Machine") {
      navigate("/formulaireVir", { state: navigationState });
    } else {
      console.error("Unrecognized option:", option);
      alert(`Invalid configuration. Received option: "${option}"`);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="absolute top-4 right-4">
        <button
          onClick={() => navigate("/dashboard")}
          className="bg-teal-500 text-white px-4 py-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Dashboard
        </button>
      </div>
      
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Distant Mode Configuration</h1>
      
      <div className="bg-white p-6 rounded-lg shadow-lg w-96">
        <form onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
          <div className="mb-4">
            <label className="block text-sm font-medium mb-1">IP Address:</label>
            <input
              type="text"
              name="remote_ip"
              value={formData.remote_ip}
              onChange={handleInputChange}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium mb-1">Username:</label>
            <input
              type="text"
              name="remote_user"
              value={formData.remote_user}
              onChange={handleInputChange}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium mb-1">Password:</label>
            <input
              type="password"
              name="remote_password"
              value={formData.remote_password}
              onChange={handleInputChange}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium mb-1">Email:</label>
            <input
              type="email"
              name="mail"
              value={formData.mail}
              onChange={handleInputChange}
              className="w-full p-2 border rounded"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium mb-1">Remote OS:</label>
            <select
              name="remote_os"
              value={formData.remote_os}
              onChange={handleInputChange}
              className="w-full p-2 border rounded"
            >
              <option value="Windows">Windows</option>
              <option value="Linux">Linux</option>
            </select>
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium mb-1">Hypervisor:</label>
            <select
              name="hypervisor"
              value={formData.hypervisor}
              onChange={handleInputChange}
              className="w-full p-2 border rounded"
              disabled={hypervisor ? true : false}
            >
              <option value="VirtualBox">VirtualBox</option>
              <option value="VMware">VMware Workstation Pro</option>
            </select>
          </div>

          <button
            type="submit"
            className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
          >
            Connect
          </button>
        </form>
      </div>
      
      <Tooltip effect="solid" />
    </div>
  );
};

export default DistantConfigVir;