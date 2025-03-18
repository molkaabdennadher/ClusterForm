import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const DistantConfig = () => {
  const [proxmoxIp, setProxmoxIp] = useState('');
  const [nodeName, setNodeName] = useState('');
  const [user, setUser] = useState('root'); // Champ utilisateur prédéfini sur 'root'
  const [password, setPassword] = useState('');
  const [vm_id, setVmId] = useState(''); // Ajout de l'état pour VM ID
  const navigate = useNavigate();

  const handleSubmit = () => {
    // Crée un objet avec les données
    const vmData = {
      proxmoxIp,
      nodeName,
      user,
      password,
      vm_id
    };

    // Sauvegarde les données dans localStorage
    localStorage.setItem('vmData', JSON.stringify(vmData));

    // Navigue vers le formulaire avec les données sauvegardées
    navigate('/formulaire', { state: vmData });
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
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Distant Mode</h1>
      <div className="bg-white p-6 rounded-lg shadow-lg w-96">
        <label className="block text-sm font-medium">Proxmox IP:</label>
        <input
          type="text"
          placeholder="Enter Proxmox IP"
          value={proxmoxIp}
          onChange={(e) => setProxmoxIp(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">Node Name:</label>
        <input
          type="text"
          placeholder="Enter Proxmox Node Name"
          value={nodeName}
          onChange={(e) => setNodeName(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">User:</label>
        <input
          type="text"
          placeholder="Enter User"
          value={user}
          onChange={(e) => setUser(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">Password:</label>
        <input
          type="password"
          placeholder="Enter Proxmox Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

      <label className="block text-sm font-medium">VM ID:</label>
        <input
          type="number" // Utiliser type="number" pour les champs numériques
          name="vm_id"
          placeholder="Enter VM ID"
          value={vm_id}
          onChange={(e) => setVmId(e.target.value)} // Ne pas convertir en Number, gérer la conversion plus tard
          className="w-full p-2 border rounded mb-4"
          required
        />

        <button
          type="button"
          onClick={handleSubmit}
          className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Connect
        </button>
      </div>
    </div>
  );
};

export default DistantConfig;
