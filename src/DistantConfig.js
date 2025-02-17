import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const DistantConfig = () => {
  const [ip, setIp] = useState("");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [hypervisor, setHypervisor] = useState("VirtualBox");
  const navigate = useNavigate();

  const handleSubmit = () => {
    if (!ip || !login || !password) {
      alert("Veuillez remplir tous les champs !");
      return;
    }
    navigate("/formulaire", { state: { ip, login, password, hypervisor } });
  };

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Forms</h1>

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
        Connect
      </button>
    </div>
  );
};

// 🎨 Styles
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

export default DistantConfig;
