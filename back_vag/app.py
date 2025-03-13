
import time
from flask import Flask, request, jsonify, render_template
import subprocess
import os
import paramiko
import re
import traceback
import random
import shutil
import platform
import shlex
import smtplib
import tempfile
from email.message import EmailMessage
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
@app.route('/get-remote-cpu-info', methods=['POST'])
def get_remote_cpu_info():
    """
    Récupère le nombre de processeurs logiques et la mémoire totale (en Go) de la machine distante
    via SSH. Les commandes exécutées dépendent de l'OS distant (Windows ou Linux).
    """
    try:
        data = request.get_json()
        remote_ip = data.get('remote_ip')
        remote_user = data.get('remote_user')
        remote_password = data.get('remote_password')
        remote_os = data.get('remote_os', 'Windows').lower()

        # Créer et configurer le client SSH
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)

        logical_processors = 2  # Valeur par défaut
        total_memory = 16       # Valeur par défaut en Go

        if remote_os == "windows":
            # Récupérer le nombre de processeurs logiques via PowerShell
            cpu_command = (
                'powershell -Command "Get-WmiObject Win32_Processor | '
                'Measure-Object -Sum -Property NumberOfLogicalProcessors | '
                'Select-Object -ExpandProperty Sum"'
            )
            cpu_result = client.exec_command(cpu_command)[1].read().decode('utf-8', errors='replace').strip()
            if cpu_result.isdigit():
                logical_processors = int(cpu_result)

            # Récupérer la mémoire physique totale via systeminfo
            ram_command = r'systeminfo | findstr /C:"Mémoire physique totale"'
            # Utiliser l'encodage cp850 pour gérer la sortie OEM
            ram_output = client.exec_command(ram_command)[1].read().decode('cp850', errors='replace').strip()
            print("Sortie de systeminfo (remote):", ram_output)
            # Utiliser une regex pour extraire le nombre (en Mo)
            match = re.search(r"([\d\.,]+)", ram_output)
            if match:
                mem_str = match.group(1)
                mem_str = mem_str.replace(",", ".").strip()
                try:
                    mem_mb = float(mem_str)
                    print(mem_mb)
                    # Convertir de Mo en Go (arrondi à l'entier)
                    total_memory = int(mem_mb)
                    print("Total Memory (remote):", total_memory, "Go")
                except ValueError:
                    print("Conversion échouée pour la mémoire:", mem_str)
        elif remote_os == "linux":
            # Récupérer le nombre de CPUs via lscpu
            cpu_command = "lscpu | grep '^CPU(s):' | awk '{print $2}'"
            cpu_result = client.exec_command(cpu_command)[1].read().decode('utf-8', errors='replace').strip()
            if cpu_result.isdigit():
                logical_processors = int(cpu_result)
            # Récupérer la mémoire via free -g
            ram_command = "free -g | grep '^Mem:' | awk '{print $2}'"
            ram_output = client.exec_command(ram_command)[1].read().decode('utf-8', errors='replace').strip()
            if ram_output.isdigit():
                total_memory = int(ram_output)
        else:
            print("OS non supporté, utilisation de valeurs par défaut.")

        max_cpu = min(logical_processors, 16)
        print(f"Remote - Max CPU: {max_cpu}, Total RAM: {total_memory} Go")
        client.close()
        return jsonify({"maxCpu": max_cpu, "totalMemoryGB": total_memory}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"maxCpu": 8, "totalMemoryGB": 16, "error": str(e)}), 200
