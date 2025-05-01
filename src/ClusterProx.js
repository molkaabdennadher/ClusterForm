import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const ClusterProx = () => {
  const [clusterName, setClusterName] = useState("");
  const [nodeCount, setNodeCount] = useState(3);
  const [clusterType, setClusterType] = useState("Classic"); // 'Classic' ou 'HA'

  const navigate = useNavigate();

  const handleSubmit = (e) => {
    e.preventDefault();

    const clusterData = {
      clusterName,
      nodeCount,
      clusterType,
    };
    console.log("Cluster type envoyé :", clusterType);
    navigate("/ClusterformProx", {
      state: clusterData,
    });
  };

  const handleDashboardClick = () => {
    navigate("/ClusterDashProx");
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

        {/* Cluster Type: HA, Classic, or Spark HA */}
        <label className="block text-sm font-medium mb-2">Cluster Type:</label>
        <div className="flex flex-col mb-4 space-y-2">
          <label className="flex items-center">
            <input
              type="radio"
              name="clusterType"
              value="HA"
              checked={clusterType === "HA"}
              onChange={(e) => setClusterType(e.target.value)}
              className="mr-2"
            />
            High Availability (HA)
          </label>

          <label className="flex items-center">
            <input
              type="radio"
              name="clusterType"
              value="Classic"
              checked={clusterType === "Classic"}
              onChange={(e) => setClusterType(e.target.value)}
              className="mr-2"
            />
            Classic
          </label>

          {/* ✅ Nouveau bouton radio Spark HA */}
          <label className="flex items-center">
            <input
              type="radio"
              name="clusterType"
              value="Spark HA"
              checked={clusterType === "Spark HA"}
              onChange={(e) => setClusterType(e.target.value)}
              className="mr-2"
            />
            Spark (HA)
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

export default ClusterProx;