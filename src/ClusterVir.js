import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const ClusterVir = () => {
  const [clusterName, setClusterName] = useState("");
  const [clusterDescription, setClusterDescription] = useState("tttt");
  const [nodeCount, setNodeCount] = useState(3);
  const [clusterType, setClusterType] = useState({
    Ha: false,
    Classic: true,
  });

  const navigate = useNavigate();

  const handleClusterTypeChange = (e) => {
    const { name, checked } = e.target;
    setClusterType((prev) => ({
      ...prev,
      [name]: checked,
    }));
    // Mettez à jour isHaSelected en fonction du type de cluster
    if (name === "Ha") {
      setIsHaSelected(checked);
    }
  };
 

  const [isHaSelected, setIsHaSelected] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();

    // Préparer les données globales du cluster
    const clusterData = {
      clusterName,
      clusterDescription,
      nodeCount,
      clusterType,
      isHaSelected, // sous forme de chaîne, transformation dans l'étape suivante

      nodeDetails: [], // à compléter dans l'étape suivante

    };

    // On passe ces données vers la page de configuration des nœuds
    navigate("/ClusterformVir", {
      state: clusterData,
    });
  };

  const handleDashboardClick = () => {
    navigate("/ClusterDashVir");
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="absolute top-4 right-4">
        <button
          onClick={handleDashboardClick}
          className="bg-teal-500 text-white px-4 py-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Dashboard
        </button>
      </div>

      <h1 className="text-4xl font-bold text-teal-600 mb-6">Create a Cluster</h1>
      <form onSubmit={handleSubmit} className="bg-white p-6 rounded-lg shadow-lg w-96">
        {/* Cluster Name */}
        <label className="block text-sm font-medium mb-2">Cluster Name:</label>
        <input
          type="text"
          value={clusterName}
          onChange={(e) => setClusterName(e.target.value)}
          placeholder="Enter cluster name"
          className="w-full p-2 border rounded mb-4"
          required
        />

        {/* Cluster Description */}
        <label className="block text-sm font-medium mb-2">Cluster Description:</label>
        <input
          type="text"
          value={clusterDescription}
          onChange={(e) => setClusterDescription(e.target.value)}
          placeholder="Enter cluster description"
          className="w-full p-2 border rounded mb-4"
          required
        />

        {/* Number of Nodes */}
        <label className="block text-sm font-medium mb-2">Number of Nodes: {nodeCount}</label>
        <input
          type="range"
          min="1"
          max="10"
          value={nodeCount}
          onChange={(e) => setNodeCount(e.target.value)}
          className="w-full mb-4"
        />

        {/* Cluster Type: HA or Classic */}
        <label className="block text-sm font-medium mb-2">Cluster Type:</label>
        <div className="flex items-center mb-4">
          <label className="mr-4">
            <input
              type="checkbox"
              name="Ha"
              checked={clusterType.Ha}
              onChange={handleClusterTypeChange}
              className="mr-2"
            />
            High Availability (HA)
          </label>
          <label>
            <input
              type="checkbox"
              name="Classic"
              checked={clusterType.Classic}
              onChange={handleClusterTypeChange}
              className="mr-2"
            />
            Classic
          </label>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Create Cluster
        </button>
      </form>
    </div>
  );
};

export default ClusterVir;
