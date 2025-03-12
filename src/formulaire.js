import React, { useState, useEffect } from 'react'; 
import { useLocation, useNavigate } from 'react-router-dom';

const Formulaire = () => {
  const { state } = useLocation();  // Récupère les données envoyées par DistantConfig
  const [formData, setFormData] = useState(state || JSON.parse(localStorage.getItem('vmData')));  // Utilise les données d'état ou localStorage
// États pour les limites RAM/CPU
const [maxRam, setMaxRam] = useState(0);
const [maxCpu, setMaxCpu] = useState(0);
useEffect(() => {
  const fetchLimits = async () => {
    try {
      const response = await fetch('http://localhost:5000/get_limits');
      const data = await response.json();

      if (data.max_ram && data.max_cpu) {
        setMaxRam(data.max_ram);
        setMaxCpu(data.max_cpu);
      } else {
        console.error('Erreur lors de la récupération des limites :', data.error);
      }
    } catch (error) {
      console.error('Erreur de connexion à l\'API :', error);
    }
  };

  fetchLimits();
}, []);

// Enregistrer les données du formulaire dans localStorage
useEffect(() => {
  localStorage.setItem('vmData', JSON.stringify(formData));
}, [formData]);

  const [hostname, setHostname] = useState('');
  const [ram, setRam] = useState(2048); // Valeur par défaut
  const [cpu, setCpu] = useState(1); // Valeur par défaut
  const [network, setNetwork] = useState('nat'); // Valeur par défaut
  const [template, setTemplate] = useState('ubuntu'); // Valeur par défaut


  const [proxmoxIp, setProxmoxIp] = useState(formData?.proxmoxIp || '');  // Déclare proxmoxIp
  const [nodeName, setNodeName] = useState(formData?.nodeName || '');  // Déclare nodeName
  const [password, setPassword] = useState(formData?.password || '');  // Déclare password
  const [vm_id, setVmId] = useState(formData?.vm_id || '');  // Déclare vm_id
  const [vmIp, setVmIp] = useState(formData?.vmIp || '');  // Déclare vm_ip



  const navigate = useNavigate();

  const handleCreate = async () => {
    // Crée une VM fictive avant d'attendre la réponse de l'API
    const newVM = {
      hostname,
      ram,
      cpu,
      network,
      template,
      proxmoxIp,        
      password,  
      nodeName, 
      vm_id,
      vmIp,
      status: 'Creating...', // Statut temporaire
    };

    // Ajoute cette VM à une "liste des VMs" (stockée dans l'état)
    const currentVMs = JSON.parse(localStorage.getItem('vms')) || [];
    currentVMs.push(newVM);
    localStorage.setItem('vms', JSON.stringify(currentVMs));

    // Redirige vers le dashboard (affichera la VM même avant la réponse de l'API)
    navigate('/dashboard');

    try {
      const response = await fetch('http://localhost:5000/create_vmprox', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          proxmoxIp: proxmoxIp,
          password: password,
          hostname: hostname,
          ram: parseInt(ram, 10),
          cpu: parseInt(cpu, 10),
          targetNode: nodeName,
          network: network,
          vm_id: vm_id,
        }),
      });

      if (!response.ok) {
        throw new Error('Erreur lors de la création de la VM');
      }

      const result = await response.json();
      console.log(result.message);
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    const configResponse = await fetch('http://localhost:5000/conf_vmprox', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        proxmoxIp: proxmoxIp,
        password: password,
        vm_id: vm_id,
        ram: ram,
        cpu: cpu,
        network_ip: vmIp, 
      }),
    });

    if (!configResponse.ok) {
      throw new Error('Erreur lors de la configuration de la VM');
    }

    const configResult = await configResponse.json();
    console.log(configResult.message);
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

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

        <label className="block text-sm font-medium">RAM (Mo) (max {maxRam} Mo):</label>
        <input
          type="number"
          placeholder="Enter RAM"
          value={ram}
          onChange={(e) => setRam(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
          min="512"
          max={maxRam}
        />

        <label className="block text-sm font-medium">CPU (max {maxCpu} cœurs):</label>
        <input
          type="number"
          placeholder="Enter CPU Cores"
          value={cpu}
          onChange={(e) => setCpu(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
          min="1"
          max={maxCpu}
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
