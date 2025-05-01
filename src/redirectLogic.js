export const redirectToPage = (navigate, selectedOption, selectedMode, hypervisor) => {
  console.log("Redirection Debug =>", { hypervisor, selectedOption, selectedMode });

  let path = "";

  if (hypervisor === "VirtualBox") {
    if (selectedOption === "Cluster" && selectedMode === "Local mode") {
      path = "/ClusterVir";
    } else if (selectedOption === "Virtual Machine" && selectedMode === "Local mode") {
      path = "/formulaireVir";
    } else if (selectedOption === "Virtual Machine" && selectedMode === "Distant mode") {
      path = "/DistantConfigVir";
    }
  } else if (hypervisor === "Proxmox") {
    if (selectedOption === "Virtual Machine" ) {
      path = "/DistantConfig";
    } else if (selectedOption === "Virtual Machine") {
      path = "/CloneTemplate";
    }
  }

  if (path) {
    console.log("Navigation vers :", path);
    navigate(path, { state: { hypervisor, selectedOption} });
  } else {
    console.error("Erreur de redirection", { hypervisor, selectedOption, selectedMode });
  }
};
