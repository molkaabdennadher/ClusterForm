import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const CloneTemplate = () => {
  const navigate = useNavigate();

  // États pour stocker les données du formulaire
  const [sourceProxmoxIp, setSourceProxmoxIp] = useState("");
  const [targetProxmoxIp, setTargetProxmoxIp] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [username, setUsername] = useState("root");
  const [password, setPassword] = useState("");
  const [storage, setStorage] = useState("local");
  const [message, setMessage] = useState("");

  // Fonction pour gérer la soumission du formulaire
  const handleSubmit = async (e) => {
    e.preventDefault();
    navigate("/formulaire");

    const data = {
      sourceProxmoxIp,
      targetProxmoxIp,
      template_id: templateId,
      username,
      password,
      storage,
    };

    try {
      const response = await fetch("http://localhost:5000/clone_template", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });

      const result = await response.json();

      if (result.success) {
        setMessage({ type: "success", text: `Succès : ${result.message}` });
        
      } else {
        setMessage({ type: "error", text: `Erreur : ${result.message}` });
      }
    } catch (error) {
      setMessage({ type: "error", text: `Erreur de connexion : ${error.message}` });
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      {/* Bouton de navigation vers le Dashboard */}
      <div className="absolute top-4 right-4">
        <button
          onClick={() => navigate("/dashboard")}
          className="bg-teal-500 text-white px-4 py-2 rounded-lg shadow-md hover:bg-teal-600"
        >
          Dashboard
        </button>
      </div>

      <h1 className="text-4xl font-bold text-teal-600 mb-6">Cloner un Template Proxmox</h1>

      <div className="bg-white p-6 rounded-lg shadow-lg w-96">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium">Adresse IP du serveur source :</label>
            <input
              type="text"
              value={sourceProxmoxIp}
              onChange={(e) => setSourceProxmoxIp(e.target.value)}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium">Adresse IP du serveur cible :</label>
            <input
              type="text"
              value={targetProxmoxIp}
              onChange={(e) => setTargetProxmoxIp(e.target.value)}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium">ID du template :</label>
            <input
              type="text"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium">Nom d'utilisateur SSH :</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium">Mot de passe SSH :</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full p-2 border rounded"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium">Stockage cible (optionnel) :</label>
            <input
              type="text"
              value={storage}
              onChange={(e) => setStorage(e.target.value)}
              className="w-full p-2 border rounded"
            />
          </div>

          <button type="submit" className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600">
            Cloner le template
          </button>
        </form>

        {/* Message de réponse */}
        {message && (
          <div
            className={`mt-4 p-4 rounded-lg shadow-md ${
              message.type === "success" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
            }`}
          >
            {message.text}
          </div>
        )}
      </div>
    </div>
  );
};

export default CloneTemplate;
