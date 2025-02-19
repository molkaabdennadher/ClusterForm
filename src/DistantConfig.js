import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const DistantConfig = () => {
  // États d'origine
  const [ip, setIp] = useState("");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [remote_os, setOs] = useState("Windows");
  const [hypervisor, setHypervisor] = useState("VirtualBox");
  const navigate = useNavigate();

  const handleSubmit = () => {
    if (!ip || !login || !password) {
      alert("Veuillez remplir tous les champs !");
      return;
    }
    // Navigation vers le formulaire en transmettant les infos de connexion distante
    navigate("/formulaire", {
      state: {
        remote_ip: ip,
        remote_user: login,
        remote_password: password,
        remote_os,
        hypervisor,
        mode: "distant"
      }
    });
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
        <label className="block text-sm font-medium">IP Address:</label>
        <input
          type="text"
          placeholder="Enter the IP address"
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">Username:</label>
        <input
          type="text"
          placeholder="Enter the username"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">Password:</label>
        <input
          type="password"
          placeholder="Enter the password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-2 border rounded mb-4"
          required
        />

        <label className="block text-sm font-medium">OS:</label>
        <select
          value={remote_os}
          onChange={(e) => setOs(e.target.value)}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="Windows">Windows</option>
          <option value="Linux">Linux</option>
        </select>

        <label className="block text-sm font-medium">Hypervisor:</label>
        <select
          value={hypervisor}
          onChange={(e) => setHypervisor(e.target.value)}
          className="w-full p-2 border rounded mb-4"
        >
          <option value="VirtualBox">VirtualBox</option>
          <option value="VMware">VMware Workstation Pro</option>
        </select>

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

