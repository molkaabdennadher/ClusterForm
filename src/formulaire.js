import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Formulaire() {
  const [hostname, setHostname] = useState("");
  const [box, setBox] = useState("ubuntu/trusty64");
  const [ram, setRam] = useState(2);
  const [cpu, setCpu] = useState(1);
  const [network, setNetwork] = useState("NAT");
  const [submitted, setSubmitted] = useState(false);
  const [ipAddress, setIpAddress] = useState("");
  const [port, setPort] = useState("");

  const navigate = useNavigate();

  const generateIpAddress = () => {
    return `192.168.1.${Math.floor(Math.random() * 100) + 1}`;
  };

  const generatePort = () => {
    return Math.floor(Math.random() * (65535 - 2000) + 2000).toString();
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!hostname.trim()) {
      alert("Le champ Hostname est requis.");
      return;
    }

    const newIp = generateIpAddress();
    const newPort = generatePort();

    const storedMachines = JSON.parse(localStorage.getItem("vms")) || [];

    const newMachine = {
      hostname,
      box,
      ram: `${ram} GB`,
      cpu: `${cpu} vCPUs`,
      network,
      status: "Running",
      date: new Date().toLocaleDateString(),
      ipAddress: newIp,
      port: newPort,
    };

    const updatedMachines = [...storedMachines, newMachine];

    localStorage.setItem("vms", JSON.stringify(updatedMachines));
    window.dispatchEvent(new Event("storage"));

    setIpAddress(newIp);
    setPort(newPort);
    setSubmitted(true);
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
      <h1 className="text-4xl font-bold text-teal-600 mb-6">Create a Virtual Machine</h1>
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
            max="16"
            step="2"
            value={ram}
            onChange={(e) => setRam(Number(e.target.value))}
            className="w-full mb-4"
          />

          <label className="block text-sm font-medium">CPU: {cpu} vCPUs</label>
          <input
            type="range"
            min="1"
            max="8"
            step="1"
            value={cpu}
            onChange={(e) => setCpu(Number(e.target.value))}
            className="w-full mb-4"
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
          <p className="text-gray-600">22 (guest) =&gt; {port} (host)</p>
        </div>
      )}
    </div>
  );
}
