import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const Formulaire = () => {
  const location = useLocation();
  const { proxmoxIp, nodeName, user, password } = location.state || {};

  const [hostname, setHostname] = useState('');
  const [ram, setRam] = useState(2048); // Valeur par défaut
  const [cpu, setCpu] = useState(1); // Valeur par défaut
  const [network, setNetwork] = useState('nat'); // Valeur par défaut
  const [template, setTemplate] = useState('ubuntu'); // Valeur par défaut

  const navigate = useNavigate();

  const handleCreate = async () => {
    // Crée une VM fictive avant d'attendre la réponse de l'API
    const newVM = {
      hostname,
      ram,
      cpu,
      network,
      template,
      status: 'Creating...', // Statut temporaire
    };

    // Ajoute cette VM à une "liste des VMs" (stockée dans l'état)
    const currentVMs = JSON.parse(localStorage.getItem('vms')) || [];
    currentVMs.push(newVM);
    localStorage.setItem('vms', JSON.stringify(currentVMs));

    // Redirige vers le dashboard (affichera la VM même avant la réponse de l'API)
    navigate('/dashboard');

    try {
      const response = await fetch('http://localhost:5000/create_vm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          proxmoxIp: proxmoxIp,
          proxmoxPassword: password,
          hostname: hostname,
          ram: parseInt(ram, 10),
          cpu: parseInt(cpu, 10),
          targetNode: nodeName,
          network: network,
        }),
      });

      if (!response.ok) {
        throw new Error('Erreur lors de la création de la VM');
      }

      const result = await response.json();
      console.log(result.message);

      // Si la création de la VM réussit, mettez à jour son statut dans la liste
      const updatedVMs = currentVMs.map((vm) =>
        vm.hostname === hostname ? { ...vm, status: 'Created' } : vm
      );
      localStorage.setItem('vms', JSON.stringify(updatedVMs));
    } catch (error) {
      console.error('Erreur:', error);
      // Si l'API échoue, vous pouvez également mettre à jour le statut de la VM en "Erreur"
      const updatedVMs = currentVMs.map((vm) =>
        vm.hostname === hostname ? { ...vm, status: 'Error' } : vm
      );
      localStorage.setItem('vms', JSON.stringify(updatedVMs));
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <div className="absolute top-4 right-4">
        <button
          onClick={() => navigate("/dashboard")}
          className="bg-teal-500 text-white px-4 py-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Dashboard
        </button>
      </div>
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Create VM</h1>
      <div className="bg-white p-6 rounded-lg shadow-lg w-96">
        <label className="block text-sm font-medium">Hostname:</label>
        <input
          type="text"
          placeholder="Enter Hostname"
          value={hostname}
          onChange={(e) => setHostname(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">RAM (Mo):</label>
        <input
          type="number"
          placeholder="Enter RAM"
          value={ram}
          onChange={(e) => setRam(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">CPU:</label>
        <input
          type="number"
          placeholder="Enter CPU Cores"
          value={cpu}
          onChange={(e) => setCpu(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">Network:</label>
        <select
          value={network}
          onChange={(e) => setNetwork(e.target.value)}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="nat">NAT</option>
          <option value="bridged">Bridged</option>
          <option value="private">Private Network</option>
        </select>

        <label className="block text-sm font-medium">Template:</label>
        <select
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="ubuntu">Ubuntu</option>
          <option value="windows">Windows</option>
        </select>

        <button
          type="button"
          onClick={handleCreate}
          className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Create
        </button>
      </div>
    </div>
  );
};

export default Formulaire;
