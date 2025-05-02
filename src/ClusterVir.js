import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const ClusterVir = () => {
  const navigate = useNavigate();

  const [clusterName, setClusterName] = useState("aa");
  const [clusterDescription, setClusterDescription] = useState("ttt");
  const [nodeCount, setNodeCount] = useState(1);
  const [clusterType, setClusterType] = useState({
    Ha: false,
    Spark: false,
    Classic: true,
  });
  const [isHaSelected, setIsHaSelected] = useState(false);
  const [isSparkSelected, setIsSparkSelected] = useState(false);

  const handleClusterTypeChange = (e) => {
    const { name, checked } = e.target;
    setClusterType((prev) => ({
      ...prev,
      [name]: checked,
    }));
    if (name === "Ha") {
      setIsHaSelected(checked);
    }
    if (name === "Spark") {
      setIsSparkSelected(checked);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const clusterData = {
      clusterName,
      clusterDescription,
      nodeCount,
      clusterType,
      isHaSelected,
      isSparkSelected,
      nodeDetails: [], // À compléter dans la configuration des nœuds
    };

    // Passage des données vers le formulaire de configuration des nœuds
    navigate("/ClusterformVir", { state: clusterData });
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
        <label className="block text-sm font-medium mb-2">
          Number of Nodes: {nodeCount}
        </label>
        <input
          type="range"
          min="1"
          max="10"
          value={nodeCount}
          onChange={(e) => setNodeCount(Number(e.target.value))}
          className="w-full mb-4"
        />

        {/* Cluster Type: HA, Classic et Spark */}
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
          <label className="mr-4">
            <input
              type="checkbox"
              name="Classic"
              checked={clusterType.Classic}
              onChange={handleClusterTypeChange}
              className="mr-2"
            />
            Classic
          </label>
          <label>
            <input
              type="checkbox"
              name="Spark"
              checked={clusterType.Spark}
              onChange={handleClusterTypeChange}
              className="mr-2"
            />
            Spark/YARN
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