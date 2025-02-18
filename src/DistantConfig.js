import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const DistantConfig = () => {
  const [ip, setIp] = useState("");
  const [login, setLogin] = useState(""); // Ce champ sera utilisé comme remote_user
  const [password, setPassword] = useState("");
  const [remote_os, setOs] = useState("Windows");
  const [hypervisor, setHypervisor] = useState("VirtualBox");
  const navigate = useNavigate();

  const handleSubmit = () => {
    if (!ip || !login || !password) {
      alert("Veuillez remplir tous les champs !");
      return;
    }
    // On navigue vers le formulaire en passant les infos de connexion distante,
    // y compris remote_user (issu du champ login)
    navigate("/formulaire", {
      state: {
        remote_ip: ip,
        remote_user: login,
        remote_password: password,
        remote_os,
        hypervisor,
        mode: "distant"
      }
    });
  };

  const styles = {
    container: {
      textAlign: "center",
      padding: "50px",
      backgroundColor: "#E3FDFD",
      height: "100vh",
    },
    title: {
      fontSize: "50px",
      fontWeight: "bold",
      color: "#008080",
    },
    label: {
      display: "block",
      fontSize: "18px",
      fontWeight: "bold",
      marginTop: "20px",
      color: "#004D40",
    },
    input: {
      width: "80%",
      padding: "10px",
      marginTop: "10px",
      borderRadius: "5px",
      border: "1px solid #ccc",
    },
    select: {
      width: "83%",
      padding: "10px",
      marginTop: "10px",
      borderRadius: "5px",
      border: "1px solid #ccc",
    },
    button: {
      marginTop: "20px",
      padding: "10px 20px",
      backgroundColor: "#008080",
      color: "white",
      fontSize: "18px",
      border: "none",
      cursor: "pointer",
      borderRadius: "5px",
    },
  };

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Configuration</h1>

      <label style={styles.label}>IP Address :</label>
      <input
        type="text"
        placeholder="Please tape your IP address here..."
        value={ip}
        onChange={(e) => setIp(e.target.value)}
        style={styles.input}
      />

      <label style={styles.label}>Login :</label>
      <input
        type="text"
        placeholder="Please tape your login here..."
        value={login}
        onChange={(e) => setLogin(e.target.value)}
        style={styles.input}
      />

      <label style={styles.label}>Password :</label>
      <input
        type="password"
        placeholder="Please tape your password here..."
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        style={styles.input}
      />
      <label style={styles.label}>OS :</label>
      <select
        value={hypervisor}
        onChange={(e) => setHypervisor(e.target.value)}
        style={styles.select}
      >
        <option value="Windows">Windows</option>
        <option value="Linux">Linux</option>
      </select>
      <label style={styles.label}>Hypervisor</label>
      <select
        value={hypervisor}
        onChange={(e) => setHypervisor(e.target.value)}
        style={styles.select}
      >
        <option value="VirtualBox">VirtualBox</option>
        <option value="VMware">VMware Workstation Pro</option>
      </select>

      <button style={styles.button} onClick={handleSubmit}>
        Connecter
      </button>
    </div>
  );
};

export default DistantConfig;
