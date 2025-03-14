import React, { useState } from 'react';

const CustomBox = ({ onClose, onAddBox }) => {
    const [boxName, setBoxName] = useState("");
    const [isoFile, setIsoFile] = useState(null);
    const [isoUrl, setIsoUrl] = useState("");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [description, setDescription] = useState("");
    const [software, setSoftware] = useState({
        ssh: false,
        hadoop: false,
        python: false,
        nettools: false,
        java: false,
        ansible: false,
    });

    const handleAddBox = () => {
        if (boxName.trim() && (isoFile || isoUrl) && username && password) {
            onAddBox({
                name: boxName,
                isoImage: isoFile ? isoFile.name : isoUrl,
                username,
                password,
                description,
                software
            });
            setBoxName("");
            setIsoFile(null);
            setIsoUrl("");
            setUsername("");
            setPassword("");
            setDescription("");
            setSoftware({
                ssh: false,
                hadoop: false,
                python: false,
                nettools: false,
                java: false,
                ansible: false,
            });
            onClose();
        } else {
            alert("Les champs marqués * sont requis.");
        }
    };

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        setIsoFile(file || null);
        if (file) setIsoUrl(""); // Reset l'URL si fichier sélectionné
    };

    const handleUrlChange = (e) => {
        setIsoUrl(e.target.value);
        if (e.target.value) setIsoFile(null); // Reset le fichier si URL saisie
    };

    const handleSoftwareChange = (softwareName) => {
        setSoftware(prev => ({
            ...prev,
            [softwareName]: !prev[softwareName],
        }));
    };

    return (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white p-6 rounded-lg shadow-lg w-96">
                <h2 className="text-lg font-bold mb-4">Create your new box</h2>

                <label className="block text-sm font-medium">Box name * :</label>
                <input
                    placeholder="Set your box name..."
                    type="text"
                    value={boxName}
                    onChange={(e) => setBoxName(e.target.value)}
                    className="w-full p-2 border rounded mb-4"
                />

                <label className="block text-sm font-medium mb-2">ISO image * :</label>
                <input
                    type="file"
                    onChange={handleFileChange}
                    className="w-full mb-2"
                    accept=".iso"
                />
                <div className="text-center mb-2 text-sm text-gray-500">OU</div>
                <input
                    type="url"
                    value={isoUrl}
                    placeholder="Enter an ISO URL..."
                    onChange={handleUrlChange}
                    className="w-full p-2 border rounded mb-4"
                />
                {isoFile && (
                    <p className="text-gray-600 text-sm mb-4">
                        Selected file: {isoFile.name}
                    </p>
                )}

                <div className="flex space-x-4 mb-4">
                    <div className="flex-1">
                        <label className="block text-sm font-medium mb-2">User name*:</label>
                        <input
                            placeholder="Set your username..."

                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full p-2 border rounded"
                            required
                        />
                    </div>
                    <div className="flex-1">
                        <label className="block text-sm font-medium mb-2">User password*:</label>
                        <input
                            type="password"
                            placeholder="Set your password..."

                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full p-2 border rounded"
                            required
                        />
                    </div>
                </div>

                <label className="block text-sm font-medium mb-2">Description:</label>
                <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe your box ..."

                    className="w-full p-2 border rounded mb-4"
                    rows="3"
                />

                <h3 className="text-sm font-medium mb-2">Softwares :</h3>
                {Object.keys(software).map((key) => (
                    <label key={key} className="inline-flex items-center mb-2">
                        <input
                            type="checkbox"
                            checked={software[key]}
                            onChange={() => handleSoftwareChange(key)}
                            className="form-checkbox h-5 w-5 text-teal-600"
                        />
                        <span className="ml-2 text-gray-700 capitalize">{key}</span>
                    </label>
                ))}

                <button onClick={handleAddBox} className="w-full bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600">
                    Submit
                </button>
                <button onClick={onClose} className="mt-2 w-full bg-gray-300 text-black p-2 rounded-lg hover:bg-gray-400">
                    Decline
                </button>
            </div>
        </div>
    );
};

export default CustomBox;