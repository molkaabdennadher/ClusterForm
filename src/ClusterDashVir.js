import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const ClusterDashVir = () => {
  const location = useLocation();
  const [clusterAttempts, setClusterAttempts] = useState([]);
  const [selectedClusterIndex, setSelectedClusterIndex] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const savedAttempts = JSON.parse(localStorage.getItem("clusterAttempts")) || [];
    if (location.state && !savedAttempts.some(attempt => attempt.clusterName === location.state.clusterName)) {
      savedAttempts.push(location.state);
    }
    setClusterAttempts(savedAttempts);
    setIsLoading(false);
  }, [location.state]);

  const handleRowClick = (index) => {
    setSelectedClusterIndex(selectedClusterIndex === index ? null : index);
  };

  if (isLoading) {
    return <div className="text-center py-8">Chargement en cours...</div>;
  }

  if (clusterAttempts.length === 0) {
    return <div className="text-center py-8">Aucun cluster n'a été créé.</div>;
  }

  return (
    <div className="min-h-screen p-4 bg-gradient-to-b from-teal-100 to-white">
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Cluster Dashboard</h1>
      <div className="overflow-x-auto max-h-[70vh]">
        <table className="min-w-full bg-white border border-gray-300">
          <thead className="sticky top-0 bg-teal-500 text-white">
            <tr>
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
                  className={`hover:bg-gray-100 cursor-pointer ${
                    selectedClusterIndex === index ? 'bg-teal-200' : ''
                  }`}
                  onClick={() => handleRowClick(index)}
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
                      <div className="flex justify-end">
                        <button
                          onClick={() => setSelectedClusterIndex(null)}
                          className="bg-red-500 text-white px-2 py-1 rounded-lg hover:bg-red-600"
                        >
                          Fermer
                        </button>
                      </div>
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
                            <div className="mb-4">
                              <p className="text-sm text-gray-600">
                                <strong>Rôles :</strong>
                              </p>
                              <div className="flex flex-wrap gap-2">
                                {node.isNameNode && (
                                  <span className="bg-blue-500 text-white px-2 py-1 rounded-full text-xs">
                                    Name Node
                                  </span>
                                )}
                                {node.isResourceManager && (
                                  <span className="bg-green-500 text-white px-2 py-1 rounded-full text-xs">
                                    Resource Manager
                                  </span>
                                )}
                                {node.isDataNode && (
                                  <span className="bg-purple-500 text-white px-2 py-1 rounded-full text-xs">
                                    Data Node
                                  </span>
                                )}
                              </div>
                            </div>
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