import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";

export default function Formulaire() {
  const [hostname, setHostname] = useState("");
  const [box, setBox] = useState("ubuntu/trusty64");
  const [ram, setRam] = useState(2);
  const [totalMemoryGB, setMaxRam] = useState(16);
  const [cpu, setCpu] = useState(1);
  const [maxCpu, setMaxCpu] = useState(8);
  const [network, setNetwork] = useState("NAT");
  const [submitted, setSubmitted] = useState(false);
  const [ipAddress, setIpAddress] = useState("");
  const [port, setPort] = useState("");

  const navigate = useNavigate();
  const location = useLocation();
  const remoteConfig = location.state || {};
  const isRemote = remoteConfig.mode === "distant";

  useEffect(() => {
    if (!isRemote) {
      fetch("http://localhost:5000/get-cpu-info")
        .then((res) => res.json())
        .then((data) => {
          if (data.maxCpu) setMaxCpu(data.maxCpu);
          if (data.totalMemoryGB) setMaxRam(data.totalMemoryGB);
          console.log("System info:", data);
        })
        .catch((err) => console.error("Erreur lors de la récupération des infos système:", err));
    }
    else {
      console.log("Mode distant");
      // Pour le mode distant, on appelle l'endpoint pour récupérer les infos système de la machine distante.
      fetch("http://localhost:5000/get-remote-cpu-info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          remote_ip: remoteConfig.remote_ip,
          remote_user: remoteConfig.remote_user,
          remote_password: remoteConfig.remote_password,
          remote_os: remoteConfig.remote_os,
        }),
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.maxCpu) setMaxCpu(data.maxCpu);
          if (data.totalMemoryGB) setMaxRam(data.totalMemoryGB);
          console.log("Remote system info:", data);
        })
        .catch((err) =>
          console.error("Erreur lors de la récupération des infos système distantes:", err)
        ); }
      
  }, [isRemote]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!hostname.trim()) {
      alert("Le champ Hostname est requis.");
      return;
    }

    const requestData = {
      vm_name: hostname,
      box: box,
      ram: ram,
      cpu: cpu,
      network: network
    };

    if (isRemote) {
      requestData.remote_ip = remoteConfig.remote_ip;
      requestData.remote_password = remoteConfig.remote_password;
      requestData.mail = remoteConfig.mail; 
      requestData.remote_user = remoteConfig.remote_user; // Transmet le login reçu depuis DistantConfig
      requestData.remote_os = remoteConfig.remote_os;
      requestData.hypervisor = remoteConfig.hypervisor;
    }

    try {
      const endpoint = isRemote
        ? "http://localhost:5000/create-vm-remote"
        : "http://localhost:5000/create-vm";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData),
      });
      const data = await response.json();

      if (response.ok) {
        setIpAddress(data.ipAddress);
        setPort(data.port);
        setSubmitted(true);

        const newMachine = {
          hostname: hostname,
          box: box,
          network: network,
          ram: `${ram} GB`,
          cpu: `${cpu} vCPUs`,
          status: "Running",
          date: new Date().toLocaleDateString(),
          ipAddress: data.ipAddress,
          port: data.port
        };

        const storedMachines = JSON.parse(localStorage.getItem("vms")) || [];
        const updatedMachines = [...storedMachines, newMachine];
        localStorage.setItem("vms", JSON.stringify(updatedMachines));
        window.dispatchEvent(new Event("storage"));
      } else {
        alert(`❌ Erreur: ${data.error}`);
      }
    } catch (error) {
      console.error("Erreur de requête:", error);
      alert("Erreur lors de la communication avec le serveur.");
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
      <h1 className="text-4xl font-bold text-teal-600 mb-6">
        Create a Virtual Machine ({isRemote ? "Distant Mode" : "Local Mode"})
      </h1>
      {!submitted ? (
        <form onSubmit={handleSubmit} className="bg-white p-6 rounded-lg shadow-lg w-96">
          <label className="block text-sm font-medium">Host name:</label>
          <input
            type="text"
            value={hostname}
            onChange={(e) => setHostname(e.target.value)}
            placeholder="Enter your host name"
            className="w-full p-2 border rounded mb-4"
            required
          />

          <label className="block text-sm font-medium">Box:</label>
          <select
            value={box}
            onChange={(e) => setBox(e.target.value)}
            className="w-full p-2 border rounded mb-4"
          >
            <option>ubuntu/trusty64</option>
            <option>laravel/homestead</option>
            <option>hashicorp/precise64</option>
            <option>centos/7</option>
            <option>debian/jessie64</option>
            <option>hashicorp/precise32</option>
            <option>scotch/box</option>
          </select>

          <label className="block text-sm font-medium">RAM: {ram} GB</label>
          <input
            type="range"
            min="2"
            max={totalMemoryGB}
            step="2"
            value={ram}
            onChange={(e) => setRam(Number(e.target.value))}
            className="w-full mb-4"
          />

          <label className="block text-sm font-medium">CPU: {cpu} vCPUs</label>
          <input
            type="range"
            min="1"
            max={maxCpu} // la valeur maximale récupérée du back
            step="1"
            value={cpu}
            onChange={(e) => setCpu(Number(e.target.value))}
          />

          <label className="block text-sm font-medium">Network:</label>
          <select
            value={network}
            onChange={(e) => setNetwork(e.target.value)}
            className="w-full p-2 border rounded mb-4"
          >
            <option>NAT</option>
            <option>Bridged Adapter</option>
            <option>Internal Network</option>
            <option>Host-only Adapter</option>
          </select>

          <button type="submit" className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600">
            Create
          </button>
        </form>
      ) : (
        <div className="success-message text-center mt-6">
          <h2 className="text-2xl font-bold text-teal-600">✅ Machine created successfully!</h2>
          <p className="text-lg text-gray-700">SSH address: {ipAddress}:{port}</p>
          <p className="text-gray-600">Utilisez cette adresse pour vous connecter via SSH.</p>
        </div>
      )}
    </div>
  );
}
