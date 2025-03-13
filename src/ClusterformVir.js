import React, { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import OSVersionSelect from './OSVersionSelect';
import CustomBox from './CustomBox';
export default function ClusterFormVir() {
  const location = useLocation();
  const navigate = useNavigate();
  const [isCustomBoxOpen, setIsCustomBoxOpen] = useState(false);
  const [customRam, setCustomRam] = useState(4);
  const [customCpu, setCustomCpu] = useState(2);
  const [customBoxes, setCustomBoxes] = useState(() => {
    // Récupérer les boxes personnalisées depuis localStorage
    const savedBoxes = localStorage.getItem("customBoxes");
    return savedBoxes ? JSON.parse(savedBoxes) : []; // Si aucune box n'est trouvée, retourner un tableau vide
  });
  const [osOptions, setOsOptions] = useState(() => {
    const savedOptions = localStorage.getItem("osOptions");
    return savedOptions ? JSON.parse(savedOptions) : ["ubuntu/trusty64", "ubuntu-focal", "ubuntu-bionic"];
  });
  // Récupération des données globales du cluster transmises depuis ClusterVir
  const { clusterName, clusterDescription, nodeCount, clusterType, isHaSelected } = location.state;

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
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === "osOptions") {
        setOsOptions(JSON.parse(e.newValue));
      }
    };

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  const handleNodeDetailsChange = (field, value) => {
    setNodeDetails((prev) => {
      const updatedDetails = [...prev];
      updatedDetails[currentNode][field] = value;
      return updatedDetails;
    });
  };
  const handleAddCustomBox = ({ name, ram, cpu }) => {
    const updatedBoxes = [...customBoxes, { name, ram, cpu }];
    const updatedOptions = [...osOptions, name];

    setCustomBoxes(updatedBoxes);
    setOsOptions(updatedOptions);

    // Mettre à jour localStorage
    localStorage.setItem("customBoxes", JSON.stringify(updatedBoxes));
    localStorage.setItem("osOptions", JSON.stringify(updatedOptions));
  };
  const [haComponents, setHaComponents] = useState({
    isZookeeper: false,
    isNamenodeStandby: false,
    isResourceManagerStandby: false,
  });

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
        nodeCount,
        clusterType,
        nodeDetails,
        haComponents,
        customBoxes,
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
        <OSVersionSelect
          value={nodeDetails[currentNode].osVersion}
          onChange={(value) => handleNodeDetailsChange("osVersion", value)}
          onCustomBoxSelect={setIsCustomBoxOpen}
          options={osOptions} // Passer la liste des options dynamiques
        />
        {isCustomBoxOpen && (
          <CustomBox
            ram={customRam}
            cpu={customCpu}
            onRamChange={setCustomRam}
            onCpuChange={setCustomCpu}
            onClose={() => setIsCustomBoxOpen(false)}
            onAddBox={handleAddCustomBox} // Assurez-vous que c'est bien passé ici
          />
        )}
       

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
        {isHaSelected && (
          <div className="mb-4">
            <label className="inline-flex items-center">
              <input
                type="checkbox"
                checked={haComponents.isZookeeper}
                onChange={(e) => setHaComponents({ ...haComponents, isZookeeper: e.target.checked })}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">Zookeeper</span>
            </label>
            <label className="inline-flex items-center ml-4">
              <input
                type="checkbox"
                checked={haComponents.isNamenodeStandby}
                onChange={(e) => setHaComponents({ ...haComponents, isNamenodeStandby: e.target.checked })}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">Namenode Standby</span>
            </label>
            <label className="inline-flex items-center ml-4">
              <input
                type="checkbox"
                checked={haComponents.isResourceManagerStandby}
                onChange={(e) => setHaComponents({ ...haComponents, isResourceManagerStandby: e.target.checked })}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">Resource Manager Standby</span>
            </label>
          </div>

        )}

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
