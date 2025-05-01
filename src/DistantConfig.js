import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";

const DistantConfig = () => {
  const [servers, setServers] = useState([]);
  const [selectedSourceServer, setSelectedSourceServer] = useState(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [hostname, setHostname] = useState("");
  const [vm_id, setVmId] = useState("");
  const [network, setNetwork] = useState("nat");
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const targetServer = location.state?.targetServer;

  useEffect(() => {
    const savedServers = JSON.parse(localStorage.getItem("servers")) || [];
    setServers(savedServers);
  }, []);

  useEffect(() => {
    if (selectedSourceServer && selectedSourceServer.templates.length > 0) {
      setSelectedTemplateId(selectedSourceServer.templates[0].id);
    } else {
      setSelectedTemplateId("");
    }
  }, [selectedSourceServer]);

  const validateInputs = () => {
    if (!selectedSourceServer || !selectedTemplateId || !hostname || !vm_id) {
      alert("Veuillez remplir tous les champs.");
      return false;
    }

    if (vm_id < 100 || vm_id > 999999) {
      alert("L'ID de la VM doit être compris entre 100 et 999999.");
      return false;
    }

    return true;
  };

  const handleSubmit = async () => {
    if (!validateInputs()) return;
  
    setIsLoading(true);
    try {
      const isSameServer = selectedSourceServer.serverIp === targetServer.serverIp;
  
      if (!isSameServer) {
        const response = await axios.post("http://localhost:5000/clone_template", {
          sourceProxmoxIp: selectedSourceServer.serverIp,
          targetProxmoxIp: targetServer.serverIp,
          template_id: selectedTemplateId,
          username: selectedSourceServer.user,
          password: selectedSourceServer.password,
        });
  
        if (!response.data.success) {
          alert(`Erreur lors du clonage : ${response.data.message}`);
          return;
        }
        alert("Clonage réussi !");
      }
  
      const createResponse = await axios.post("http://localhost:5000/create_vmprox", {
        proxmoxIp: targetServer.serverIp,
        password: targetServer.password,
        hostname: hostname,
        targetNode: targetServer.node,
        network: network,
        template: "ubuntu-template",
        vm_id: vm_id,
      });
  
      if (createResponse.data.error) {
        alert(`Erreur lors de la création de la VM : ${createResponse.data.error}`);
      } else {
        alert("VM créée avec succès !");
  
        // Structure the VM data correctly
        const newVm = {
          proxmoxIp: targetServer.serverIp,
          nodeName: targetServer.node,
          password: targetServer.password,
          hostname: hostname,
          vm_id: vm_id,
          network: network,
          ipAddress: 'N/A', // You can update this later if the API provides an IP
          template: "ubuntu-template",
          status: 'Stopped', // Default status
          creationDate: new Date().toISOString().split('T')[0], // Current date
        };
  
        // Navigate to Dashboard and pass the new VM data
        navigate("/dashboard", { state: { newVm } });
      }
    } catch (error) {
      console.error("Erreur :", error);
      alert("Erreur lors du clonage ou de la création de la VM.");
    } finally {
      setIsLoading(false);
    }
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
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Distant Mode</h1>
      <div className="bg-white p-6 rounded-lg shadow-lg w-96">
        <label className="block text-sm font-medium">Serveur source:</label>
        <select
          value={selectedSourceServer ? selectedSourceServer.id : ""}
          onChange={(e) => {
            const server = servers.find((s) => s.id.toString() === e.target.value);
            setSelectedSourceServer(server || null);
          }}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="" disabled>Sélectionnez un serveur source</option>
          {servers.map((server) => (
            <option key={server.id} value={server.id}>
              {server.serverIp} ({server.node})
            </option>
          ))}
        </select>

        <label className="block text-sm font-medium">Template ID:</label>
        <select
          value={selectedTemplateId}
          onChange={(e) => setSelectedTemplateId(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        >
          <option value="" disabled>Sélectionnez un template ID</option>
          {selectedSourceServer?.templates.map((template, index) => (
            <option key={index} value={template.id}>
              {template.id}
            </option>
          ))}
        </select>

        <label className="block text-sm font-medium">Hostname:</label>
        <input
          type="text"
          placeholder="Entrez le hostname"
          value={hostname}
          onChange={(e) => setHostname(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">VM ID:</label>
        <input
          type="number"
          placeholder="Entrez l'ID de la VM"
          value={vm_id}
          onChange={(e) => setVmId(Number(e.target.value))}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">Type de réseau:</label>
        <select
          value={network}
          onChange={(e) => setNetwork(e.target.value)}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="nat">NAT</option>
          <option value="bridged">Bridged</option>
        </select>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={isLoading}
          className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600 disabled:bg-gray-400"
        >
          {isLoading ? "Chargement..." : "Cloner et créer la VM"}
        </button>
      </div>
    </div>
  );
};

export default DistantConfig;