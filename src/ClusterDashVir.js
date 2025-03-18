import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const ClusterDashVir = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [clusterAttempts, setClusterAttempts] = useState([]);
  const [selectedClusterIndex, setSelectedClusterIndex] = useState(null);

  // Définir la fonction handleRowClick
  const handleRowClick = (index) => {
    setSelectedClusterIndex(selectedClusterIndex === index ? null : index);
  };

  useEffect(() => {
    // Récupérer les essais depuis localStorage
    const savedAttempts = JSON.parse(localStorage.getItem("clusterAttempts")) || [];

    // Vérifier si l'essai actuel (location.state) existe déjà dans savedAttempts
    if (location.state && !savedAttempts.some(attempt => attempt.clusterName === location.state.clusterName)) {
      savedAttempts.push(location.state);
    }

    // Mettre à jour l'état avec les essais mis à jour
    setClusterAttempts(savedAttempts);
  }, [location.state, navigate]);

  return (
    <div className="min-h-screen p-4 bg-gradient-to-b from-teal-100 to-white">
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Cluster Dashboard</h1>
      <div className="overflow-x-auto">
        <table className="min-w-full bg-white border border-gray-300">
          <thead>
            <tr className="bg-teal-500 text-white">
              <th className="py-2 px-4 border">Nodes</th>
              <th className="py-2 px-4 border">Cluster Name</th>
              <th className="py-2 px-4 border">Cluster Description</th>
              <th className="py-2 px-4 border">Cluster IP</th>
              <th className="py-2 px-4 border">Gateway IP</th>
              <th className="py-2 px-4 border">Node Count</th>
              <th className="py-2 px-4 border">Cluster Type</th>
            </tr>
          </thead>
          <tbody>
            {clusterAttempts.map((attempt, index) => (
              <React.Fragment key={index}>
                <tr
                  className={`hover:bg-gray-100 ${
                    selectedClusterIndex === index ? 'bg-teal-200' : ''
                  }`}
                  onClick={() => handleRowClick(index)} // Utiliser handleRowClick ici
                >
                  <td className="py-2 px-4 border">
                    <select className="border rounded p-1">
                      {/* Options here */}
                    </select>
                  </td>
                  <td className="py-2 px-4 border">{attempt.clusterName}</td>
                  <td className="py-2 px-4 border">{attempt.clusterDescription}</td>
                  <td className="py-2 px-4 border">{attempt.clusterIp}</td>
                  <td className="py-2 px-4 border">{attempt.gateway}</td>
                  <td className="py-2 px-4 border">{attempt.nodeCount}</td>
                  <td className="py-2 px-4 border">
                    {attempt.clusterType?.Ha ? 'High Availability (HA)' : 'Classic'}
                  </td>
                </tr>
                {selectedClusterIndex === index && (
                  <tr className="bg-gray-200">
                    <td colSpan="7" className="py-2 px-4 border">
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
                        {attempt.nodeDetails.map((node, nodeIndex) => (
                          <div
                            key={nodeIndex}
                            className="bg-white border border-gray-300 rounded-lg shadow-md p-4"
                          >
                            <p className="text-lg font-semibold text-teal-600">
                              {node.hostname}
                            </p>
                            <p className="text-sm text-gray-600">
                              <strong>Description :</strong> {node.nodeDescription}
                            </p>
                            <p className="text-sm text-gray-600">
                              <strong>RAM :</strong> {node.ram} GB
                            </p>
                            <p className="text-sm text-gray-600">
                              <strong>CPU :</strong> {node.cpu} vCPUs
                            </p>
                            <p className="text-sm text-gray-600">
                              <strong>OS :</strong> {node.osVersion}
                            </p>

                            {/* Afficher les rôles des nœuds sous forme de texte */}
                            <div className="mb-4">
                              <p className="text-sm text-gray-600">
                                <strong>Rôles :</strong>
                              </p>
                              <ul className="list-disc list-inside">
                                {node.isNameNode && <li>Name Node</li>}
                                {node.isResourceManager && <li>Resource Manager</li>}
                                {node.isDataNode && <li>Data Node</li>}
                              </ul>
                            </div>

                            {/* Afficher les composants HA (si le cluster est de type HA) */}
                            {attempt.clusterType?.Ha && (
                              <div className="mb-4">
                                <p className="text-sm text-gray-600">
                                  <strong>Composants HA :</strong>
                                </p>
                                <ul className="list-disc list-inside">
                                  {node.haComponents?.isZookeeper && <li>Zookeeper</li>}
                                  {node.haComponents?.isNamenodeStandby && <li>Namenode Standby</li>}
                                  {node.haComponents?.isResourceManagerStandby && (
                                    <li>Resource Manager Standby</li>
                                  )}
                                </ul>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ClusterDashVir;