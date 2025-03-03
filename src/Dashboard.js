import React, { useState, useEffect } from "react";

const Dashboard = () => {
  const [searchTerm, setSearchTerm] = useState("");
  const [machines, setMachines] = useState([]);

  const loadMachines = () => {
    const storedMachines = JSON.parse(localStorage.getItem("vms")) || [];
    setMachines(storedMachines);
  };

  useEffect(() => {
    loadMachines();

    const handleStorageChange = () => loadMachines();
    window.addEventListener("storage", handleStorageChange);

    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  const handleStart = async (machine) => {
    try {
      const requestData = {
        mode: machine.mode || "local",
        vm_name: machine.hostname,
      };

      if (machine.mode === "distant") {
        if (!machine.remote_ip) {
          alert("Pour le mode distant, veuillez renseigner l'adresse IP de la machine distante.");
          return;
        }
        requestData.remote_ip = machine.remote_ip;
        requestData.remote_user = machine.remote_user;
        requestData.remote_password = machine.remote_password;
        requestData.remote_os = machine.remote_os;
      }

      const response = await fetch("http://localhost:5000/start-vm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData),
      });

      const data = await response.json();
      if (response.ok) {
        alert(`✅ ${data.message}`);
      } else {
        alert(`❌ Erreur: ${data.error}`);
      }
    } catch (error) {
      console.error("Erreur de requête:", error);
      alert("Erreur lors de la communication avec le serveur.");
    }
  };

  const handleStop = async (machine) => {
    try {
      const requestData = {
        mode: machine.mode || "local",
        vm_name: machine.hostname,
      };

      if (machine.mode === "distant") {
        if (!machine.remote_ip) {
          alert("Pour le mode distant, veuillez renseigner l'adresse IP de la machine distante.");
          return;
        }
        requestData.remote_ip = machine.remote_ip;
        requestData.remote_user = machine.remote_user;
        requestData.remote_password = machine.remote_password;
        requestData.remote_os = machine.remote_os;
      }

      const response = await fetch("http://localhost:5000/stop-vm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData),
      });

      const data = await response.json();
      if (response.ok) {
        alert(`✅ ${data.message}`);
      } else {
        alert(`❌ Erreur: ${data.error}`);
      }
    } catch (error) {
      console.error("Erreur de requête:", error);
      alert("Erreur lors de la communication avec le serveur.");
    }
  };

  const handleDelete = async (machine, index) => {
    try {
      const vmName = machine.hostname;
      if (!vmName) {
        alert("Erreur: Le nom de la VM n'est pas défini.");
        return;
      }

      const requestData = {
        mode: machine.mode || "local",
        vm_name: vmName,
      };

      if (machine.mode === "distant") {
        if (!machine.remote_ip) {
          alert("Pour le mode distant, veuillez renseigner l'adresse IP de la machine distante.");
          return;
        }
        requestData.remote_ip = machine.remote_ip;
        requestData.remote_user = machine.remote_user;
        requestData.remote_password = machine.remote_password;
        requestData.remote_os = machine.remote_os;
      }

      const response = await fetch("http://localhost:5000/delete-vm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData),
      });

      const data = await response.json();
      if (response.ok) {
        alert(`✅ ${data.message}`);
        const updatedMachines = machines.filter((_, idx) => idx !== index);
        localStorage.setItem("vms", JSON.stringify(updatedMachines));
        setMachines(updatedMachines);
      } else {
        alert(`❌ Erreur: ${data.error}`);
      }
    } catch (error) {
      console.error("Erreur de requête:", error);
      alert("Erreur lors de la communication avec le serveur.");
    }
  };

  const handleOpenTerminal = async (machine) => {
    try {
      const requestData = {
        mode: machine.mode || "local",
        vm_name: machine.hostname,
      };

      if (machine.mode === "distant") {
        if (!machine.remote_ip) {
          alert("Pour le mode distant, veuillez renseigner l'adresse IP de la machine distante.");
          return;
        }
        requestData.remote_ip = machine.remote_ip;
        requestData.remote_user = machine.remote_user;
        requestData.remote_password = machine.remote_password;
        requestData.remote_os = machine.remote_os;
      }

      const response = await fetch("http://localhost:5000/open-terminal-vm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData),
      });

      const data = await response.json();
      if (response.ok) {
        alert(`SSH Configuration:\n${data.sshConfig}`);
      } else {
        alert(`❌ Erreur: ${data.error}`);
      }
    } catch (error) {
      console.error("Erreur de requête:", error);
      alert("Erreur lors de la communication avec le serveur.");
    }
  };

  const filteredMachines = machines.filter((machine) =>
    machine.hostname.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="p-6 bg-gradient-to-b from-teal-100 to-white min-h-screen">
      <h1 className="text-4xl font-bold text-center text-teal-600">Dashboard</h1>
      <div className="flex justify-end p-4">
        <input
          type="text"
          placeholder="Search..."
          className="p-2 border rounded-md"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>
      <table className="min-w-full border-collapse border border-gray-300 rounded-lg">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-3 border">Host Name</th>
            <th className="p-3 border">Box</th>
            <th className="p-3 border">Network</th>
            <th className="p-3 border">RAM</th>
            <th className="p-3 border">CPU</th>
            <th className="p-3 border">Date of Creation</th>
            <th className="p-3 border">SSH Address</th>
            <th className="p-3 border">Mode</th>
            <th className="p-3 border">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredMachines.map((machine, index) => (
            <tr key={index} className="text-center border-b">
              <td className="p-3 border">{machine.hostname}</td>
              <td className="p-3 border">{machine.box}</td>
              <td className="p-3 border">{machine.network}</td>
              <td className="p-3 border">{machine.ram}</td>
              <td className="p-3 border">{machine.cpu}</td>

              <td className="p-3 border">{machine.date}</td>
              <td className="p-3 border">{`${machine.ipAddress}:${machine.port}`}</td>
              <td className="p-3 border">{machine.mode}</td>
              <td className="p-3 border flex justify-around">
                <button onClick={() => handleStart(machine)} className="text-green-500 hover:text-green-700">
                  ▶
                </button>
                <button onClick={() => handleStop(machine)} className="text-yellow-500 hover:text-yellow-700">
                  ■
                </button>
                <button onClick={() => handleOpenTerminal(machine)} className="text-blue-500 hover:text-blue-700">
                  ⎘
                </button>
                <button onClick={() => handleDelete(machine, index)} className="text-red-500 hover:text-red-700">
                  ✖
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Dashboard;