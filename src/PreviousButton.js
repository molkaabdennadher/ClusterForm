import { useNavigate } from 'react-router-dom';

function PreviousButton() {
  const navigate = useNavigate();

  const goBack = () => {
    navigate(-1); // Retourne à la page précédente
  };

  return (
    <button 
      onClick={goBack} 
      className="bg-teal-500 text-white p-2 rounded-lg shadow-md hover:bg-teal-600"
      >
      Précédent
    </button>
  );
}

export default PreviousButton;
