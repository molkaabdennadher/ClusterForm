from flask import Flask, request, jsonify
import subprocess
import os
import random
from flask import render_template
from flask_cors import CORS  # Import de flask-cors

app = Flask(__name__)
CORS(app)  # Autorise toutes les origines (pour le développement)

@app.route('/', methods=['GET'])
def index():
    render_template('formulaire.js')

@app.route('/create-vm', methods=['POST'])
def create_vm():
    data = request.json
    vm_name = data.get("vm_name")
    box = data.get("box")
    ram = data.get("ram")
    cpu = data.get("cpu")
    network = data.get("network", "NAT")

    if not vm_name or not box or not ram or not cpu:
        return jsonify({"error": "Missing parameters"}), 400

    # Convertir la RAM de GB en MB pour VirtualBox
    memory_mb = int(ram * 1024)

    # Configuration réseau : si ce n'est pas NAT, générer une IP privée
    network_config = ""
    ip_address = ""
    if network != "NAT":
        # Génère une IP privée dans la plage 192.168.56.x
        ip_address = f"192.168.56.{random.randint(2, 254)}"
        network_config = f'  config.vm.network "private_network", ip: "{ip_address}"\n'

    # Construction du contenu du Vagrantfile
    vagrantfile_content = f"""Vagrant.configure("2") do |config|
  config.vm.box = "{box}"
  config.vm.hostname = "{vm_name}"
{network_config}  config.vm.provider "virtualbox" do |vb|
    vb.memory = "{memory_mb}"
    vb.cpus = "{cpu}"
  end
end
"""

    # Création d'un dossier dédié à la VM (ex.: ./vms/<vm_name>)
    vm_path = os.path.join(".", "vms", vm_name)
    os.makedirs(vm_path, exist_ok=True)

    # Écriture du Vagrantfile
    vagrantfile_path = os.path.join(vm_path, "Vagrantfile")
    with open(vagrantfile_path, "w") as vf:
        vf.write(vagrantfile_content)

    try:
        # Lancer la création de la VM avec Vagrant
        subprocess.run(["vagrant", "up"], cwd=vm_path, check=True)

        # Récupération des infos SSH selon le type de réseau
        if network == "NAT":
            # Exécute "vagrant ssh-config" pour récupérer l'IP (souvent 127.0.0.1) et le port redirigé (ex: 2222)
            ssh_config = subprocess.check_output(["vagrant", "ssh-config"], cwd=vm_path, universal_newlines=True)
            hostname_line = ""
            port_line = ""
            for line in ssh_config.splitlines():
                if line.strip().startswith("HostName"):
                    hostname_line = line.strip().split()[1]
                if line.strip().startswith("Port"):
                    port_line = line.strip().split()[1]
            ip_address = hostname_line
            port = port_line
        else:
            # Pour un réseau privé, l'IP est celle générée et le port SSH est par défaut 22
            port = "22"

        return jsonify({
            "message": f"VM {vm_name} is created",
            "ipAddress": ip_address,
            "port": port
        }), 200
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)