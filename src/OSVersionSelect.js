// OSVersionSelect.js
import React from 'react';

const OSVersionSelect = ({ value, onChange, onCustomBoxSelect, options }) => {
    return (
        <div>
            <label className="block text-sm font-medium mb-2">OS Version:</label>
            <select
                value={value}
                onChange={(e) => {
                    onChange(e.target.value);
                    if (e.target.value === "Box-perso") {
                        onCustomBoxSelect(true); // Ouvre l'interface personnalisée
                    } else {
                        onCustomBoxSelect(false); // Ferme l'interface personnalisée
                    }
                }}
                className="w-full p-2 border rounded mb-4"
            >
                {options.map((option, index) => (
                    <option key={index} value={option}>
                        {option}
                    </option>
                ))}

                <option value="Box-perso">Box Personnalisée</option>
            </select>
        </div>
    );
};

export default OSVersionSelect;