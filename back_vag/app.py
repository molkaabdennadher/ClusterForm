from flask import Flask, request, jsonify
import subprocess
import os
import paramiko
import traceback
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

# Endpoint pour créer la VM en mode distant via Paramiko
@app.route("/create-vm-remote", methods=["POST"])
def create_vm_remote():
    """
    Crée une VM sur une machine distante (Windows ou Linux) via SSH + Vagrant + VirtualBox,
    puis copie le Vagrantfile sur la machine source.
    """
    try:
        data = request.get_json()

        # ------------------- Paramètres de connexion SSH -------------------
        remote_ip = data.get('remote_ip')
        remote_user = data.get('remote_user')
        remote_password = data.get('remote_password')
        remote_os = data.get('remote_os', 'Windows').lower()

        # ------------------- Paramètres de la VM -------------------
        vm_name = data.get("vm_name", "DefaultVM")
        box = data.get("box", "ubuntu/bionic64")
        ram = float(data.get("ram", 1))  # en GB
        cpu = int(data.get("cpu", 1))
        network = data.get("network", "NAT")

        if not vm_name:
            return jsonify({"error": "vm_name is required"}), 400

        memory_mb = int(ram * 1024)

        # Configuration réseau
        network_config = ""
        ip_address_generated = ""
        if network != "NAT":
            ip_address_generated = f"192.168.56.{random.randint(2,254)}"
            network_config = f'  config.vm.network "private_network", ip: "{ip_address_generated}"\n'

        # ------------------- Construction du Vagrantfile -------------------
        vagrantfile_content = f"""Vagrant.configure("2") do |config|
  config.vm.box = "{box}"
  config.vm.hostname = "{vm_name}"
{network_config}  config.vm.provider "virtualbox" do |vb|
    vb.name = "{vm_name}"
    vb.memory = "{memory_mb}"
    vb.cpus = {cpu}
  end
end
"""

        # ------------------- 1) Connexion SSH -------------------
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(remote_ip, username=remote_user, password=remote_password)
        print("Connexion SSH établie avec la machine distante.")

        sftp = client.open_sftp()

        # ------------------- 2) Aller dans le home_dir -------------------
        if remote_os == 'windows':
            home_dir = sftp.getcwd() or '.'
        else:
            home_dir = f"/home/{remote_user}"
            try:
                sftp.chdir(home_dir)
            except IOError:
                sftp.mkdir(home_dir)
                sftp.chdir(home_dir)

        # ------------------- 3) Créer/Aller dans le dossier "vms" -------------------
        try:
            sftp.chdir("vms")
        except IOError:
            sftp.mkdir("vms")
            sftp.chdir("vms")

        # ------------------- 4) Créer/Aller dans le dossier <vm_name> -------------------
        try:
            sftp.chdir(vm_name)
        except IOError:
            sftp.mkdir(vm_name)
            sftp.chdir(vm_name)

        # On est maintenant dans le dossier de la VM sur la machine distante
        remote_vm_folder = sftp.getcwd()
        print(f"DEBUG - Dossier de la VM sur la machine distante : {remote_vm_folder}")

        # ------------------- 5) Écrire le Vagrantfile -------------------
        remote_vagrantfile_path = "Vagrantfile"  # dans le dossier courant
        with sftp.open(remote_vagrantfile_path, 'w') as remote_file:
            remote_file.write(vagrantfile_content)
        print("DEBUG - Vagrantfile écrit dans", remote_vagrantfile_path)

        # ------------------- 6) Exécuter 'vagrant up' -------------------
        if remote_os == 'windows':
            # Si le chemin commence par "/", on le retire
            folder = remote_vm_folder.lstrip("/")
            command_vagrant_up = f'cd /d "{folder}" && vagrant up'
        else:
            command_vagrant_up = f'cd "{remote_vm_folder}" && vagrant up'

        stdin, stdout, stderr = client.exec_command(command_vagrant_up)
        out_up = stdout.read().decode('utf-8', errors='replace')
        err_up = stderr.read().decode('utf-8', errors='replace')
        if err_up.strip():
            sftp.close()
            client.close()
            return jsonify({"error": err_up}), 500
        print("DEBUG - vagrant up result:", out_up)

        # ------------------- 7) Récupérer l'état de la VM -------------------
        command_status = f'cd "{remote_vm_folder}" && vagrant status'
        stdin, stdout, stderr = client.exec_command(command_status)
        vm_status = stdout.read().decode('utf-8', errors='replace') + stderr.read().decode('utf-8', errors='replace')

        # ------------------- 8) Récupérer l'IP/Port si NAT -------------------
        ip_address = ""
        port = ""
        if network == "NAT":
            command_ssh_config = f'cd "{remote_vm_folder}" && vagrant ssh-config'
            stdin, stdout, stderr = client.exec_command(command_ssh_config)
            ssh_config = stdout.read().decode('utf-8', errors='replace')
            for line in ssh_config.splitlines():
                if line.strip().startswith("HostName"):
                    ip_address = line.strip().split()[1]
                if line.strip().startswith("Port"):
                    port = line.strip().split()[1]
        else:
            ip_address = ip_address_generated
            port = "22"

        # ------------------- 9) Copier le Vagrantfile sur la machine source -------------------
        local_vm_folder = os.path.join("vms_local", vm_name)
        os.makedirs(local_vm_folder, exist_ok=True)
        local_vagrantfile_path = os.path.join(local_vm_folder, "Vagrantfile")

        with sftp.open(remote_vagrantfile_path, 'rb') as remote_vf:
            vagrant_data = remote_vf.read()

        with open(local_vagrantfile_path, 'wb') as local_vf:
            local_vf.write(vagrant_data)

        print(f"DEBUG - Vagrantfile copié localement dans : {local_vagrantfile_path}")

        # ------------------- 10) Fermer les connexions -------------------
        sftp.close()
        client.close()

        # ------------------- 11) Réponse JSON -------------------
        return jsonify({
            "message": f"VM {vm_name} created remotely",
            "vm_name": vm_name,
            "remote_vm_folder": remote_vm_folder,
            "ipAddress": ip_address,
            "port": port,
            "vm_status": vm_status,
            "local_vagrantfile": os.path.abspath(local_vagrantfile_path)
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)