import React, { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import OSVersionSelect from "./OSVersionSelect";
import CustomBox from "./CustomBox";

export default function ClusterFormVir() {
  const location = useLocation();
  const navigate = useNavigate();

  // Récupération des données du cluster depuis location.state ou valeurs par défaut
  const {
    clusterName = "Default Cluster",
    clusterDescription = "",
    nodeCount = 3,
    clusterType = { Ha: false, Spark: false, Classic: true },
    isHaSelected = false,
    isSparkSelected = false,
  } = location.state || {};

  // États pour la gestion des boîtes personnalisées
  const [isCustomBoxOpen, setIsCustomBoxOpen] = useState(false);
  const [customRam, setCustomRam] = useState(4);
  const [customCpu, setCustomCpu] = useState(2);
  const [customBoxes, setCustomBoxes] = useState(() => {
    const saved = localStorage.getItem("customBoxes");
    return saved ? JSON.parse(saved) : [];
  });

  // Options du système d'exploitation
  const [osOptions, setOsOptions] = useState(() => {
    const saved = localStorage.getItem("osOptions");
    return saved
      ? JSON.parse(saved)
      : ["ubuntu/trusty64", "ubuntu-focal", "ubuntu-bionic"];
  });

  // État pour stocker la liste des nœuds (récupérée depuis le formulaire)
  const [nodeDetails, setNodeDetails] = useState([]);

  // État pour les données du nœud en cours de saisie
  const [currentNodeData, setCurrentNodeData] = useState({
    hostname: "",
    osVersion: "ubuntu/bionic64", //a voir pour l'image 
    ram: 4,
    cpu: 2,
    ip: "192.168.56.4",
    nodeDescription: "",
    isNameNode: true,
    isNameNodeStandby: isHaSelected ? false : undefined,
    isResourceManager: true,
    isResourceManagerStandby: isHaSelected ? false : undefined,
    isDataNode: true,
    isNodeManager: false,
    isZookeeper: isHaSelected ? false : undefined,
    isJournalNode: isHaSelected ? false : undefined,
    // Champ pour Spark, initialisé à false
    isSparkNode: false,
  });

  // Index du nœud en cours (pour afficher "Node X sur Y")
  const [currentNodeIndex, setCurrentNodeIndex] = useState(0);

  // Synchronisation des options OS via localStorage
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === "osOptions") {
        setOsOptions(JSON.parse(e.newValue));
      }
    };
    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  // Mise à jour d'un champ du formulaire pour le nœud en cours
  const handleFieldChange = (field, value) => {
    setCurrentNodeData((prev) => ({ ...prev, [field]: value }));
  };

  // Ajouter une boîte personnalisée
  const handleAddCustomBox = ({ name, ram, cpu }) => {
    const updatedBoxes = [...customBoxes, { name, ram, cpu }];
    const updatedOptions = [...osOptions, name];
    setCustomBoxes(updatedBoxes);
    setOsOptions(updatedOptions);
    localStorage.setItem("customBoxes", JSON.stringify(updatedBoxes));
    localStorage.setItem("osOptions", JSON.stringify(updatedOptions));
  };

  // Soumettre les données du nœud courant
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!currentNodeData.hostname || !currentNodeData.ip) {
      alert("Veuillez renseigner au moins le hostname et l'IP.");
      return;
    }
    setNodeDetails((prev) => [...prev, currentNodeData]);
    if (currentNodeIndex < nodeCount - 1) {
      setCurrentNodeIndex((prev) => prev + 1);
      setCurrentNodeData({
        hostname: "",
        osVersion:  "ubuntu/bionic64",
        ram: 4,
        cpu: 2,
        ip: "",
        nodeDescription: "",
        isNameNode: currentNodeIndex === 0,
        isNameNodeStandby: isHaSelected ? false : undefined,
        isResourceManager: currentNodeIndex === 0,
        isResourceManagerStandby: isHaSelected ? false : undefined,
        isDataNode: true,
        isNodeManager: true,
        isZookeeper: isHaSelected ? false : undefined,
        isJournalNode: isHaSelected ? false : undefined,
        isSparkNode: false,
      });
    } else {
      const clusterData = {
        clusterName,
        clusterDescription,
        nodeCount,
        clusterType,
        isHaSelected,
        isSparkSelected,
        nodeDetails: [...nodeDetails, currentNodeData],
        customBoxes,
        remote_ip: "192.168.0.27",
        remote_user: "User",
        remote_password: "amiria123",
        mail: "amiriaayoub@gmail.com"
      };

      let endpoint = "";
      if (isHaSelected) {
        endpoint = isSparkSelected
          ? "http://localhost:5000/create-cluster-HA-spark-remote"
          : "http://localhost:5000/create-cluster-HA-remote";
      } else {
        endpoint = "http://localhost:5000/create-cluster-remote";
      }

      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clusterData),
      })
        .then((response) => {
          if (!response.ok)
            throw new Error("Erreur lors de la création du cluster");
          return response.json();
        })
        .then((data) => {
          console.log("Cluster créé:", data);
          navigate("/ClusterDashVir", { state: data });
        })
        .catch((error) => {
          console.error("Erreur:", error);
          alert("Une erreur s'est produite lors de la création du cluster.");
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
        <h2 className="text-xl font-semibold mb-4">
          Node {currentNodeIndex + 1} / {nodeCount}
        </h2>
        <label className="block text-sm font-medium mb-2">Host Name:</label>
        <input
          type="text"
          value={currentNodeData.hostname}
          onChange={(e) => handleFieldChange("hostname", e.target.value)}
          placeholder="Enter host name"
          className="w-full p-2 border rounded mb-4"
          required
        />

        <OSVersionSelect
          value={currentNodeData.osVersion}
          onChange={(value) => handleFieldChange("osVersion", value)}
          onCustomBoxSelect={setIsCustomBoxOpen}
          options={osOptions}
        />

        {isCustomBoxOpen && (
          <CustomBox
            ram={customRam}
            cpu={customCpu}
            onRamChange={setCustomRam}
            onCpuChange={setCustomCpu}
            onClose={() => setIsCustomBoxOpen(false)}
            onAddBox={handleAddCustomBox}
          />
        )}

        <label className="block text-sm font-medium">
          RAM: {currentNodeData.ram} GB
        </label>
        <input
          type="range"
          min="2"
          max="16"
          step="2"
          value={currentNodeData.ram}
          onChange={(e) => handleFieldChange("ram", Number(e.target.value))}
          className="w-full mb-4"
        />

        <label className="block text-sm font-medium">
          CPU: {currentNodeData.cpu} vCPUs
        </label>
        <input
          type="range"
          min="1"
          max="8"
          step="1"
          value={currentNodeData.cpu}
          onChange={(e) => handleFieldChange("cpu", Number(e.target.value))}
          className="w-full mb-4"
        />

        <label className="block text-sm font-medium mb-2">IP:</label>
        <input
          type="text"
          value={currentNodeData.ip}
          onChange={(e) => handleFieldChange("ip", e.target.value)}
          placeholder="Enter IP address"
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium mb-2">
          Node Description:
        </label>
        <input
          type="text"
          value={currentNodeData.nodeDescription}
          onChange={(e) => handleFieldChange("nodeDescription", e.target.value)}
          placeholder="Enter node description"
          className="w-full p-2 border rounded mb-4"
        />

        <div className="mb-4">
          <label className="inline-flex items-center">
            <input
              type="checkbox"
              checked={currentNodeData.isNameNode}
              onChange={(e) => handleFieldChange("isNameNode", e.target.checked)}
              className="form-checkbox h-5 w-5 text-teal-600"
            />
            <span className="ml-2 text-gray-700">Name Node</span>
          </label>
          <label className="inline-flex items-center ml-4">
            <input
              type="checkbox"
              checked={currentNodeData.isResourceManager}
              onChange={(e) => handleFieldChange("isResourceManager", e.target.checked)}
              className="form-checkbox h-5 w-5 text-teal-600"
            />
            <span className="ml-2 text-gray-700">Resource Manager</span>
          </label>
          <label className="inline-flex items-center ml-4">
            <input
              type="checkbox"
              checked={currentNodeData.isDataNode}
              onChange={(e) => handleFieldChange("isDataNode", e.target.checked)}
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
                checked={currentNodeData.isNameNodeStandby || false}
                onChange={(e) => handleFieldChange("isNameNodeStandby", e.target.checked)}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">NameNode Standby</span>
            </label>
            <label className="inline-flex items-center ml-4">
              <input
                type="checkbox"
                checked={currentNodeData.isResourceManagerStandby || false}
                onChange={(e) => handleFieldChange("isResourceManagerStandby", e.target.checked)}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">Resource Manager Standby</span>
            </label>
            <label className="inline-flex items-center ml-4">
              <input
                type="checkbox"
                checked={currentNodeData.isZookeeper || false}
                onChange={(e) => handleFieldChange("isZookeeper", e.target.checked)}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">Zookeeper</span>
            </label>
            <label className="inline-flex items-center ml-4">
              <input
                type="checkbox"
                checked={currentNodeData.isJournalNode || false}
                onChange={(e) => handleFieldChange("isJournalNode", e.target.checked)}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">Journal Node</span>
            </label>
          </div>
        )}

        {isSparkSelected && (
          <div className="mb-4">
            <label className="inline-flex items-center">
              <input
                type="checkbox"
                checked={currentNodeData.isSparkNode || false}
                onChange={(e) => handleFieldChange("isSparkNode", e.target.checked)}
                className="form-checkbox h-5 w-5 text-teal-600"
              />
              <span className="ml-2 text-gray-700">Spark Node</span>
            </label>
          </div>
        )}

        <button
          type="submit"
          className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Submit Cluster
        </button>
      </form>
    </div>
  );
}