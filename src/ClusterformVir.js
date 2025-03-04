import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export default function ClusterformVir() {
  const [osVersion, setOsVersion] = useState("ubuntu-trusty24");
  const [ram, setRam] = useState(4);
  const [cpu, setCpu] = useState(2);
  const [totalMemoryGB, setMaxRam] = useState(16);
  const [maxCpu, setMaxCpu] = useState(8);
  const [network, setNetwork] = useState("NAT");
  const [hostname, setHostname] = useState("");
  const [currentNode, setCurrentNode] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();
  const { clusterName, clusterDescription, nodeCount, clusterType } = location.state;

  const [nodeDetails, setNodeDetails] = useState(
    Array.from({ length: nodeCount }, () => ({
      hostname: "",
      osVersion: "ubuntu-trusty24",
      ram: 4,
      cpu: 2,
      network: "NAT",
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

    // Si le nœud actuel est le dernier, naviguer vers le tableau de bord
    if (currentNode < nodeCount - 1) {
      setCurrentNode(currentNode + 1);
      // Réinitialiser les valeurs pour le nœud suivant
      setHostname("");
      setOsVersion("ubuntu-trusty24");
      setRam(4);
      setCpu(2);
      setNetwork("NAT");
      setNodeDetails((prev) => {
        const updatedDetails = [...prev];
        updatedDetails[currentNode + 1] = {
          ...updatedDetails[currentNode + 1],
          hostname: "",
          nodeDescription: "",
          isNameNode: false,
          isResourceManager: false,
          isDataNode: false,
        };
        return updatedDetails;
      });
    } else {
      // Naviguer vers le tableau de bord avec les détails des nœuds
      navigate("/ClusterDashVir", {
        state: {
          clusterName,
          clusterDescription,
          nodeCount,
          clusterType,
          nodeDetails,
        },
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
          <option value="ubuntu-trusty24">Ubuntu-trusty 24</option>
          <option value="ubuntu-focal">Ubuntu-focal</option>
          <option value="ubuntu-bionic">Ubuntu-bionic</option>
        </select>

        <label className="block text-sm font-medium">RAM: {nodeDetails[currentNode].ram} GB</label>
        <input
          type="range"
          min="2"
          max={totalMemoryGB}
          step="2"
          value={nodeDetails[currentNode].ram}
          onChange={(e) => handleNodeDetailsChange("ram", Number(e.target.value))}
          className="w-full mb-4"
        />

        <label className="block text-sm font-medium">CPU: {nodeDetails[currentNode].cpu} vCPUs</label>
        <input
          type="range"
          min="1"
          max={maxCpu}
          step="1"
          value={nodeDetails[currentNode].cpu}
          onChange={(e) => handleNodeDetailsChange("cpu", Number(e.target.value))}
          className="w-full mb-4"
        />

        <label className="block text-sm font-medium mb-2">Network:</label>
        <select
          value={nodeDetails[currentNode].network}
          onChange={(e) => handleNodeDetailsChange("network", e.target.value)}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="NAT">NAT</option>
          <option value="Bridged">Bridged</option>
          <option value="Private">Private Network</option>
        </select>

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
          {currentNode < nodeCount - 1 ? "Next" : "Submit Form"}
        </button>
      </form>
    </div>
  );
}
