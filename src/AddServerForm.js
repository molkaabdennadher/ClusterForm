import React, { useState } from "react";

function AddServerForm({ onAddServer, onClose }) {
  const [serverIp, setServerIp] = useState("");
  const [node, setNode] = useState("");
  const [user, setUser] = useState("root");
  const [password, setPassword] = useState("");
  const [template, setTemplate] = useState("");
  const [TempId, setTempId] = useState(""); // Nouvel état pour le champ VM ID

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Créer un nouvel objet serveur avec le champ Template et VM ID
    const newServer = {
      serverIp,
      node,
      user,
      password,
      template,
      TempId, // Ajout du champ VM ID
    };

    onAddServer(newServer); // Ajout du serveur dans l'état parent

    try {
      const response = await fetch("http://localhost:5000/add_server", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newServer), // Envoyer les données au serveur
      });

      const data = await response.json();

      if (response.ok) {
        alert("Serveur ajouté avec succès!");
      } else {
        alert("Erreur : " + data.message);
      }
    } catch (error) {
      alert("Erreur de connexion au serveur Flask");
      console.error(error);
    }

    // Réinitialisation des champs du formulaire
    setServerIp("");
    setNode("");
    setUser("root");
    setPassword("");
    setTemplate("");
    setTempId(""); // Réinitialiser le champ VM ID
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
      <div className="bg-white p-6 rounded-lg shadow-lg w-1/3">
        <h2 className="text-xl font-bold mb-4">Ajouter un serveur Proxmox</h2>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-gray-700">Adresse IP du serveur</label>
              <input
                type="text"
                value={serverIp}
                onChange={(e) => setServerIp(e.target.value)}
                className="w-full p-2 border rounded-lg"
                placeholder="Ex: 192.168.1.100"
                required
              />
            </div>
            <div>
              <label className="block text-gray-700">Node</label>
              <input
                type="text"
                value={node}
                onChange={(e) => setNode(e.target.value)}
                className="w-full p-2 border rounded-lg"
                placeholder="Ex: node1"
                required
              />
            </div>
            <div>
              <label className="block text-gray-700">User</label>
              <input
                type="text"
                value={user}
                onChange={(e) => setUser(e.target.value)}
                className="w-full p-2 border rounded-lg"
                placeholder="Ex: root"
                required
              />
            </div>
            <div>
              <label className="block text-gray-700">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full p-2 border rounded-lg"
                placeholder="Mot de passe"
                required
              />
            </div>
            <div>
              <label className="block text-gray-700">Template</label>
              <input
                type="text"
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                className="w-full p-2 border rounded-lg"
                placeholder="Ex: ubuntu-20.04-template"
                required
              />
            </div>
            <div>
              <label className="block text-gray-700">Template ID</label>
              <input
                type="text"
                value={TempId}
                onChange={(e) => setTempId(e.target.value)}
                className="w-full p-2 border rounded-lg"
                placeholder="Ex: 100"
                required
              />
            </div>
          </div>
          <div className="flex justify-end mt-6">
            <button
              type="button"
              onClick={onClose}
              className="bg-gray-500 text-white p-2 rounded-lg shadow-md hover:bg-gray-600 mr-2"
            >
              Annuler
            </button>
            <button
              type="submit"
              className="bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
            >
              Ajouter
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default AddServerForm;