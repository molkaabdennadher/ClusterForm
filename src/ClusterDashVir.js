import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const ClusterDashVir = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [clusterData, setClusterData] = useState(null);

  useEffect(() => {
    if (location.state) {
      setClusterData(location.state);
    } else {
      // Redirigez l'utilisateur vers ClusterVir s'il n'y a pas de données de cluster
      navigate('/ClusterVir');
    }
  }, [location.state, navigate]);

  if (!clusterData) {
    return <div>Loading...</div>;
  }

  const { clusterName, clusterDescription, nodeCount, clusterType, nodeDetails } = clusterData;

  return (
    <div className="min-h-screen p-4 bg-gradient-to-b from-teal-100 to-white">
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Cluster Dashboard</h1>
      <div className="overflow-x-auto">
        <table className="min-w-full bg-white border border-gray-300">
          <thead>
            <tr className="bg-teal-500 text-white">
              <th className="py-2 px-4 border">Cluster Name</th>
              <th className="py-2 px-4 border">Cluster Description</th>
              <th className="py-2 px-4 border">Node Count</th>
              <th className="py-2 px-4 border">Cluster Type</th>
            </tr>
          </thead>
          <tbody>
            <tr className="hover:bg-gray-100">
              <td className="py-2 px-4 border">{clusterName}</td>
              <td className="py-2 px-4 border">{clusterDescription}</td>
              <td className="py-2 px-4 border">{nodeCount}</td>
              <td className="py-2 px-4 border">{clusterType.Ha ? 'High Availability (HA)' : 'Classic'}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {nodeDetails.map((node, index) => (
          <div key={index} className="bg-teal-100 p-4 rounded-lg shadow-md">
            <h3 className="text-lg font-bold text-teal-600 mb-2">Node {index + 1}</h3>
            <p className="text-gray-600 mb-2">Hostname: {node.hostname}</p>
            <p className="text-gray-600 mb-2">OS Version: {node.osVersion}</p>
            <p className="text-gray-600 mb-2">RAM: {node.ram} GB</p>
            <p className="text-gray-600 mb-2">CPU: {node.cpu} vCPUs</p>
            <p className="text-gray-600 mb-2">Network: {node.network}</p>
            <p className="text-gray-600 mb-2">
              Roles:
              {node.isNameNode && <span className="ml-2 text-teal-600">Name Node</span>}
              {node.isResourceManager && <span className="ml-2 text-teal-600">Resource Manager</span>}
              {node.isDataNode && <span className="ml-2 text-teal-600">Data Node</span>}
            </p>
            <p className="text-gray-600">{node.nodeDescription}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ClusterDashVir;