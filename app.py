from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import requests

app = Flask(__name__)
CORS(app)

# Fonction de connexion à Proxmox
def connect_to_proxmox(proxmox_ip, username, password):
    url = f"https://{proxmox_ip}:8006/api2/json/access/ticket"
    payload = {
        'username': username,
        'password': password
    }

    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

    response = requests.post(url, data=payload, verify=False)
    
    if response.status_code == 200:
        return response.json()['data']
    else:
        raise Exception("Échec de la connexion avec Proxmox: " + response.text)

@app.route('/create_vm', methods=['POST'])  
def create_vm():
    data = request.json
    print(request.form)  
    vm_id = request.form.get('vm_id')
    print(data)  

    proxmox_ip = data.get('proxmoxIp')  
    proxmox_password = data.get('proxmoxPassword')
    hostname = data.get('hostname')
    ram = data.get('ram')
    cpu = data.get('cpu')
    target_node = data.get('targetNode')
    network = data.get('network', 'nat')  
    vm_id = data.get('vmId')  # Corriger ici
    # Créer un fichier variables.tfvars pour Terraform
    terraform_vars = f"""
proxmox_ip = "{proxmox_ip}"
proxmox_password = "{proxmox_password}"
hostname = "{hostname}"
ram = {ram}
cpu = {cpu}
target_node = "{target_node}"
network_ip = "{network}"
vm_id = {vm_id} 
"""

    with open('variables.tfvars', 'w') as f:
        f.write(terraform_vars.strip())  # Enlever les espaces inutiles

    # Exécuter Terraform
    try:
        # Initialisation de Terraform
        print("Initializing Terraform...")
        subprocess.run(["terraform", "init"], check=True)
        print("Terraform initialized.")
        
        # Exécution de la commande Terraform pour créer la VM
        print("Creating VM with Terraform...")
        subprocess.run(["terraform", "apply", "-auto-approve", "-var-file=variables.tfvars"], check=True)
        print("VM created successfully.")
        
        return jsonify({"message": "VM created successfully!"}), 200
    except subprocess.CalledProcessError as e:
        print(f"Error during Terraform execution: {e}")
        return jsonify({"error": "Failed to create VM"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
