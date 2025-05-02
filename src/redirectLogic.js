export const redirectToPage = (navigate, selectedOption, selectedMode, hypervisor) => {
  // Validation des entrées
  if (!selectedOption || !selectedMode || !hypervisor) {
    console.error("Paramètres manquants:", { selectedOption, selectedMode, hypervisor });
    return navigate("/DistantConfigVir", {
      state: {
        error: "missing_parameters",
        params: { selectedOption, selectedMode, hypervisor }
      }
    });
  }

  // Normalisation robuste
  const normHyper = String(hypervisor).trim().toLowerCase();
  const normOption = String(selectedOption).trim().toLowerCase();
  const normMode = String(selectedMode).trim().toLowerCase();

  // Configuration exhaustive des routes
  const ROUTES = {
    virtualbox: {
      "virtual machine": {
        "local mode": "/formulaireVir",
        "distant mode": "/DistantConfigVir"
      },
      "cluster": {
        "local mode": "/ClusterVir",
        "distant mode": "/DistantConfigVir"
      }
    },
    proxmox: {
      "virtual machine": "/DistantConfig"
    }
  };

  const path = ROUTES[normHyper]?.[normOption]?.[normMode] 
             || "/DistantConfigVir";

  navigate(path, {
    state: {
      option: normOption,
      hypervisor: normHyper,
      mode: normMode
    }
  });
};