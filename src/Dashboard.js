import React, { useState, useEffect } from 'react';

const Dashboard = () => {
  const [vms, setVms] = useState([]);

  useEffect(() => {
    // Récupérer les VMs depuis localStorage lors du montage du composant
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
          proxmox_ip: vm.proxmoxIp, // Adresse IP de Proxmox (déjà enregistrée)
          vm_id: vm.vm_id,           // ID de la VM à démarrer
          username: 'root',         // Utilisateur root pour SSH (ou remplace par une variable)
          password: vm.password,    // Mot de passe (assure-toi de le sécuriser)
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
  
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const handleStop = async (vm) => {
    try {
      const response = await fetch('http://localhost:5000/stop_vmprox', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          proxmox_ip: vm.proxmoxIp, // Adresse IP de Proxmox
          vm_id: vm.vm_id,          // ID de la VM à arrêter
          username: 'root',         // Utilisateur root pour SSH
          password: vm.password,    // Mot de passe (assure-toi de le sécuriser)
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
  ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
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
  ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
 ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const handleDelete = async (vm) => {
    // Demander une confirmation avant de supprimer la VM
    if (window.confirm(`Are you sure you want to delete the VM ${vm.hostname}?`)) {
      console.log({
        proxmox_ip: vm.proxmox_ip,
        vm_id: vm.vm_id,
        username: 'root',
        password: vm.password
      });  // Affiche les données avant d'envoyer la requête
  
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
  }
  
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  

  return (
    <div className="min-h-screen p-4 bg-gradient-to-b from-teal-100 to-white">
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Dashboard</h1>
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
                <td className="py-2 px-4 border">{vm.password}</td>
                <td className="py-2 px-4 border">{vm.nodeName}</td>
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
                    onClick={() => handleConsole(vm)}
                    className="bg-blue-500 text-white px-2 py-1 rounded mr-2 hover:bg-blue-600"
                  >
                    Console
                  </button>
                  <button
                    onClick={() => handleDelete(vm)}
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
