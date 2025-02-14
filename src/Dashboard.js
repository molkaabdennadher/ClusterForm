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

  const handleDelete = (index) => {
    const updatedMachines = machines.filter((_, i) => i !== index);
    setMachines(updatedMachines);
    localStorage.setItem("vms", JSON.stringify(updatedMachines));

    window.dispatchEvent(new Event("storage"));
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
            <th className="p-3 border">Status</th>
            <th className="p-3 border">Date of Creation</th>
            <th className="p-3 border">SSH Address</th>
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
              <td className={`p-3 border font-semibold ${machine.status === "Running" ? "text-green-500" : "text-red-500"}`}>
                {machine.status}
              </td>
              <td className="p-3 border">{machine.date}</td>
              <td className="p-3 border">{machine.ipAddress}:{machine.port}</td>
              <td className="p-3 border">
                <button onClick={() => handleDelete(index)} className="text-red-500 hover:text-red-700">✖</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Dashboard;
