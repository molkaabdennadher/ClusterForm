import React, { useState, useEffect } from 'react';

const Dashboard = () => {
  const [vms, setVms] = useState([]);

  useEffect(() => {
    // Récupérer les VMs depuis localStorage lors du montage du composant
    const storedVMs = JSON.parse(localStorage.getItem('vms')) || [];
    setVms(storedVMs);
  }, []);

  const handleStart = (vm) => {
    // Logique pour démarrer la VM
    const updatedVMs = vms.map((v) =>
      v.hostname === vm.hostname ? { ...v, status: 'Running' } : v
    );
    setVms(updatedVMs);
    localStorage.setItem('vms', JSON.stringify(updatedVMs));
    console.log(`Starting VM: ${vm.hostname}`);
  };

  const handleStop = (vm) => {
    // Logique pour arrêter la VM
    const updatedVMs = vms.map((v) =>
      v.hostname === vm.hostname ? { ...v, status: 'Stopped' } : v
    );
    setVms(updatedVMs);
    localStorage.setItem('vms', JSON.stringify(updatedVMs));
    console.log(`Stopping VM: ${vm.hostname}`);
  };

  const handleConsole = (ip) => {
    // Ouvrir le terminal SSH
    window.open(`ssh://user@${ip}`, '_blank'); // Remplacez 'user' par le nom d'utilisateur approprié
    console.log(`Connecting to VM via SSH: ssh://user@${ip}`);
  };

  const handleDelete = (hostname) => {
    // Demander une confirmation avant de supprimer la VM
    if (window.confirm(`Are you sure you want to delete the VM ${hostname}?`)) {
      const updatedVMs = vms.filter(vm => vm.hostname !== hostname);
      setVms(updatedVMs);
      localStorage.setItem('vms', JSON.stringify(updatedVMs));
      console.log(`Deleted VM: ${hostname}`);
    }
  };

  return (
    <div className="min-h-screen p-4 bg-gradient-to-b from-teal-100 to-white">
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Dashboard</h1>
      <div className="overflow-x-auto">
        <table className="min-w-full bg-white border border-gray-300">
          <thead>
            <tr className="bg-teal-500 text-white">
              <th className="py-2 px-4 border">Hostname</th>
              <th className="py-2 px-4 border">Template</th>
              <th className="py-2 px-4 border">Network</th>
              <th className="py-2 px-4 border">RAM (Mo)</th>
              <th className="py-2 px-4 border">CPU</th>
              <th className="py-2 px-4 border">Status</th>
              <th className="py-2 px-4 border">Creation Date</th>
              <th className="py-2 px-4 border">Actions</th>
            </tr>
          </thead>
          <tbody>
            {vms.map((vm, index) => (
              <tr key={index} className="hover:bg-gray-100">
                <td className="py-2 px-4 border">{vm.hostname}</td>
                <td className="py-2 px-4 border">{vm.template}</td>
                <td className="py-2 px-4 border">{vm.network}</td>
                <td className="py-2 px-4 border">{vm.ram}</td>
                <td className="py-2 px-4 border">{vm.cpu}</td>
                <td className="py-2 px-4 border">{vm.status}</td>
                <td className="py-2 px-4 border">{vm.creationDate}</td>
                <td className="py-2 px-4 border">
                  <button
                    onClick={() => handleStart(vm)}
                    className="bg-green-500 text-white px-2 py-1 rounded mr-2 hover:bg-green-600"
                  >
                    Start
                  </button>
                  <button
                    onClick={() => handleStop(vm)}
                    className="bg-red-500 text-white px-2 py-1 rounded mr-2 hover:bg-red-600"
                  >
                    Stop
                  </button>
                  <button
                    onClick={() => handleConsole(vm.ip)}
                    className="bg-blue-500 text-white px-2 py-1 rounded mr-2 hover:bg-blue-600"
                  >
                    Console
                  </button>
                  <button
                    onClick={() => handleDelete(vm.hostname)}
                    className="bg-gray-500 text-white px-2 py-1 rounded hover:bg-gray-600"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Dashboard;
