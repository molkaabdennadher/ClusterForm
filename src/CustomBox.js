import React, { useState } from 'react';

const CustomBox = ({ ram, cpu, onRamChange, onCpuChange, onClose, onAddBox }) => {
    const [boxName, setBoxName] = useState("");

    const handleAddBox = () => {
        if (boxName.trim()) {
            // Appelle la fonction pour ajouter la box avec tous les détails
            onAddBox({ name: boxName, ram, cpu });
            setBoxName(""); // Réinitialise le champ de nom de box
        } else {
            alert("Le nom de la box est requis.");
        }
    };

    return (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white p-6 rounded-lg shadow-lg w-96">
                <h2 className="text-lg font-bold mb-4">Configuration Personnalisée</h2>
                <label className="block text-sm font-medium">Nom de la Box:</label>
                <input
                    type="text"
                    value={boxName}
                    onChange={(e) => setBoxName(e.target.value)}
                    className="w-full p-2 border rounded mb-4"
                    required
                />
                <label className="block text-sm font-medium mb-2">RAM: {ram} GB</label>
                <input
                    type="range"
                    min="2"
                    max="16"
                    step="2"
                    value={ram}
                    onChange={(e) => onRamChange(Number(e.target.value))}
                    className="w-full mb-4"
                />

                <label className="block text-sm font-medium mb-2">CPU: {cpu} vCPUs</label>
                <input
                    type="range"
                    min="1"
                    max="8"
                    step="1"
                    value={cpu}
                    onChange={(e) => onCpuChange(Number(e.target.value))}
                    className="w-full mb-4"
                />
                

                <button onClick={handleAddBox} className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600">
                    Ajouter
                </button>
                <button onClick={onClose} className="mt-2 w-full bg-gray-300 text-black p-2 rounded-lg hover:bg-gray-400">
                    Annuler
                </button>
            </div>
        </div>
    );
};

export default CustomBox;
