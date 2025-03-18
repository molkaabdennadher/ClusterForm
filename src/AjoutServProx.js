import AddServerForm from "./AddServerForm"; 
import React, { useState } from "react"; 
import { useNavigate } from "react-router-dom"; 
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"; 
import { faPlay, faStop, faPlus } from "@fortawesome/free-solid-svg-icons"; 

function AjoutServProx() {
  const [servers, setServers] = useState(() => {
    const savedServers = localStorage.getItem("servers");
    return savedServers ? JSON.parse(savedServers) : []; // Retourne un tableau vide par défaut
  });
  const [showAddServerForm, setShowAddServerForm] = useState(false); 
  const [selectedServer, setSelectedServer] = useState(null); 
  const navigate = useNavigate();

  const startServer = (id) => {
    setServers((prevServers) => {
      const updatedServers = prevServers.map((server) =>
        server.id === id ? { ...server, status: "running" } : server
      );
      localStorage.setItem("servers", JSON.stringify(updatedServers));
      return updatedServers;
    });
  };

  const stopServer = (id) => {
    setServers((prevServers) => {
      const updatedServers = prevServers.map((server) =>
        server.id === id ? { ...server, status: "stopped" } : server
      );
      localStorage.setItem("servers", JSON.stringify(updatedServers));
      return updatedServers;
    });
  };

  const addServer = (newServer) => {
    setServers((prevServers) => {
      const updatedServers = [...prevServers, { ...newServer, id: Date.now() }];
      localStorage.setItem("servers", JSON.stringify(updatedServers));
      return updatedServers;
    });
    setShowAddServerForm(false);
  };

  const handleNext = () => {
    navigate("/option-select", { state: { hypervisor: "Proxmox" } });
  };

  const handlePrevious = () => {
    navigate("/");
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="bg-white p-10 rounded-lg shadow-xl w-3/4 max-w-4xl">
        <h1 className="text-5xl font-bold text-teal-600 mb-10">Proxmox Server</h1>
        <div className="flex justify-end mb-6">
          <button
            onClick={() => setShowAddServerForm(true)}
            className="flex items-center bg-teal-500 text-white p-3 rounded-lg shadow-md hover:bg-teal-600"
          >
            <FontAwesomeIcon icon={faPlus} className="mr-2" />
          </button>
        </div>
        {showAddServerForm && <AddServerForm onAddServer={addServer} onClose={() => setShowAddServerForm(false)} />}
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border-collapse border border-gray-300">
            <thead className="bg-teal-500 text-white">
              <tr>
                <th className="px-6 py-4 border-b text-left">Server IP</th>
                <th className="px-6 py-4 border-b text-left">Node</th>
                <th className="px-6 py-4 border-b text-left">User</th>
                <th className="px-6 py-4 border-b text-left">Password</th>
                <th className="px-6 py-4 border-b text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {servers.map((server) => (
                <tr
                  key={server.id}
                  className={`cursor-pointer ${selectedServer?.id === server.id ? "bg-teal-100" : ""} hover:bg-teal-50`}
                  onClick={() => setSelectedServer(server)}
                >
                  <td className="px-6 py-4 border-b">{server.serverIp}</td>
                  <td className="px-6 py-4 border-b">{server.node}</td>
                  <td className="px-6 py-4 border-b">{server.user}</td>
                  <td className="px-6 py-4 border-b">{server.password}</td>
                  <td className="px-6 py-4 border-b text-center">
                    {server.status === "stopped" ? (
                      <button onClick={() => startServer(server.id)} className="text-green-500 hover:text-green-700">
                        <FontAwesomeIcon icon={faPlay} />
                      </button>
                    ) : (
                      <button onClick={() => stopServer(server.id)} className="text-red-500 hover:text-red-700">
                        <FontAwesomeIcon icon={faStop} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex justify-between mt-6">
          <button onClick={handlePrevious} className="flex items-center bg-gray-500 text-white p-3 rounded-lg shadow-md hover:bg-gray-600">Back</button>
          <button onClick={handleNext} className="bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600">Next</button>
        </div>
      </div>
    </div>
  );
}

export default AjoutServProx;
