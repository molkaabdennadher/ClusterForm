import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlay, faStop, faPlus, faSync } from "@fortawesome/free-solid-svg-icons";
import axios from "axios";
import AddServerForm from "./AddServerForm";

function AjoutServProx() {
  const [servers, setServers] = useState(() => {
    const savedServers = localStorage.getItem("servers");
    return savedServers ? JSON.parse(savedServers) : [];
  });
  const [showAddServerForm, setShowAddServerForm] = useState(false);
  const [selectedServer, setSelectedServer] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedOption } = location.state || { selectedOption: "" }; // Récupérer selectedOption depuis l'état

  console.log("Données reçues dans AjoutServProx :", location.state); // Debug

  // Fonction pour récupérer les templates
  const getTemplates = async (server) => {
    try {
      const response = await axios.post("http://localhost:5000/connect_and_get_templates", {
        proxmox_ip: server.serverIp,
        username: server.user,
        password: server.password,
      });

      if (response.data.success) {
        alert("Templates récupérés avec succès !");

        // Mettre à jour les templates du serveur
        const updatedServers = servers.map((s) =>
          s.id === server.id ? { ...s, templates: response.data.templates } : s
        );
        setServers(updatedServers);
        localStorage.setItem("servers", JSON.stringify(updatedServers));
      } else {
        alert(`Échec de la récupération des templates : ${response.data.error}`);
      }
    } catch (error) {
      console.error("Erreur lors de la récupération des templates :", error);
      alert(`Erreur lors de la récupération des templates : ${error.message}`);
    }
  };

  // Fonction pour naviguer vers la page suivante
  const navigateToNextPage = (server) => {
    if (!server) {
      alert("Veuillez sélectionner un serveur.");
      return;
    }

    // Naviguer vers la page appropriée en fonction de selectedOption
    if (selectedOption === "Cluster") {
      navigate("/ClusterProx", { state: { selectedServer: server } });
    } else if (selectedOption === "Virtual Machine") {
      navigate("/DistantConfig", { state: { targetServer: server } });
    }
  };

  // Fonction pour ajouter un nouveau serveur
  const addServer = (newServer) => {
    const updatedServers = [...servers, { ...newServer, id: Date.now(), templates: [] }];
    setServers(updatedServers);
    localStorage.setItem("servers", JSON.stringify(updatedServers));
    setShowAddServerForm(false);
  };

  // Fonction pour naviguer vers la page précédente
  const handlePrevious = () => {
    navigate("/");
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="bg-white p-10 rounded-lg shadow-xl w-3/4 max-w-4xl">
        <h1 className="text-5xl font-bold text-teal-600 mb-10">Proxmox Server</h1>
        <div className="flex justify-end mb-6">
          <button
            onClick={() => setShowAddServerForm(true)}
            className="flex items-center bg-teal-500 text-white p-3 rounded-lg shadow-md hover:bg-teal-600"
          >
            <FontAwesomeIcon icon={faPlus} className="mr-2" />
          </button>
        </div>
        {showAddServerForm && <AddServerForm onAddServer={addServer} onClose={() => setShowAddServerForm(false)} />}
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border-collapse border border-gray-300">
            <thead className="bg-teal-500 text-white">
              <tr>
                <th className="px-6 py-4 border-b text-left">Server IP</th>
                <th className="px-6 py-4 border-b text-left">Node</th>
                <th className="px-6 py-4 border-b text-left">User</th>
                <th className="px-6 py-4 border-b text-left">Password</th>
                <th className="px-6 py-4 border-b text-left">Template</th>
                <th className="px-6 py-4 border-b text-left">Template ID</th>
                <th className="px-6 py-4 border-b text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {servers.map((server) => (
                <tr
                  key={server.id}
                  className={`cursor-pointer ${selectedServer?.id === server.id ? "bg-teal-100" : ""} hover:bg-teal-50`}
                  onClick={() => {
                    setSelectedServer(server); // Sélectionner le serveur
                    navigateToNextPage(server); // Naviguer vers la page suivante
                  }}
                >
                  <td className="px-6 py-4 border-b">{server.serverIp}</td>
                  <td className="px-6 py-4 border-b">{server.node}</td>
                  <td className="px-6 py-4 border-b">{server.user}</td>
                  <td className="px-6 py-4 border-b">{server.password}</td>
                  <td className="px-6 py-4 border-b">
                    <select className="w-full p-2 border rounded">
                      {server.templates.map((template, index) => (
                        <option key={index} value={template.name}>
                          {template.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-6 py-4 border-b">
                    <select className="w-full p-2 border rounded">
                      {server.templates.map((template, index) => (
                        <option key={index} value={template.id}>
                          {template.id}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-6 py-4 border-b text-center">
                    <button
                      onClick={(e) => {
                        e.stopPropagation(); // Empêcher la propagation de l'événement de clic sur la ligne
                        getTemplates(server); // Exécuter la fonction pour récupérer les templates
                      }}
                      className="text-blue-500 hover:text-blue-700 mr-2"
                      title="Update"
                    >
                      <FontAwesomeIcon icon={faSync} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex justify-between mt-6">
          <button onClick={handlePrevious} className="flex items-center bg-gray-500 text-white p-3 rounded-lg shadow-md hover:bg-gray-600">Back</button>
        </div>
      </div>
    </div>
  );
}

export default AjoutServProx;