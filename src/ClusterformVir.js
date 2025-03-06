import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export default function ClusterFormVir() {
  const location = useLocation();
  const navigate = useNavigate();
  // Récupération des données globales du cluster transmises depuis ClusterVir
  const { clusterName, clusterDescription, nodeCount, clusterType, clusterIp, gateway, nameservers } = location.state;

  const [currentNode, setCurrentNode] = useState(0);
  const [nodeDetails, setNodeDetails] = useState(
    Array.from({ length: nodeCount }, () => ({
      hostname: "",
      osVersion: "ubuntu/bionic64",
      ram: 4,
      cpu: 2,
      ip: "",
      nodeDescription: "",
      isNameNode: false,
      isResourceManager: false,
      isDataNode: false,
    }))
  );

  const handleNodeDetailsChange = (field, value) => {
    setNodeDetails((prev) => {
      const updatedDetails = [...prev];
      updatedDetails[currentNode][field] = value;
      return updatedDetails;
    });
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (currentNode < nodeCount - 1) {
      // Passer au formulaire du nœud suivant
      setCurrentNode(currentNode + 1);
      setNodeDetails((prev) => {
        const updatedDetails = [...prev];
        updatedDetails[currentNode + 1] = {
          ...updatedDetails[currentNode + 1],
          hostname: "",
          ip: "",
          nodeDescription: "",
          isNameNode: false,
          isResourceManager: false,
          isDataNode: false,
        };
        return updatedDetails;
      });
    } else {
      // Au dernier nœud, rassembler toutes les données et appeler l'API
      const clusterData = {
        clusterName,
        clusterDescription,
        clusterIp,
        nodeCount,
        clusterType,
        gateway, // passerelle
        nameservers: nameservers.split(",").map((ns) => ns.trim()),
        nodeDetails,
      };

      fetch("http://localhost:5000/create_cluster", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(clusterData),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error("Erreur lors de la création du cluster");
          }
          return response.json();
        })
        .then((data) => {
          console.log("Cluster créé:", data);
          // Rediriger vers le dashboard ou afficher un message de succès
          navigate("/ClusterDashVir", { state: data });
        })
        .catch((error) => {
          console.error("Erreur:", error);
          // Vous pouvez afficher un message d'erreur ici
        });
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="absolute top-4 right-4">
        <button
          onClick={() => navigate("/ClusterDashVir")}
          className="bg-teal-500 text-white px-4 py-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Dashboard
        </button>
      </div>
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Cluster Form</h1>

      <form onSubmit={handleSubmit} className="bg-white p-6 rounded-lg shadow-lg w-96">
        <label className="block text-sm font-medium mb-2">Host Name:</label>
        <input
          type="text"
          value={nodeDetails[currentNode].hostname}
          onChange={(e) => handleNodeDetailsChange("hostname", e.target.value)}
          className="w-full p-2 border rounded mb-4"
          placeholder={`Enter host name ${currentNode + 1}`}
          required
        />

        <label className="block text-sm font-medium mb-2">OS Version:</label>
        <select
          value={nodeDetails[currentNode].osVersion}
          onChange={(e) => handleNodeDetailsChange("osVersion", e.target.value)}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="ubuntu/trusty64">ubuntu/trusty64</option>
          <option value="ubuntu-focal">Ubuntu-focal</option>
          <option value="ubuntu-bionic">Ubuntu-bionic</option>
        </select>

        <label className="block text-sm font-medium">RAM: {nodeDetails[currentNode].ram} GB</label>
        <input
          type="range"
          min="2"
          max="16"
          step="2"
          value={nodeDetails[currentNode].ram}
          onChange={(e) => handleNodeDetailsChange("ram", Number(e.target.value))}
          className="w-full mb-4"
        />

        <label className="block text-sm font-medium">CPU: {nodeDetails[currentNode].cpu} vCPUs</label>
        <input
          type="range"
          min="1"
          max="8"
          step="1"
          value={nodeDetails[currentNode].cpu}
          onChange={(e) => handleNodeDetailsChange("cpu", Number(e.target.value))}
          className="w-full mb-4"
        />

        <label className="block text-sm font-medium mb-2">IP:</label>
        <input
          type="text"
          value={nodeDetails[currentNode].ip}
          onChange={(e) => handleNodeDetailsChange("ip", e.target.value)}
          className="w-full p-2 border rounded mb-4"
          placeholder={`IP address for node ${currentNode + 1}`}
          required
        />

        <label className="block text-sm font-medium mb-2">Node Description:</label>
        <input
          type="text"
          value={nodeDetails[currentNode].nodeDescription}
          onChange={(e) => handleNodeDetailsChange("nodeDescription", e.target.value)}
          className="w-full p-2 border rounded mb-4"
          placeholder={`Enter node ${currentNode + 1} description`}
        />

        <div className="mb-4">
          <label className="inline-flex items-center">
            <input
              type="checkbox"
              checked={nodeDetails[currentNode].isNameNode}
              onChange={(e) => handleNodeDetailsChange("isNameNode", e.target.checked)}
              className="form-checkbox h-5 w-5 text-teal-600"
            />
            <span className="ml-2 text-gray-700">Name Node</span>
          </label>
          <label className="inline-flex items-center ml-4">
            <input
              type="checkbox"
              checked={nodeDetails[currentNode].isResourceManager}
              onChange={(e) => handleNodeDetailsChange("isResourceManager", e.target.checked)}
              className="form-checkbox h-5 w-5 text-teal-600"
            />
            <span className="ml-2 text-gray-700">Resource Manager</span>
          </label>
          <label className="inline-flex items-center ml-4">
            <input
              type="checkbox"
              checked={nodeDetails[currentNode].isDataNode}
              onChange={(e) => handleNodeDetailsChange("isDataNode", e.target.checked)}
              className="form-checkbox h-5 w-5 text-teal-600"
            />
            <span className="ml-2 text-gray-700">Data Node</span>
          </label>
        </div>

        <button
          type="submit"
          className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          {currentNode < nodeCount - 1 ? "Next" : "Submit Cluster"}
        </button>
      </form>
    </div>
  );
}
