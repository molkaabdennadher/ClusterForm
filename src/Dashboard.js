import React, { useState, useEffect } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faPlay, faStop, faTerminal, faTrash, faTimes, faExchangeAlt } from '@fortawesome/free-solid-svg-icons';

const Dashboard = () => {
  const [vms, setVms] = useState([]);
  const [isMigrationModalOpen, setIsMigrationModalOpen] = useState(false);
  const [selectedVm, setSelectedVm] = useState(null);
  const [migrationData, setMigrationData] = useState({
    proxmoxIp: '',
    username: 'root',
    password: '',
  });

  useEffect(() => {
    const storedVMs = JSON.parse(localStorage.getItem('vms')) || [];
    setVms(storedVMs);
  }, []);

  const handleStart = async (vm) => {
    try {
      const response = await fetch('http://localhost:5000/start_vmprox', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          proxmox_ip: vm.proxmoxIp,
          vm_id: vm.vm_id,
          username: 'root',
          password: vm.password,
        }),
      });

      const data = await response.json();

      if (data.success) {
        alert(`VM ${vm.hostname} démarrée avec succès : ${data.message}`);
        const updatedVMs = vms.map((v) =>
          v.vm_id === vm.vm_id ? { ...v, status: 'Running' } : v
        );
        setVms(updatedVMs);
        localStorage.setItem('vms', JSON.stringify(updatedVMs));
      } else {
        alert(`Erreur lors du démarrage de la VM : ${data.message}`);
      }
    } catch (error) {
      alert(`Erreur de connexion : ${error.message}`);
    }
  };

  const handleStop = async (vm) => {
    try {
      const response = await fetch('http://localhost:5000/stop_vmprox', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          proxmox_ip: vm.proxmoxIp,
          vm_id: vm.vm_id,
          username: 'root',
          password: vm.password,
        }),
      });

      const data = await response.json();

      if (data.status === 'success') {
        alert(`VM ${vm.hostname} arrêtée avec succès : ${data.message}`);
        const updatedVMs = vms.map((v) =>
          v.vm_id === vm.vm_id ? { ...v, status: 'Stopped' } : v
        );
        setVms(updatedVMs);
        localStorage.setItem('vms', JSON.stringify(updatedVMs));
      } else {
        alert(`Erreur lors de l'arrêt de la VM : ${data.message}`);
      }
    } catch (error) {
      alert(`Erreur de connexion : ${error.message}`);
    }
  };

  const handleConsole = (vm) => {
    fetch('http://localhost:5000/open_console', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        proxmoxIp: vm.proxmoxIp,
        username: 'root',
        password: vm.password,
      }),
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          alert('Console ouverte avec succès');
        } else {
          alert(`Erreur lors de l'ouverture de la console : ${data.message}`);
        }
      })
      .catch((error) => {
        alert(`Erreur de connexion : ${error.message}`);
      });
  };

  const handleDelete = async (vm) => {
    if (window.confirm(`Are you sure you want to delete the VM ${vm.hostname}?`)) {
      try {
        const response = await fetch('http://localhost:5000/delete_vmprox', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            proxmoxIp: vm.proxmoxIp,
            vm_id: vm.vm_id,
            username: 'root',
            password: vm.password,
          }),
        });

        const data = await response.json();

        if (data.success) {
          alert(`VM ${vm.hostname} supprimée avec succès`);
          const updatedVMs = vms.filter((v) => v.vm_id !== vm.vm_id);
          setVms(updatedVMs);
          localStorage.setItem('vms', JSON.stringify(updatedVMs));
        } else {
          alert(`Erreur lors de la suppression de la VM: ${data.message}`);
        }
      } catch (error) {
        alert(`Erreur de connexion: ${error.message}`);
      }
    }
  };

  const handleMigrate = async () => {
    if (!selectedVm) return;

    try {
      const response = await fetch('http://localhost:5000/migrate_vm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          sourceProxmoxIp: selectedVm.proxmoxIp,
          targetProxmoxIp: migrationData.proxmoxIp,
          vm_id: selectedVm.vm_id,
          username: migrationData.username,
          password: migrationData.password,
        }),
      });

      const data = await response.json();

      if (data.success) {
        alert(`VM ${selectedVm.hostname} migrée avec succès vers ${migrationData.proxmoxIp}`);
        setIsMigrationModalOpen(false);
      } else {
        alert(`Erreur lors de la migration : ${data.message}`);
      }
    } catch (error) {
      alert(`Erreur de connexion : ${error.message}`);
    }
  };

  const clearLocalStorage = () => {
    localStorage.clear();
    alert('LocalStorage has been cleared.');
    setVms([]);
  };

  return (
    <div className="min-h-screen p-4 bg-gradient-to-b from-teal-100 to-white">
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Dashboard</h1>
      <button
        onClick={clearLocalStorage}
        className="bg-red-500 text-white px-4 py-2 rounded mb-4 hover:bg-red-600"
      >
        Clear LocalStorage
      </button>
      <div className="overflow-x-auto">
        <table className="min-w-full bg-white border border-gray-300">
          <thead>
            <tr className="bg-teal-500 text-white">
              <th className="py-2 px-4 border">Proxmox IP</th>
              <th className="py-2 px-4 border">Node Name</th>
              <th className="py-2 px-4 border">Proxmox Password</th>
              <th className="py-2 px-4 border">Hostname</th>
              <th className="py-2 px-4 border">ID</th>
              <th className="py-2 px-4 border">Network</th>
              <th className="py-2 px-4 border">RAM (Mo)</th>
              <th className="py-2 px-4 border">CPU</th>
              <th className="py-2 px-4 border">Template</th>
              <th className="py-2 px-4 border">Status</th>
              <th className="py-2 px-4 border">Creation Date</th>
              <th className="py-2 px-4 border">Actions</th>
            </tr>
          </thead>
          <tbody>
            {vms.map((vm, index) => (
              <tr key={index} className="hover:bg-gray-100">
                <td className="py-2 px-4 border">{vm.proxmoxIp}</td>
                <td className="py-2 px-4 border">{vm.nodeName}</td>
                <td className="py-2 px-4 border">{vm.password}</td>
                <td className="py-2 px-4 border">{vm.hostname}</td>
                <td className="py-2 px-4 border">{vm.vm_id}</td>
                <td className="py-2 px-4 border">{vm.network}</td>
                <td className="py-2 px-4 border">{vm.ram}</td>
                <td className="py-2 px-4 border">{vm.cpu}</td>
                <td className="py-2 px-4 border">{vm.template}</td>
                <td className="py-2 px-4 border">{vm.status}</td>
                <td className="py-2 px-4 border">{vm.creationDate}</td>
                <td className="py-2 px-4 border">
                  <button
                    onClick={() => handleStart(vm)}
                    className="text-green-500 hover:text-green-600 mr-2"
                    title="Start"
                  >
                    <FontAwesomeIcon icon={faPlay} />
                  </button>
                  <button
                    onClick={() => handleStop(vm)}
                    className="text-red-500 hover:text-red-600 mr-2"
                    title="Stop"
                  >
                    <FontAwesomeIcon icon={faStop} />
                  </button>
                  <button
                    onClick={() => handleConsole(vm)}
                    className="text-blue-500 hover:text-blue-600 mr-2"
                    title="Console"
                  >
                    <FontAwesomeIcon icon={faTerminal} />
                  </button>
                  <button
                    onClick={() => {
                      setSelectedVm(vm);
                      setIsMigrationModalOpen(true);
                    }}
                    className="text-purple-500 hover:text-purple-600 mr-2"
                    title="Migrer"
                  >
                    <FontAwesomeIcon icon={faExchangeAlt} />
                  </button>
                  <button
                    onClick={() => handleDelete(vm)}
                    className="text-gray-500 hover:text-gray-600"
                    title="Delete"
                  >
                    <FontAwesomeIcon icon={faTrash} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isMigrationModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="bg-white p-6 rounded-lg shadow-lg w-96">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">Migrer la VM</h2>
              <button
                onClick={() => setIsMigrationModalOpen(false)}
                className="text-gray-500 hover:text-gray-700"
              >
                <FontAwesomeIcon icon={faTimes} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Adresse IP du serveur Proxmox cible</label>
                <input
                  type="text"
                  value={migrationData.proxmoxIp}
                  onChange={(e) => setMigrationData({ ...migrationData, proxmoxIp: e.target.value })}
                  className="mt-1 block w-full border border-gray-300 rounded-md p-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Utilisateur</label>
                <input
                  type="text"
                  value={migrationData.username}
                  onChange={(e) => setMigrationData({ ...migrationData, username: e.target.value })}
                  className="mt-1 block w-full border border-gray-300 rounded-md p-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Mot de passe</label>
                <input
                  type="password"
                  value={migrationData.password}
                  onChange={(e) => setMigrationData({ ...migrationData, password: e.target.value })}
                  className="mt-1 block w-full border border-gray-300 rounded-md p-2"
                />
              </div>
              <button
                onClick={handleMigrate}
                className="w-full bg-teal-500 text-white py-2 rounded-md hover:bg-teal-600"
              >
                Migrer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;