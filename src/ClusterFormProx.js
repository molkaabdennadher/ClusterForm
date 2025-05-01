import React, { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const RoleBadge = ({ role }) => {
  const roleColors = {
    namenode: "bg-blue-100 text-blue-800",
    datanode: "bg-green-100 text-green-800",
    resourcemanager: "bg-purple-100 text-purple-800",
    ansible: "bg-orange-100 text-orange-800",
    zookeeper: "bg-yellow-100 text-yellow-800",
    journalnode: "bg-pink-100 text-pink-800"
  };
  return (
    <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${roleColors[role] || 'bg-gray-100 text-gray-800'}`}>
      {role}
    </span>
  );
};

export default function ClusterFormProx() {
  const location = useLocation();
  console.log("ClusterType reçu :", location.state?.clusterType); // Ajout ici
  const navigate = useNavigate();
  const { clusterName, nodeCount, clusterType} = location.state;

  const [formData, setFormData] = useState({
    cluster_name: clusterName,
    node_count: nodeCount,
    proxmox_ip: "",
    password: "",
    target_node: "",
    network_type: "nat",
    template: "",
    vm_id_start: "",
    vm_type: "hadoop",
    roles_config: {
      namenode: true,
      datanode: true,
      resourcemanager: true,
      zookeeper: clusterType === "HA",
      journalnode: clusterType === "HA"
    }
  });

  const [isCreating, setIsCreating] = useState(false);
  const [creationLog, setCreationLog] = useState([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [servers, setServers] = useState([]);
  const [templates, setTemplates] = useState([]);

  useEffect(() => {
    const savedServers = JSON.parse(localStorage.getItem("servers")) || [];
    setServers(savedServers);
  }, []);

  useEffect(() => {
    if (formData.proxmox_ip) {
      const selectedServer = servers.find(
        (server) => server.serverIp === formData.proxmox_ip
      );
      if (selectedServer) {
        setTemplates(selectedServer.templates || []);
      }
    }
  }, [formData.proxmox_ip, servers]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value
    }));
  };

  const addLogMessage = (message) => {
    setCreationLog((prev) => [...prev, `${new Date().toLocaleTimeString()}: ${message}`]);
  };

  const createHadoopCluster = async () => {
    console.log("Type de cluster sélectionné:", clusterType); // Debug
    setIsCreating(true);
    setCreationLog([]);
    
    try {
      addLogMessage("Initialisation de la création du cluster...");
      
      // Conversion des types avant envoi
      const payload = {
        ...formData,
        node_count: parseInt(formData.node_count, 10),
        vm_id_start: parseInt(formData.vm_id_start, 10),
        hostname: `${formData.cluster_name}-node`,
        vm_type: "hadoop"
      };

      // Validation côté client
      if (isNaN(payload.node_count) || payload.node_count < 1) {
        throw new Error("Nombre de nœuds invalide");
      }

      if (isNaN(payload.vm_id_start) || payload.vm_id_start < 100) {
        throw new Error("ID de VM doit être ≥ 100");
      }

      // Choix du endpoint en fonction du type de cluster
      let endpoint;
      if (clusterType === "Classic") {
        endpoint = "http://localhost:5000/clustercreate_vmprox";
      } else if (clusterType === "HA") {
        endpoint = "http://localhost:5000/clusterha_vmprox";
      } else if (clusterType === "Spark HA") {
        endpoint = "http://localhost:5000/clusterspark_vmprox";
      } else {
        throw new Error("Type de cluster non reconnu");
      }

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Erreur HTTP: ${response.status}`);
      }

      const result = await response.json();
      addLogMessage("Cluster en cours de création...");
      await createHadoopNodes(); // Appelle la fonction pour créer les nœuds
    } catch (error) {
      addLogMessage(`ERREUR: ${error.message}`);
    } finally {
      setIsCreating(false);
    }
  };

  const createHadoopNodes = async () => {
    try {
      const nodes = [];
      let namenode_ip = null;
      const datanode_ips = [];
      let created = 0;
  
      // Configuration spéciale pour Spark HA
      const isSparkHA = clusterType === "Spark HA";
      const totalNodes = isSparkHA ? formData.node_count + 2 : formData.node_count;
  
      // Choix du endpoint
      let endpoint;
      if (clusterType === "Classic") {
        endpoint = "http://localhost:5000/clustercreate_vmprox";
      } else if (clusterType === "HA") {
        endpoint = "http://localhost:5000/clusterha_vmprox";
      } else if (clusterType === "Spark HA") {
        endpoint = "http://localhost:5000/clusterspark_vmprox";
      }
  
      for (let i = 1; i <= totalNodes; i++) {
        const vm_id = parseInt(formData.vm_id_start) + i;
        let node_name, roles = [];
  
        if (isSparkHA) {
          // Gestion spécifique des nœuds supplémentaires pour Spark HA
          if (i === formData.node_count + 1) {
            node_name = `ansible-${formData.cluster_name}`;
            roles = ["ansible"];
          } else if (i === formData.node_count + 2) {
            node_name = `${formData.cluster_name}-standby`;
            roles = ["standby"];
          } else {
            node_name = `${formData.cluster_name}-node-${i}`;
            const isFirstNode = i === 1;
            roles = determineNodeRoles(isFirstNode);
          }
        } else {
          // Configuration standard pour Classic et HA
          node_name = `${formData.cluster_name}-node-${i}`;
          const isFirstNode = i === 1;
          roles = determineNodeRoles(isFirstNode);
        }
  
        const nodeData = {
          ...formData,
          hostname: node_name,
          vm_id: vm_id,
          vm_type: "hadoop",
          node_index: i,
          roles: roles
        };
  
        addLogMessage(`Création du nœud ${node_name} (ID: ${vm_id}, Rôles: ${roles.join(", ")})...`);
  
        const createResponse = await fetchWithTimeout(
          endpoint,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(nodeData)
          },
          30000
        );

        const createData = await createResponse.json();
        if (!createResponse.ok) {
          addLogMessage(`Échec de la création : ${createData.error || "Erreur inconnue"}`);
          continue;
        }

        addLogMessage(`Configuration du nœud ${node_name}...`);
        const confResponse = await fetchWithTimeout(
          "http://localhost:5000/clusterconf_vmprox",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ...nodeData,
              proxmox_ip: formData.proxmox_ip,
              password: formData.password
            })
          },
          30000
        );

        const confData = await confResponse.json();
        if (!confResponse.ok) {
          addLogMessage(`Échec de la configuration : ${confData.error || "Erreur inconnue"}`);
          continue;
        }

        const node_ip = confData.ip;
        if (roles.includes("namenode")) namenode_ip = node_ip;
        if (roles.includes("datanode")) datanode_ips.push(node_ip);
        nodes.push({
          name: node_name,
          ip: node_ip,
          vm_id: vm_id,
          roles: roles,
          type: "hadoop"
        });
        created++;
        addLogMessage(`Nœud ${node_name} prêt - IP: ${node_ip} - Rôles: ${roles.join(", ")}`);
        await new Promise(resolve => setTimeout(resolve, 15000));
      }

      if (created === 0) {
        throw new Error("Aucun nœud n'a été créé");
      }
      return {
        success: true,
        created,
        nodes,
        namenode_ip,
        datanode_ips
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  };

  const determineNodeRoles = (isFirstNode) => {
    const roles = [];
    if (isFirstNode) {
      if (formData.roles_config.namenode) roles.push("namenode");
      if (formData.roles_config.resourcemanager) roles.push("resourcemanager");
    }
    if (formData.roles_config.datanode) roles.push("datanode");
    if ((clusterType === "HA" || clusterType === "Spark HA") && formData.roles_config.zookeeper) {
      roles.push("zookeeper");
    }
    if ((clusterType === "HA" || clusterType === "Spark HA") && formData.roles_config.journalnode) {
      roles.push("journalnode");
    }
    return roles;
  };

  const fetchWithTimeout = async (url, options, timeout) => {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      clearTimeout(id);
      return response;
    } catch (error) {
      clearTimeout(id);
      throw new Error(error.name === "AbortError" ? "Délai d'attente dépassé" : error.message);
    }
  };

  const renderRoleConfiguration = () => (
    <div className="mt-4 p-4 border rounded-lg bg-gray-50">
      <h3 className="font-medium text-lg mb-3">Configuration des rôles</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-3">
          <h4 className="font-medium">Rôles principaux</h4>
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.roles_config.namenode}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  roles_config: {
                    ...prev.roles_config,
                    namenode: e.target.checked
                  }
                }))
              }
              className="form-checkbox h-5 w-5 text-blue-600"
              disabled={clusterType !== "HDFS"}
            />
            <span>NameNode (Premier nœud)</span>
          </label>
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.roles_config.datanode}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  roles_config: {
                    ...prev.roles_config,
                    datanode: e.target.checked
                  }
                }))
              }
              className="form-checkbox h-5 w-5 text-green-600"
            />
            <span>DataNode (Tous les nœuds)</span>
          </label>
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.roles_config.resourcemanager}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  roles_config: {
                    ...prev.roles_config,
                    resourcemanager: e.target.checked
                  }
                }))
              }
              className="form-checkbox h-5 w-5 text-purple-600"
              disabled={clusterType !== "YARN"}
            />
            <span>ResourceManager (Premier nœud)</span>
          </label>
        </div>
        {clusterType === "Spark HA" && (
          <>
            <div className="pt-2 mt-2 border-t">
              <h4 className="font-medium">Configuration Spark</h4>
              <p className="text-sm text-gray-600">
                Spark sera installé sur le NameNode par défaut<br/>
                Spark sera installé sur les DataNodes par défaut
              </p>
            </div>
          </>
        )}{clusterType === "Spark HA" && (
          <div className="space-y-3">
            <h4 className="font-medium">Configuration Spark</h4>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={formData.roles_config.spark_master}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  roles_config: {
                    ...prev.roles_config,
                    spark_master: e.target.checked
                  }
                }))}
                className="form-checkbox h-5 w-5 text-red-600"
              />
              <span>Spark (NameNode)</span>
            </label>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={formData.roles_config.spark_worker}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  roles_config: {
                    ...prev.roles_config,
                    spark_worker: e.target.checked
                  }
                }))}
                className="form-checkbox h-5 w-5 text-orange-600"
              />
              <span>Spark (DataNodes)</span>
            </label>
          </div>
        )}
        
        {clusterType === "HA" && (
          <div className="space-y-3">
            <h4 className="font-medium">Haute disponibilité</h4>
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={formData.roles_config.zookeeper}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    roles_config: {
                      ...prev.roles_config,
                      zookeeper: e.target.checked
                    }
                  }))
                }
                className="form-checkbox h-5 w-5 text-yellow-600"
              />
              <span>ZooKeeper</span>
            </label>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-teal-100 to-white p-4">
      <h1 className="text-4xl font-bold text-teal-600 mb-6">
        Configuration du cluster {clusterType}
      </h1>
      <div className="w-full max-w-4xl bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-2xl font-semibold text-teal-600 mb-4">
          {formData.cluster_name} ({formData.node_count} nœuds)
        </h2>
        {!isCreating ? (
          <form onSubmit={(e) => { e.preventDefault(); createHadoopCluster(); }} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Serveur Proxmox*</label>
                <select
                  name="proxmox_ip"
                  value={formData.proxmox_ip}
                  onChange={handleInputChange}
                  className="w-full p-2 border rounded"
                  required
                >
                  <option value="">Sélectionner un serveur</option>
                  {servers.map((server, index) => (
                    <option key={index} value={server.serverIp}>
                      {server.serverName} ({server.serverIp})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Mot de passe root*</label>
                <input
                  type="password"
                  name="password"
                  value={formData.password}
                  onChange={handleInputChange}
                  placeholder="Mot de passe Proxmox"
                  className="w-full p-2 border rounded"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Nœud cible*</label>
                <input
                  type="text"
                  name="target_node"
                  value={formData.target_node}
                  onChange={handleInputChange}
                  placeholder="pve ou nom du nœud"
                  className="w-full p-2 border rounded"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Modèle*</label>
                <select
                  name="template"
                  value={formData.template}
                  onChange={handleInputChange}
                  className="w-full p-2 border rounded"
                  required
                  disabled={!formData.proxmox_ip}
                >
                  <option value="">Sélectionner un modèle</option>
                  {templates.map((template, index) => (
                    <option key={index} value={template.name}>
                      {template.name} (ID: {template.id})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Réseau*</label>
                <select
                  name="network_type"
                  value={formData.network_type}
                  onChange={handleInputChange}
                  className="w-full p-2 border rounded"
                  required
                >
                  <option value="nat">NAT</option>
                  <option value="bridged">Pont</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">ID de démarrage de la VM*</label>
                <input
                  type="number"
                  name="vm_id_start"
                  value={formData.vm_id_start}
                  onChange={handleInputChange}
                  placeholder="ex. 1000"
                  min="100"
                  max="9999"
                  className="w-full p-2 border rounded"
                  required
                />
              </div>
            </div>
            {renderRoleConfiguration()}
            <button
              type="submit"
              className="w-full bg-teal-500 text-white p-3 rounded-lg shadow-md hover:bg-teal-600 transition duration-300 flex items-center justify-center"
              disabled={isCreating}
            >
              {isCreating ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Création du cluster en cours...
                </>
              ) : "Lancer la création du cluster"}
            </button>
          </form>
        ) : (
          <div className="mt-6">
            <h3 className="text-lg font-semibold mb-2">
              Progression : {currentStep}/4 étapes
            </h3>
            <div className="w-full bg-gray-200 rounded-full h-4 mb-4">
              <div
                className="bg-teal-500 h-4 rounded-full transition-all duration-500"
                style={{ width: `${(currentStep / 4) * 100}%` }}
              ></div>
            </div>
            <div className="bg-gray-100 p-4 rounded-lg max-h-96 overflow-y-auto">
              <h4 className="font-medium mb-2">Journal d'activité :</h4>
              <ul className="space-y-2 font-mono text-sm">
                {creationLog.map((log, index) => (
                  <li key={index} className="flex items-start">
                    <span className="text-gray-500 mr-2">{log.split(':')[0]}:</span>
                    <span>
                      {log.includes("Rôles:") ? (
                        <>
                          {log.split("Rôles:")[0].split(':').slice(1).join(':')}
                          <div className="flex flex-wrap gap-1 mt-1">
                            {log.split("Rôles:")[1].split(", ").map(role => (
                              <RoleBadge key={role.trim()} role={role.trim()} />
                            ))}
                          </div>
                        </>
                      ) : log.includes("IP:") ? (
                        <>
                          {log.split("IP:")[0].split(':').slice(1).join(':')}
                          <span className="font-bold">IP: {log.split("IP:")[1]}</span>
                        </>
                      ) : (
                        log.split(':').slice(1).join(':')
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}