@app.route('/stop-vm', methods=['POST']) 
def stop_vm():
    """
    Arrête la VM spécifiée, en local ou en mode distant.
    Si la VM n'est pas trouvée, renvoie un message d'erreur.
    """
    try:
        data = request.get_json()
        mode = data.get("mode", "local")  # "local" par défaut
        vm_name = data.get("vm_name")
        if not vm_name:
            return jsonify({"error": "vm_name is required"}), 400

        if mode == "local":
            vm_path = os.path.join(".", "vms", vm_name)
            if not os.path.exists(vm_path):
                return jsonify({"error": "VM not found"}), 404
            # Arrêter la VM en local (commande correcte: vagrant halt)
            subprocess.run(["vagrant", "halt"], cwd=vm_path, check=True)
            return jsonify({"message": f"VM {vm_name} stopped locally"}), 200
        else:
            # Mode distant : vérification des paramètres de connexion
            remote_ip = data.get("remote_ip")
            remote_user = data.get("remote_user")
            remote_password = data.get("remote_password")
            remote_os = data.get("remote_os", "Windows").lower()
            if not remote_ip or not remote_user or not remote_password:
                return jsonify({"error": "Remote connection parameters missing"}), 400

            # Établir la connexion SSH via Paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)
            sftp = client.open_sftp()
            try:
                sftp.chdir("vms")
                sftp.chdir(vm_name)
            except IOError:
                sftp.close()
                client.close()
                return jsonify({"error": "VM not found on remote host"}), 404
            remote_vm_folder = sftp.getcwd()

            # Exécuter "vagrant halt" sur la machine distante
            if remote_os == "windows":
                folder = remote_vm_folder.lstrip("/")
                command = f'cd /d "{folder}" && vagrant halt'
            else:
                command = f'cd "{remote_vm_folder}" && vagrant halt'
            stdin, stdout, stderr = client.exec_command(command)
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
            sftp.close()
            client.close()
            if err.strip():
                return jsonify({"error": err}), 500
            return jsonify({"message": f"VM {vm_name} stopped remotely", "output": out}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route('/delete-vm', methods=['POST'])
def delete_vm():
    """
    Supprime (détruit) la VM spécifiée, en local ou en mode distant.
    Tente d'arrêter la VM avant la destruction.
    """
    try:
        data = request.get_json()
        mode = data.get("mode", "local")  # "local" par défaut
        vm_name = data.get("vm_name")
        print(data)
        if not vm_name:
            return jsonify({"error": "vm_name is required"}), 400

        if mode == "local":
            vm_path = os.path.join(".", "vms", vm_name)
            if not os.path.exists(vm_path):
                return jsonify({"error": "VM not found"}), 404

            # Tenter d'arrêter la VM avant de la détruire
            subprocess.run(["vagrant", "halt"], cwd=vm_path, check=False)
            #time.sleep(5)  # Attendre quelques secondes pour que la VM s'arrête
            subprocess.run(["vagrant", "destroy", "-f"], cwd=vm_path, check=True)
            return jsonify({"message": f"VM {vm_name} deleted locally"}), 200

        else:
            # Mode distant : vérification des paramètres de connexion
            remote_ip = data.get("remote_ip")
            remote_user = data.get("remote_user")
            remote_password = data.get("remote_password")
            remote_os = data.get("remote_os", "Windows").lower()
            if not remote_ip or not remote_user or not remote_password:
                return jsonify({"error": "Remote connection parameters missing"}), 400

            # Établir la connexion SSH via Paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)
            sftp = client.open_sftp()
            try:
                sftp.chdir("vms")
                sftp.chdir(vm_name)
            except IOError:
                sftp.close()
                client.close()
                return jsonify({"error": "VM not found on remote host"}), 404
            remote_vm_folder = sftp.getcwd()

            # Tenter d'arrêter la VM sur la machine distante
            if remote_os == "windows":
                folder = remote_vm_folder.lstrip("/")
                halt_cmd = f'cd /d "{folder}" && vagrant halt'
            else:
                halt_cmd = f'cd "{remote_vm_folder}" && vagrant halt'
            client.exec_command(halt_cmd)
            time.sleep(5)  # Attendre quelques secondes après l'arrêt

            # Exécuter "vagrant destroy -f" sur la machine distante
            if remote_os == "windows":
                folder = remote_vm_folder.lstrip("/")
                command = f'cd /d "{folder}" && vagrant destroy -f'
            else:
                command = f'cd "{remote_vm_folder}" && vagrant destroy -f'
            stdin, stdout, stderr = client.exec_command(command)
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
            sftp.close()
            client.close()
            if err.strip():
                return jsonify({"error": err}), 500
            return jsonify({"message": f"VM {vm_name} deleted remotely", "output": out}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/start-vm', methods=['POST'])
def start_vm():
    """
    Démarre la VM spécifiée, en local ou en mode distant.
    Si la VM n'est pas trouvée, renvoie un message d'erreur.
    """
    try:
        data = request.get_json()
        mode = data.get("mode", "local")  # "local" par défaut
        vm_name = data.get("vm_name")
        if not vm_name:
            return jsonify({"error": "vm_name is required"}), 400

        if mode == "local":
            vm_path = os.path.join(".", "vms", vm_name)
            if not os.path.exists(vm_path):
                return jsonify({"error": "VM not found"}), 404
            # Démarrer la VM en local
            subprocess.run(["vagrant", "up"], cwd=vm_path, check=True)
            return jsonify({"message": f"VM {vm_name} started locally"}), 200
        else:
            # Mode distant : vérification des paramètres de connexion
            remote_ip = data.get("remote_ip")
            remote_user = data.get("remote_user")
            remote_password = data.get("remote_password")
            remote_os = data.get("remote_os", "Windows").lower()
            if not remote_ip or not remote_user or not remote_password:
                return jsonify({"error": "Remote connection parameters missing"}), 400

            # Établir la connexion SSH via Paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)
            sftp = client.open_sftp()
            try:
                sftp.chdir("vms")
                sftp.chdir(vm_name)
            except IOError:
                sftp.close()
                client.close()
                return jsonify({"error": "VM not found on remote host"}), 404
            remote_vm_folder = sftp.getcwd()

            # Exécuter "vagrant up" sur la machine distante
            if remote_os == "windows":
                folder = remote_vm_folder.lstrip("/")
                command = f'cd /d "{folder}" && vagrant up'
            else:
                command = f'cd "{remote_vm_folder}" && vagrant up'
            stdin, stdout, stderr = client.exec_command(command)
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
            sftp.close()
            client.close()
            if err.strip():
                return jsonify({"error": err}), 500
            return jsonify({"message": f"VM {vm_name} started remotely", "output": out}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

def parse_ssh_config(ssh_config_raw):
    """
    Parse la sortie de `vagrant ssh-config` pour extraire HostName, Port et IdentityFile.
    Retourne un tuple (host, port, identity_file).
    """
    host = "127.0.0.1"
    port = "22"
    identity_file = None

    for line in ssh_config_raw.splitlines():
        line = line.strip()
        if line.startswith("HostName"):
            # Exemple: HostName 127.0.0.1
            host = line.split()[1]
        elif line.startswith("Port"):
            # Exemple: Port 2222
            port = line.split()[1]
        elif line.startswith("IdentityFile"):
            # Exemple: IdentityFile C:/Users/User/.../private_key
            identity_file = " ".join(line.split()[1:])  # Au cas où il y a des espaces
            identity_file = identity_file.strip('"')    # Retire les guillemets si présents
    return host, port, identity_file

@app.route('/open-terminal-vm', methods=['POST'])
def open_terminal_vm():
    """
    Tente d'ouvrir un terminal CMD local pour se connecter en SSH à la VM (mode local).
    - Ne fonctionne que si Flask tourne sur la même machine que l'utilisateur.
    - Sur Windows, utilise 'start cmd /k ssh ...'.
    - Nécessite un environnement interactif (pas un service).
    """
    try:
        data = request.get_json()
        vm_name = data.get("vm_name")
        if not vm_name:
            return jsonify({"error": "vm_name is required"}), 400

        # Chemin local de la VM
        vm_path = os.path.join(".", "vms", vm_name)
        if not os.path.exists(vm_path):
            return jsonify({"error": "VM not found"}), 404

        # Exécute vagrant ssh-config pour récupérer HostName, Port, IdentityFile
        ssh_config_raw = subprocess.check_output(
            ["vagrant", "ssh-config"], 
            cwd=vm_path, 
            universal_newlines=True
        )

        host, port, identity_file = parse_ssh_config(ssh_config_raw)
        if not identity_file:
            return jsonify({"error": "Could not parse IdentityFile from ssh-config"}), 500

        # Commande SSH
        ssh_cmd = f'ssh -p {port} -i "{identity_file}" vagrant@{host}'

        # Sur Windows, on peut ouvrir un cmd avec la commande 'start cmd /k ...'
        # shell=True est nécessaire pour interpréter 'start' et d'autres builtins cmd.
        subprocess.Popen(f'start cmd /k {ssh_cmd}', shell=True)

        return jsonify({"message": "Local terminal opened"}), 200
    except subprocess.CalledProcessError as e:
        # Si vagrant ssh-config renvoie un code non nul
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/get-cpu-info', methods=['GET'])
def get_cpu_info():
    """
    Récupère le nombre de processeurs logiques et la mémoire totale de la machine où tourne Flask.
    - Sur Windows, utilise PowerShell pour les CPUs et systeminfo pour la RAM.
    - Sur Linux, utilise lscpu pour les CPUs et free -g pour la RAM.
    """
    try:
        os_type = platform.system()
        
        total_memory = 16
        if os_type == "Windows":
            # Récupérer le nombre de processeurs logiques via PowerShell
            cpu_command = (
                'powershell -Command "Get-WmiObject Win32_Processor | '
                'Measure-Object -Sum -Property NumberOfLogicalProcessors | '
                'Select-Object -ExpandProperty Sum"'
            )
            cpu_result = subprocess.check_output(cpu_command, shell=True, universal_newlines=True).strip()
            if cpu_result.isdigit():
                logical_processors = int(cpu_result)

              # Récupérer la mémoire physique totale via systeminfo
            ram_command = r'systeminfo | findstr /C:"Mémoire physique totale"'
            # Utilisation de l'encodage cp850 (souvent utilisé par systeminfo)
            ram_output = subprocess.check_output(ram_command, shell=True, universal_newlines=True, encoding="cp850").strip()
            print("Sortie de systeminfo:", ram_output)
            # Utiliser une expression régulière pour extraire le nombre (en Mo)
            match = re.search(r"([\d\.,]+)", ram_output)
            if match:
                mem_str = match.group(1)
                mem_str = mem_str.replace(",", ".")  # Convertir la virgule en point
                try:
                    mem_mb = float(mem_str)
                    print(mem_mb)
                    # Convertir de Mo en Go (arrondi en entier)
                    total_memory = int(mem_mb)
                    print("Total Memory:", total_memory, "Go")
                except ValueError:
                    print("Impossible de convertir la mémoire:", mem_str)

        elif os_type == "Linux":
            cpu_command = "lscpu | grep '^CPU(s):' | awk '{print $2}'"
            cpu_result = subprocess.check_output(cpu_command, shell=True, universal_newlines=True).strip()
            if cpu_result.isdigit():
                logical_processors = int(cpu_result)

            ram_command = "free -g | grep '^Mem:' | awk '{print $2}'"
            ram_output = subprocess.check_output(ram_command, shell=True, universal_newlines=True).strip()
            if ram_output.isdigit():
                total_memory = int(ram_output)
        else:
            print("OS non supporté, utilisation de valeurs par défaut.")
    

        # Définir la valeur maximale de vCPU (max = 18)
        max_cpu = min(logical_processors, 16)
        print(f"Max CPU: {max_cpu}, Total RAM: {total_memory} Go")

        return jsonify({"maxCpu": max_cpu, "totalMemoryGB": total_memory}), 200

    except Exception as e:
        traceback.print_exc()
        print("Erreur lors de la récupération des infos CPU/RAM:", e)
        return jsonify({"maxCpu": 18, "totalMemoryGB": 20}), 200  # Valeurs par défaut en cas d'erreur

def configure_ssh_with_powershell():
    """
    Configure OpenSSH Server via PowerShell sur Windows.
    Nécessite des privilèges administratifs.
    """
    commands = [
        "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0",
        "Start-Service sshd",
        "Set-Service -Name sshd -StartupType 'Automatic'",
        "New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22"
    ]
    for cmd in commands:
        try:
            subprocess.run(["powershell", "-Command", cmd], check=True)
            print("Commande PowerShell exécutée :", cmd)
        except subprocess.CalledProcessError as e:
            print("Erreur lors de l'exécution de la commande PowerShell :", cmd, "\nErreur :", e)
    print("Configuration SSH via PowerShell terminée.")

def send_email_with_vm_credentials(recipient_email, vm_details):
    """
    Envoie un email avec les informations de la VM.
    Configurer les variables SMTP avant utilisation.
    """
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = "yourguidetocs@gmail.com"
    SMTP_PASSWORD = "qcuo axza wjfa aunb"        

    msg = EmailMessage()
    msg["Subject"] = f"Votre VM {vm_details.get('vm_name')} est créée"
    msg["From"] = SMTP_USER
    msg["To"] = recipient_email
    content = f"""
Bonjour,

Votre machine virtuelle a été créée avec succès.

Nom de la VM: {vm_details.get('vm_name')}
Adresse IP: {vm_details.get('ipAddress')}
Port SSH: {vm_details.get('port')}
Chemin distant de la VM: {vm_details.get('remote_vm_folder')}


Cordialement,
L'équipe yourguidetocs
"""
    msg.set_content(content)
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("Email envoyé à", recipient_email)
    except Exception as e:
        print("Échec de l'envoi d'email :", e)

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
    recipient_email = data.get("mail")  # Champ email

    if not vm_name or not box or not ram or not cpu:
        return jsonify({"error": "Missing parameters"}), 400

    memory_mb = int(float(ram) * 1024)

    network_config = ""
    ip_address = ""
    if network != "NAT":
        ip_address = f"192.168.56.{random.randint(2, 254)}"
        network_config = f'  config.vm.network "private_network", ip: "{ip_address}"\n'

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

    vm_path = os.path.join(".", "vms", vm_name)
    os.makedirs(vm_path, exist_ok=True)

    vagrantfile_path = os.path.join(vm_path, "Vagrantfile")
    with open(vagrantfile_path, "w") as vf:
        vf.write(vagrantfile_content)

    try:
        subprocess.run(["vagrant", "up"], cwd=vm_path, check=True)

        if network == "NAT":
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
            port = "22"

        vm_details = {
            "message": f"VM {vm_name} is created",
            "vm_name": vm_name,
            "ipAddress": ip_address,
            "port": port,
            "vm_folder_path": os.path.abspath(vm_path)
        }
        if recipient_email:
            send_email_with_vm_credentials(recipient_email, vm_details)
        
        return jsonify(vm_details), 200
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/create-vm-remote", methods=["POST"])
def create_vm_remote():
    """
    Crée une VM sur une machine distante via SSH + Vagrant,
    installe Vagrant si nécessaire, configure SSH via PowerShell en cas d'échec,
    et copie le Vagrantfile sur la machine source.
    Un email est envoyé avec les informations de la VM.
    """
    try:
        data = request.get_json()

        # ------------------- Paramètres de connexion SSH -------------------
        remote_ip = data.get('remote_ip')
        remote_user = data.get('remote_user')
        remote_password = data.get('remote_password')
        remote_os = data.get('remote_os', 'Windows').lower()
        recipient_email = data.get("mail")  # Nouveau champ email

        # ------------------- Paramètres de la VM -------------------
        vm_name = data.get("vm_name", "DefaultVM")
        box = data.get("box", "ubuntu/bionic64")
        ram = float(data.get("ram", 1))  # en GB
        cpu = int(data.get("cpu", 1))
        network = data.get("network", "NAT")

        if not vm_name:
            return jsonify({"error": "vm_name is required"}), 400

        memory_mb = int(ram * 1024)

        network_config = ""
        ip_address_generated = ""
        if network != "NAT":
            ip_address_generated = f"192.168.0.{random.randint(2,254)}"
            network_config = f'  config.vm.network "private_network", ip: "{ip_address_generated}"\n'

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
        try:
            client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)
        except Exception as ssh_err:
            print("Échec de la connexion SSH :", ssh_err)
            print("Tentative de configuration SSH via PowerShell...")
            configure_ssh_with_powershell()
            # Retry la connexion
            client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)
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

        remote_vm_folder = sftp.getcwd()
        print(f"DEBUG - Dossier de la VM sur la machine distante : {remote_vm_folder}")

        # ------------------- 5) Écrire le Vagrantfile -------------------
        remote_vagrantfile_path = "Vagrantfile"
        with sftp.open(remote_vagrantfile_path, 'w') as remote_file:
            remote_file.write(vagrantfile_content)
        print("DEBUG - Vagrantfile écrit dans", remote_vagrantfile_path)

        # ------------------- 6) Exécuter 'vagrant up' -------------------
        if remote_os == 'windows':
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
            print("DEBUG - Résultat de vagrant ssh-config:", ssh_config)
            for line in ssh_config.splitlines():
                if line.strip().startswith("HostName"):
                    ip_address = line.strip().split()[1]
                if line.strip().startswith("Port"):
                    port = line.strip().split()[1]
            # Si aucune information n'est récupérée, utiliser des valeurs par défaut
            if not ip_address:
                ip_address = "127.0.0.1"
                print("DEBUG - Aucune IP trouvée dans ssh-config, utilisation de 127.0.0.1 par défaut.")
            if not port:
                port = "2222"
                print("DEBUG - Aucun port trouvé dans ssh-config, utilisation de 2222 par défaut.")
        else:
            ip_address = ip_address_generated
            port = "22"
        print(ip_address)


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

        vm_details = {
            "message": f"VM {vm_name} created remotely",
            "vm_name": vm_name,
            "remote_vm_folder": remote_vm_folder,
            "ipAddress": ip_address,
            "port": port,
            "vm_status": vm_status,
            "local_vagrantfile": os.path.abspath(local_vagrantfile_path)
        }
        if recipient_email:
            send_email_with_vm_credentials(recipient_email, vm_details)
        
        return jsonify(vm_details), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

###################################################################################################################
###############################################CLUSTER HADOOP######################################################
def get_cluster_folder(cluster_name):
    """
    Crée (si nécessaire) et retourne le chemin vers le dossier dédié au cluster.
    Le dossier sera situé dans 'clusters/<cluster_name>'.
    """
    base_folder = "clusters"
    os.makedirs(base_folder, exist_ok=True)
    folder = os.path.join(base_folder, cluster_name)
    os.makedirs(folder, exist_ok=True)
    return folder

def generate_vagrantfile(cluster_data):
    """
    Génère un Vagrantfile dynamique pour le cluster.
    Pour chaque nœud, on définit :
      - La box (ici par défaut "ubuntu/bionic64" ou tel que transmis)
      - Le hostname (tel que saisi dans le formulaire)
      - Une interface réseau en private_network avec l'IP fixée
      - Les ressources (mémoire et CPU) avec une personnalisation du nom via vb.customize
    """
    node_details = cluster_data.get("nodeDetails", [])
    vagrantfile = 'Vagrant.configure("2") do |config|\n'
    for node in node_details:
        hostname = node.get("hostname")
        os_version = node.get("osVersion", "ubuntu/bionic64")
        ram = node.get("ram", 4)    # en GB
        cpu = node.get("cpu", 2)
        ip = node.get("ip")
        ram_mb = int(ram * 1024)
        
        vagrantfile += f'''  config.vm.define "{hostname}" do |machine|
    machine.vm.box = "{os_version}"
    machine.vm.hostname = "{hostname}"
    machine.vm.network "private_network", ip: "{ip}"
    machine.vm.provider "virtualbox" do |vb|
      vb.name = "{hostname}"
      vb.customize ["modifyvm", :id, "--name", "{hostname}"]
      vb.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
      vb.customize ["modifyvm", :id, "--natdnsproxy1", "on"]

      vb.memory = "{ram_mb}"
      vb.cpus = {cpu}
    end
  end\n'''
    vagrantfile += "end\n"
    return vagrantfile
###################################################################################################################
@app.route('/create_cluster', methods=['POST'])
def create_cluster():
    # 1. Récupérer les données envoyées par le front-end
    cluster_data = request.get_json()
    if not cluster_data:
        return jsonify({"error": "No data received"}), 400

    cluster_name = cluster_data.get("clusterName")
    if not cluster_name:
        return jsonify({"error": "Cluster name is required"}), 400

    # Création du dossier dédié pour le cluster
    cluster_folder = get_cluster_folder(cluster_name)

    # 2. Génération et écriture du Vagrantfile dans le dossier dédié
    vagrantfile_content = generate_vagrantfile(cluster_data)
    vagrantfile_path = os.path.join(cluster_folder, "Vagrantfile")
    try:
        with open(vagrantfile_path, "w") as vf:
            vf.write(vagrantfile_content)
    except Exception as e:
        return jsonify({"error": "Error writing Vagrantfile", "details": str(e)}), 500

    # 3. Lancement des VMs via 'vagrant up' dans le dossier du cluster
    try:
        subprocess.run(["vagrant", "up"], cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error during 'vagrant up'", "details": str(e)}), 500

    # 4. Génération de l'inventaire Ansible
    node_details = cluster_data.get("nodeDetails", [])
    inventory_lines = []
    namenode_lines = []
    resourcemanager_lines = []
    datanodes_lines = []
    nodemanagers_lines = []
    
    for node in node_details:
        hostname = node.get("hostname")
        ip = node.get("ip")
        if node.get("isNameNode"):
            namenode_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isResourceManager"):
            resourcemanager_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isDataNode"):
            datanodes_lines.append(f"{hostname} ansible_host={ip}")
            # Assurer la data locality : un DataNode est aussi NodeManager
            nodemanagers_lines.append(f"{hostname} ansible_host={ip}")
    
        if namenode_lines:
            inventory_lines.append("[namenode]")
            inventory_lines.extend(namenode_lines)
        if resourcemanager_lines:
            inventory_lines.append("[resourcemanager]")
            inventory_lines.extend(resourcemanager_lines)
        if datanodes_lines:
            inventory_lines.append("[datanodes]")
            inventory_lines.extend(datanodes_lines)
        if nodemanagers_lines:
            inventory_lines.append("[nodemanagers]")
            inventory_lines.extend(nodemanagers_lines)
        
        inventory_content = "\n".join(inventory_lines)
        # Ajout de variables globales pour définir l'utilisateur SSH et l'interpréteur Python
        global_vars = "[all:vars]\nansible_user=vagrant\nansible_python_interpreter=/usr/bin/python3\nansible_ssh_common_args='-o StrictHostKeyChecking=no'\n\n"
        inventory_content = global_vars + inventory_content

        inventory_path = os.path.join(cluster_folder, "inventory.ini")
        try:
            with open(inventory_path, "w", encoding="utf-8") as inv_file:
                inv_file.write(inventory_content)
        except Exception as e:
            return jsonify({"error": "Error writing inventory file", "details": str(e)}), 500
    # 5. Installer Ansible sur le NameNode et configurer SSH sur les autres nœuds
    # Trouver le NameNode (premier nœud marqué isNameNode)
    namenode = None
    for node in node_details:
        if node.get("isNameNode"):
            namenode = node
            break
    if not namenode:
        return jsonify({"error": "No NameNode defined"}), 400
    namenode_hostname = namenode.get("hostname")
    namenode_ip = namenode.get("ip")  # pour le copier-coller de Hadoop
    
    # a. Installer Ansible sur le NameNode (s'il n'est pas déjà installé)
    try:
        check_ansible_cmd = f'vagrant ssh {namenode_hostname} -c "which ansible"'
        result = subprocess.run(check_ansible_cmd, shell=True, cwd=cluster_folder,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if not result.stdout.strip():
            install_ansible_cmd = f'vagrant ssh {namenode_hostname} -c "sudo apt-get update && sudo apt-get install -y ansible"'
            subprocess.run(install_ansible_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing ansible on NameNode", "details": str(e)}), 500
    # b. configuration de sssssssssh
 # --- Configuration SSH pour le NameNode ---
    try:
        # Générer une clé SSH sur le NameNode si elle n'existe pas et récupérer la clé publique
        gen_key_cmd = f'vagrant ssh {namenode_hostname} -c "test -f ~/.ssh/id_rsa.pub || ssh-keygen -t rsa -N \'\' -f ~/.ssh/id_rsa"'
        subprocess.run(gen_key_cmd, shell=True, cwd=cluster_folder, check=True)

        get_pubkey_cmd = f'vagrant ssh {namenode_hostname} -c "cat ~/.ssh/id_rsa.pub"'
        result_pub = subprocess.run(get_pubkey_cmd, shell=True, cwd=cluster_folder,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      universal_newlines=True, check=True)
        namenode_public_key = result_pub.stdout.strip()
        print("Public key du NameNode récupérée :", namenode_public_key)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error generating or retrieving SSH key on NameNode", "details": str(e)}), 500

    # Ajouter la clé du NameNode à son propre authorized_keys (pour permettre SSH local)
    try:
        add_self_key_cmd = (
            f'vagrant ssh {namenode_hostname} -c "mkdir -p ~/.ssh && '
            f'grep -q \'{namenode_public_key}\' ~/.ssh/authorized_keys || echo \'{namenode_public_key}\' >> ~/.ssh/authorized_keys && '
            f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
        )
        subprocess.run(add_self_key_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error configuring self SSH key on NameNode", "details": str(e)}), 500

    # --- Configuration SSH pour les autres nœuds ---
    for node in node_details:
        node_hostname = node.get("hostname")
        if node_hostname != namenode_hostname:
            try:
                # Générer une clé SSH sur le nœud s'il n'existe pas
                gen_key_cmd = f'vagrant ssh {node_hostname} -c "test -f ~/.ssh/id_rsa.pub || ssh-keygen -t rsa -N \'\' -f ~/.ssh/id_rsa"'
                subprocess.run(gen_key_cmd, shell=True, cwd=cluster_folder, check=True)

                # Récupérer la clé publique du nœud
                get_pubkey_cmd = f'vagrant ssh {node_hostname} -c "cat ~/.ssh/id_rsa.pub"'
                result_pub = subprocess.run(get_pubkey_cmd, shell=True, cwd=cluster_folder,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            universal_newlines=True, check=True)
                node_public_key = result_pub.stdout.strip()
                print(f"Public key du nœud {node_hostname} récupérée :", node_public_key)

                safe_node_public_key = shlex.quote(node_public_key)

                # Ajouter la clé du nœud dans son propre authorized_keys (pour SSH local)
                add_self_key_cmd = (
                    f'vagrant ssh {node_hostname} -c "mkdir -p ~/.ssh && '
                    f'grep -q {safe_node_public_key} ~/.ssh/authorized_keys || echo {safe_node_public_key} >> ~/.ssh/authorized_keys && '
                    f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                )
                subprocess.run(add_self_key_cmd, shell=True, cwd=cluster_folder, check=True)

                # Ajouter la clé du NameNode dans l'authorized_keys du nœud (pour que le NameNode puisse s'y connecter)
                add_namenode_key_cmd = (
                    f'vagrant ssh {node_hostname} -c "mkdir -p ~/.ssh && '
                    f'grep -q {shlex.quote(namenode_public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(namenode_public_key)} >> ~/.ssh/authorized_keys && '
                    f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                )
                subprocess.run(add_namenode_key_cmd, shell=True, cwd=cluster_folder, check=True)

                # Ajouter la clé du nœud dans l'authorized_keys du NameNode (pour la connexion inverse)
                add_node_key_to_namenode_cmd = (
                    f'vagrant ssh {namenode_hostname} -c "mkdir -p ~/.ssh && '
                    f'grep -q {safe_node_public_key} ~/.ssh/authorized_keys || echo {safe_node_public_key} >> ~/.ssh/authorized_keys && '
                    f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                )
                subprocess.run(add_node_key_to_namenode_cmd, shell=True, cwd=cluster_folder, check=True)

            except subprocess.CalledProcessError as e:
                return jsonify({"error": f"Error configuring SSH for node {node_hostname}", "details": str(e)}), 500

    # 6. Installation de Hadoop sur le NameNode (si nécessaire) et mise à jour de l'archive dans le dossier partagé
    try:
        # Vérifier directement sur la VM si l'archive Hadoop existe déjà dans le dossier partagé (/vagrant)
        check_archive_cmd = f'vagrant ssh {namenode_hostname} -c "test -f /vagrant/hadoop.tar.gz"'
        result = subprocess.run(check_archive_cmd, shell=True, cwd=cluster_folder)
        if result.returncode != 0:
            # L'archive n'existe pas dans /vagrant : on installe Hadoop sur le NameNode
            hadoop_install_cmd = (
                f'vagrant ssh {namenode_hostname} -c "sudo apt-get update && sudo apt-get install -y wget && '
                f'wget -O /tmp/hadoop.tar.gz https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz && '
                f'test -s /tmp/hadoop.tar.gz && '
                f'sudo tar -xzvf /tmp/hadoop.tar.gz -C /opt && '
                f'sudo mv /opt/hadoop-3.3.1 /opt/hadoop && '
                f'rm /tmp/hadoop.tar.gz"'
            )
            subprocess.run(hadoop_install_cmd, shell=True, cwd=cluster_folder, check=True)

            # Créer l'archive Hadoop sur le NameNode
            tar_hadoop_cmd = f'vagrant ssh {namenode_hostname} -c "sudo tar -czf /tmp/hadoop.tar.gz -C /opt hadoop"'
            subprocess.run(tar_hadoop_cmd, shell=True, cwd=cluster_folder, check=True)

            # Copier l'archive dans le dossier partagé (/vagrant)
            copy_to_shared_cmd = f'vagrant ssh {namenode_hostname} -c "sudo cp /tmp/hadoop.tar.gz /vagrant/hadoop.tar.gz"'
            subprocess.run(copy_to_shared_cmd, shell=True, cwd=cluster_folder, check=True)
        else:
            print("L'archive Hadoop existe déjà dans /vagrant/hadoop.tar.gz, on l'utilise pour mettre à jour le NameNode.")
            # Même si l'archive existe, on extrait sur le NameNode pour mettre à jour /opt/hadoop
            extract_cmd = f'vagrant ssh {namenode_hostname} -c "sudo rm -rf /opt/hadoop && sudo tar -xzf /vagrant/hadoop.tar.gz -C /opt"'
            subprocess.run(extract_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing Hadoop on NameNode", "details": str(e)}), 500

    # 7. Copier l'archive Hadoop vers les autres nœuds depuis le dossier partagé
    for node in node_details:
        if node.get("hostname") != namenode_hostname:
            target_hostname = node.get("hostname")
            try:
                copy_hadoop_cmd = (
                    f'vagrant ssh {target_hostname} -c "sudo apt-get update && sudo apt-get install -y openssh-client && '
                    f'sudo rm -rf /opt/hadoop && '
                    f'sudo tar -xzf /vagrant/hadoop.tar.gz -C /opt"'
                )
                subprocess.run(copy_hadoop_cmd, shell=True, cwd=cluster_folder, check=True)
            except subprocess.CalledProcessError as e:
                return jsonify({
                    "error": f"Error copying Hadoop to node {target_hostname}",
                    "details": str(e)
                }), 500

# Installer Java et net-tools et configurer les variables d'environnement sur tous les nœuds
    for node in node_details:
            target_hostname = node.get("hostname")
            try:
                install_java_net_cmd = (
                    f'vagrant ssh {target_hostname} -c "sudo apt-get update && sudo apt-get install -y default-jdk net-tools python3"'
                )
                subprocess.run(install_java_net_cmd, shell=True, cwd=cluster_folder, check=True)
                configure_env_cmd = (
                    f'vagrant ssh {target_hostname} -c "echo \'export JAVA_HOME=/usr/lib/jvm/default-java\' >> ~/.bashrc && '
                    f'echo \'export HADOOP_HOME=/opt/hadoop\' >> ~/.bashrc && '
                    f'echo \'export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin\' >> ~/.bashrc"'
                )
                subprocess.run(configure_env_cmd, shell=True, cwd=cluster_folder, check=True)
            except subprocess.CalledProcessError as e:
                return jsonify({"error": f"Error installing Java/net/python or configuring environment on node {target_hostname}", "details": str(e)}), 500

  # 7. Création des playbooks Ansible et des templates Jinja2 pour la configuration Hadoop

    # Créer le dossier "templates" pour stocker les fichiers de configuration Jinja2
    templates_dir = os.path.join(cluster_folder, "templates")
    os.makedirs(templates_dir, exist_ok=True)

    # Template pour core-site.xml
    core_site_template = """<configuration>
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://{{ namenode_hostname }}:9000</value>
  </property>
</configuration>
"""
    with open(os.path.join(templates_dir, "core-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(core_site_template)

    # Template pour hdfs-site.xml (ajout du port 9870 pour l'interface Web)
    hdfs_site_template = """<configuration>
  <property>
    <name>dfs.replication</name>
    <value>2</value>
  </property>
  <property>
    <name>dfs.namenode.http-address</name>
    <value>{{ namenode_hostname }}:9870</value>
  </property>
</configuration>
"""
    with open(os.path.join(templates_dir, "hdfs-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(hdfs_site_template)

    # Template pour yarn-site.xml
    yarn_site_template = """<configuration>
  <property>
    <name>yarn.resourcemanager.hostname</name>
    <value>{{ namenode_hostname }}</value>
  </property>
</configuration>
"""
    with open(os.path.join(templates_dir, "yarn-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(yarn_site_template)

    # Template pour mapred-site.xml
    mapred_site_template = """<configuration>
  <property>
    <name>mapreduce.framework.name</name>
    <value>yarn</value>
  </property>
</configuration>
"""
    with open(os.path.join(templates_dir, "mapred-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(mapred_site_template)

    # Template pour le fichier masters (contenant le nom du NameNode)
    masters_template = """{{ groups['namenode'][0] }}
"""
    with open(os.path.join(templates_dir, "masters.j2"), "w", encoding="utf-8") as f:
        f.write(masters_template)

    # Template pour le fichier workers (contenant la liste des DataNodes)
    workers_template = """{% for worker in groups['datanodes'] %}
{{ worker }}
{% endfor %}
"""
    with open(os.path.join(templates_dir, "workers.j2"), "w", encoding="utf-8") as f:
        f.write(workers_template)

    # Template pour mettre à jour /etc/hosts avec tous les nœuds du cluster
    hosts_template = """# ANSIBLE GENERATED CLUSTER HOSTS
{% for host in groups['all'] %}
{{ hostvars[host]['ansible_host'] }} {{ host }}
{% endfor %}
"""
    with open(os.path.join(templates_dir, "hosts.j2"), "w", encoding="utf-8") as f:
        f.write(hosts_template)

    # Création du playbook Ansible pour configurer les fichiers de Hadoop
    hadoop_config_playbook = """---
- name: Configurer les fichiers de configuration Hadoop et /etc/hosts
  hosts: all
  become: yes
  vars:
    namenode_hostname: "{{ groups['namenode'][0] }}"
  tasks:
    - name: Déployer core-site.xml
      template:
        src: templates/core-site.xml.j2
        dest: /opt/hadoop/etc/hadoop/core-site.xml

    - name: Déployer hdfs-site.xml
      template:
        src: templates/hdfs-site.xml.j2
        dest: /opt/hadoop/etc/hadoop/hdfs-site.xml

    - name: Déployer yarn-site.xml
      template:
        src: templates/yarn-site.xml.j2
        dest: /opt/hadoop/etc/hadoop/yarn-site.xml

    - name: Déployer mapred-site.xml
      template:
        src: templates/mapred-site.xml.j2
        dest: /opt/hadoop/etc/hadoop/mapred-site.xml

    - name: Déployer le fichier masters
      template:
        src: templates/masters.j2
        dest: /opt/hadoop/etc/hadoop/masters

    - name: Déployer le fichier workers
      template:
        src: templates/workers.j2
        dest: /opt/hadoop/etc/hadoop/workers

    - name: Mettre à jour le fichier /etc/hosts avec les hôtes du cluster
      template:
        src: templates/hosts.j2
        dest: /etc/hosts
"""


    hadoop_config_playbook_path = os.path.join(cluster_folder, "hadoop_config.yml")
    with open(hadoop_config_playbook_path, "w", encoding="utf-8") as f:
        f.write(hadoop_config_playbook)

     # Création du playbook Ansible pour démarrer les services Hadoop
     # Création du playbook Ansible pour démarrer les services Hadoop
   
   
    # Création du playbook Ansible pour démarrer les services Hadoop
    hadoop_start_playbook = """---
- name: Démarrer les services Hadoop
  hosts: namenode
  become: yes
  tasks:
    - name: Mettre à jour hadoop-env.sh pour définir JAVA_HOME
      shell: |
        if grep -q '^export JAVA_HOME=' /opt/hadoop/etc/hadoop/hadoop-env.sh; then
          sed -i 's|^export JAVA_HOME=.*|export JAVA_HOME=/usr/lib/jvm/default-java|' /opt/hadoop/etc/hadoop/hadoop-env.sh;
        else
          echo 'export JAVA_HOME=/usr/lib/jvm/default-java' >> /opt/hadoop/etc/hadoop/hadoop-env.sh;
        fi
      args:
        executable: /bin/bash

    - name: Créer le répertoire /opt/hadoop/logs si nécessaire
      file:
        path: /opt/hadoop/logs
        state: directory
        owner: vagrant
        group: vagrant
        mode: '0755'

    - name: Formater le NameNode (si nécessaire)
      shell: "/opt/hadoop/bin/hdfs namenode -format -force"
      args:
        creates: /opt/hadoop/hdfs/name/current/VERSION
      become_user: vagrant
      environment:
        JAVA_HOME: /usr/lib/jvm/default-java
      executable: /bin/bash

    - name: Démarrer HDFS
      shell: "/opt/hadoop/sbin/start-dfs.sh"
      become_user: vagrant
      environment:
        JAVA_HOME: /usr/lib/jvm/default-java
        HDFS_NAMENODE_USER: vagrant
        HDFS_DATANODE_USER: vagrant
        HDFS_SECONDARYNAMENODE_USER: vagrant
      executable: /bin/bash

    - name: Démarrer YARN
      shell: "/opt/hadoop/sbin/start-yarn.sh"
      become_user: vagrant
      environment:
        JAVA_HOME: /usr/lib/jvm/default-java
      executable: /bin/bash

    - name: Démarrer explicitement le ResourceManager en arrière-plan
      shell: "nohup /opt/hadoop/bin/yarn --daemon start resourcemanager > /tmp/resourcemanager.log 2>&1 &"
      become_user: vagrant
      environment:
        JAVA_HOME: /usr/lib/jvm/default-java
      executable: /bin/bash

    - name: Pause de 10 secondes pour permettre au ResourceManager de démarrer
      pause:
        seconds: 10

    - name: Vérifier le démarrage des services Hadoop (jps)
      shell: "jps"
      register: jps_output
      become_user: vagrant
      executable: /bin/bash

    - name: Afficher les processus Hadoop
      debug:
        var: jps_output.stdout
"""
    hadoop_start_playbook_path = os.path.join(cluster_folder, "hadoop_start_services.yml")
    with open(hadoop_start_playbook_path, "w", encoding="utf-8") as f:
        f.write(hadoop_start_playbook)

    # Définir un préfixe pour la commande ansible-playbook en fonction de l'OS
    ansible_cmd_prefix = ""
    if platform.system() == "Windows":
        ansible_cmd_prefix = "wsl "

    # 8. Exécuter le playbook de configuration Hadoop sur le NameNode
    try:
        inventory_file_in_vm = os.path.basename(inventory_path)
        config_playbook_cmd = (
            f'vagrant ssh {namenode_hostname} -c "cd /vagrant && ansible-playbook -i {inventory_file_in_vm} hadoop_config.yml"'
        )
        subprocess.run(config_playbook_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error configuring Hadoop configuration files", "details": str(e)}), 500

    # 9. Exécuter le playbook pour démarrer les services Hadoop sur le NameNode
    try:
        start_playbook_cmd = (
            f'vagrant ssh {namenode_hostname} -c "cd /vagrant && ansible-playbook -i {inventory_file_in_vm} hadoop_start_services.yml"'
        )
        subprocess.run(start_playbook_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error starting Hadoop services", "details": str(e)}), 500

    return jsonify({
        "message": "Cluster created successfully, inventory generated, Ansible installed on NameNode, SSH configured, "
                   "Hadoop installed and copied, Java/net/python installed, Hadoop configuration applied and services started",
        "cluster_folder": cluster_folder,
        "inventory_file": inventory_path
    }), 200


if __name__ == '__main__':
    app.run(debug=True)