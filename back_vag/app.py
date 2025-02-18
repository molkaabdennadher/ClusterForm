from flask import Flask, request, jsonify
import subprocess
import os
import paramiko

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
@app.route('/create-vm-remote', methods=['POST'])
def create_vm_remote():
    try:
        data = request.get_json()
        # Récupération des paramètres envoyés par le front-end
        ip = data.get('remote_ip')
        ssh_username = data.get('remote_user')
        ssh_password = data.get('remote_password')
        remote_os = data.get('remote_os', 'Windows').lower()  # Par défaut "windows"
        hypervisor = data.get('hypervisor', 'VirtualBox')  # Actuellement non utilisé

        # 1. Établir la connexion SSH
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=ssh_username, password=ssh_password)
        print("conxx ssh établie")

        # 2. Récupérer le hostname de la machine distante (pour nommer la VM)
        stdin, stdout, stderr = client.exec_command("hostname")
        hostname = stdout.read().decode().strip()
        if not hostname:
            hostname = ssh_username  # Si le hostname n'est pas disponible
        print("DEBUG - Hostname:", hostname)

        # 3. Ouvrir une session SFTP et déterminer le répertoire de travail
        sftp = client.open_sftp()
        if remote_os == 'windows':
            # Sous Windows, sftp.getcwd() retourne généralement le dossier personnel
            current_dir = sftp.getcwd()
            if not current_dir or current_dir == '':
                current_dir = '.'
            # Commande pour lancer Vagrant sur Windows (cd /d pour changer de disque si besoin)
            vagrant_command = f'cd /d "{current_dir}" && vagrant up'
        else:
            # Sous Linux, on se base sur /home/<ssh_username>
            current_dir = f"/home/{ssh_username}"
            try:
                sftp.chdir(current_dir)
            except IOError:
                sftp.mkdir(current_dir)
            vagrant_command = f'cd {current_dir} && vagrant up'

        print("DEBUG - Current directory:", current_dir)
        try:
            listing = sftp.listdir(current_dir)
            print("DEBUG - Listing of current_dir:", listing)
        except Exception as e:
            print("DEBUG - Impossible de lister le répertoire :", e)

        # 4. Préparer le contenu du Vagrantfile avec le hostname
        vagrantfile_content = f"""Vagrant.configure("2") do |config|
  config.vm.box = "{box}"
  config.vm.hostname = "{vm_name}"
{network_config}  config.vm.provider "virtualbox" do |vb|
    vb.name = "{vm_name}"
    vb.memory = "{memory_mb}"
    vb.cpus = "{cpu}"
  end
end
"""

        # 5. Écrire le Vagrantfile dans le répertoire courant
        remote_vagrantfile_path = f"{current_dir}/Vagrantfile" if not current_dir.endswith("/") else f"{current_dir}Vagrantfile"
        with sftp.open(remote_vagrantfile_path, 'w') as remote_file:
            remote_file.write(vagrantfile_content)
        print("DEBUG - Vagrantfile écrit dans", remote_vagrantfile_path)

        # 6. Exécuter la commande "vagrant up" pour créer la VM
        stdin, stdout, stderr = client.exec_command(vagrant_command)
        stdout_result = stdout.read().decode()
        stderr_result = stderr.read().decode()
        if stderr_result.strip():
            sftp.close()
            client.close()
            return jsonify({"error": stderr_result}), 500
        print("DEBUG - Vagrant up result:", stdout_result)

        # 7. Récupérer l'état de la VM via "vagrant status"
        status_command = f'cd "{current_dir}" && vagrant status'
        stdin, stdout, stderr = client.exec_command(status_command)
        vm_status = stdout.read().decode()
        status_err = stderr.read().decode()
        if status_err.strip():
            vm_status += "\nErreurs: " + status_err
        print("DEBUG - Vagrant status:", vm_status)

        # 8. Copier le Vagrantfile dans le dossier "vms" sur la machine distante
        # Définir le chemin du dossier "vms" dans le répertoire courant
        vms_folder = f"{current_dir}/vms" if not current_dir.endswith("/") else f"{current_dir}vms"
        try:
            sftp.chdir(vms_folder)
        except IOError:
            # Le dossier n'existe pas, on le crée
            try:
                sftp.mkdir(vms_folder)
                print("DEBUG - Dossier 'vms' créé dans", current_dir)
            except Exception as mkdir_error:
                print("DEBUG - Échec de la création du dossier 'vms':", mkdir_error)
                # Vous pouvez décider de renvoyer une erreur ici si c'est critique
        # Copier le fichier Vagrantfile dans le dossier "vms" avec un nom basé sur le hostname
        dest_vagrantfile = f"{vms_folder}/{hostname}_Vagrantfile"
        try:
            with sftp.open(remote_vagrantfile_path, 'r') as source_file:
                file_data = source_file.read()
            with sftp.open(dest_vagrantfile, 'w') as dest_file:
                dest_file.write(file_data)
            print("DEBUG - Vagrantfile copié vers", dest_vagrantfile)
        except Exception as copy_error:
            print("DEBUG - Échec de la copie du Vagrantfile:", copy_error)

        # 9. Fermer la connexion SFTP et SSH
        sftp.close()
        client.close()

        # 10. Retourner dans la réponse JSON les infos de la VM
        response = {
            "message": "VM created successfully!",
            "vm_folder_path": current_dir,
            "remote_ip": ip,
            "hostname": hostname,
            "vm_status": vm_status
        }
        return jsonify(response)

    except Exception as e:
        print("DEBUG - Exception dans create_vm_remote:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)