import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import OSVersionSelect from './OSVersionSelect'; // Assurez-vous d'importer le composant
import CustomBox from './CustomBox'; 

export default function Formulaire() {
  const [hostname, setHostname] = useState("");
  const [ram, setRam] = useState(2);
  const [customBoxes, setCustomBoxes] = useState(() => {
    // Récupérer les boxes personnalisées depuis localStorage
    const savedBoxes = localStorage.getItem("customBoxes");
    return savedBoxes ? JSON.parse(savedBoxes) : []; // Si aucune box n'est trouvée, retourner un tableau vide
  });
  const [totalMemoryGB, setMaxRam] = useState(16);
  const [cpu, setCpu] = useState(1);
  const [maxCpu, setMaxCpu] = useState(8);
  const [network, setNetwork] = useState("NAT");
  const [submitted, setSubmitted] = useState(false);
  const [ipAddress, setIpAddress] = useState("");
  const [port, setPort] = useState("");
  const [osVersion, setOsVersion] = useState("ubuntu/trusty64");
  const navigate = useNavigate();
  const location = useLocation();
  const [isCustomBoxOpen, setIsCustomBoxOpen] = useState(false);
  const [customRam, setCustomRam] = useState(4);
  const [customCpu, setCustomCpu] = useState(2);
  const [osOptions, setOsOptions] = useState(() => {
    const savedOptions = localStorage.getItem("osOptions");
    return savedOptions ? JSON.parse(savedOptions) : ["ubuntu/trusty64", "ubuntu-focal", "ubuntu-bionic"];
  });

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


  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === "osOptions") {
        setOsOptions(JSON.parse(e.newValue));
      }
    };

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);


  const handleNodeDetailsChange = (field, value) => {
    if (field === "osVersion") {
      setOsVersion(value);
      if (value === "Box-perso") {
        setIsCustomBoxOpen(true);
      } else {
        setIsCustomBoxOpen(false);
      }
    }
  };
  const handleAddCustomBox = ({ name, ram, cpu }) => {
    const updatedBoxes = [...customBoxes, { name, ram, cpu }];
    const updatedOptions = [...osOptions, name];

    setCustomBoxes(updatedBoxes);
    setOsOptions(updatedOptions);

    // Mettre à jour localStorage
    localStorage.setItem("customBoxes", JSON.stringify(updatedBoxes));
    localStorage.setItem("osOptions", JSON.stringify(updatedOptions));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!hostname.trim()) {
      alert("Le champ Hostname est requis.");
      return;
    }

    const requestData = {
      vm_name: hostname,
      box: osVersion,
      ram: ram,
      cpu: cpu,
      network: network,
      customBoxes: customBoxes,
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
          box: osVersion,
          network: network,
          ram: `${ram} GB`,
          cpu: `${cpu} vCPUs`,
          status: "Running",
          date: new Date().toLocaleDateString(),
          ipAddress: data.ipAddress,
          port: data.port,
          mode: remoteConfig.mode || "local"
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
          <OSVersionSelect
            value={osVersion}
            onChange={(value) => handleNodeDetailsChange("osVersion", value)}
            onCustomBoxSelect={setIsCustomBoxOpen}
            options={osOptions}
          />
          {isCustomBoxOpen && (
            <CustomBox
              ram={customRam}
              cpu={customCpu}
              onRamChange={setCustomRam}
              onCpuChange={setCustomCpu}
              onClose={() => setIsCustomBoxOpen(false)}
              onAddBox={handleAddCustomBox}
            />
          )}

        

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
