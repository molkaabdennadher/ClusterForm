
from datetime import datetime
import hashlib
import textwrap
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
    print(box)
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
    <value>{{ groups['resourcemanager'][0] }}</value>
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
- name: Démarrer le ResourceManager sur le nœud dédié
  hosts: resourcemanager
  become: yes
  tasks:
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

######################### HADOOP HA #################################HA----------------------------------------------------
def get_nameNode_hostname(cluster_data):
    """
    Récupère le hostname du NameNode principal depuis les données du cluster.
    Si plusieurs NameNodes sont trouvés, on prend le premier.
    """
    for node in cluster_data.get("nodeDetails", []):
        if node.get("isNameNode", False):
            return node["hostname"]
    return None  # Aucun NameNode trouvé

@app.route('/create_cluster_ha', methods=['POST'])
def create_cluster_ha():
 # 1. Récupérer les données du front-end
    cluster_data = request.get_json()
    if not cluster_data:
        return jsonify({"error": "No data received"}), 400

    cluster_name = cluster_data.get("clusterName")
    if not cluster_name:
        return jsonify({"error": "Cluster name is required"}), 400

# 2. Créer le dossier du cluster
    print(cluster_data)
    cluster_folder = get_cluster_folder(cluster_name)

# 3. Générer et écrire le Vagrantfile
    vagrantfile_content = generate_vagrantfile(cluster_data)
    vagrantfile_path = os.path.join(cluster_folder, "Vagrantfile")
    try:
        with open(vagrantfile_path, "w", encoding="utf-8") as vf:
            vf.write(vagrantfile_content)
    except Exception as e:
        return jsonify({"error": "Error writing Vagrantfile", "details": str(e)}), 500

# 4. Lancer les VMs via 'vagrant up'
    try:
        subprocess.run(["vagrant", "up"], cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error during 'vagrant up'", "details": str(e)}), 500
# 5. Générer l'inventaire Ansible HA
    node_details = cluster_data.get("nodeDetails", [])
    inventory_lines = []
    namenode_lines = []
    namenode_standby_lines = []
    resourcemanager_lines = []
    resourcemanager_standby_lines = []
    datanodes_lines = []
    nodemanagers_lines = []
    zookeeper_lines = []
    journalnode_lines = []

    for node in node_details:
        hostname = node.get("hostname")
        ip = node.get("ip")
        # NameNode actif et standby
        if node.get("isNameNode"):
            namenode_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isNameNodeStandby"):
            namenode_standby_lines.append(f"{hostname} ansible_host={ip}")
        # ResourceManager actif et standby
        if node.get("isResourceManager"):
            resourcemanager_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isResourceManagerStandby"):
            resourcemanager_standby_lines.append(f"{hostname} ansible_host={ip}")
        # DataNodes et NodeManagers
        if node.get("isDataNode"):
            datanodes_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isNodeManager"):
            nodemanagers_lines.append(f"{hostname} ansible_host={ip}")
        # ZooKeeper et JournalNode
        if node.get("isZookeeper"):
            zookeeper_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isJournalNode"):
            journalnode_lines.append(f"{hostname} ansible_host={ip}")

    if namenode_lines:
        inventory_lines.append("[namenode]")
        inventory_lines.extend(namenode_lines)
    if namenode_standby_lines:
        inventory_lines.append("[namenode_standby]")
        inventory_lines.extend(namenode_standby_lines)
    if resourcemanager_lines:
        inventory_lines.append("[resourcemanager]")
        inventory_lines.extend(resourcemanager_lines)
    if resourcemanager_standby_lines:
        inventory_lines.append("[resourcemanager_standby]")
        inventory_lines.extend(resourcemanager_standby_lines)
    if datanodes_lines:
        inventory_lines.append("[datanodes]")
        inventory_lines.extend(datanodes_lines)
    if nodemanagers_lines:
        inventory_lines.append("[nodemanagers]")
        inventory_lines.extend(nodemanagers_lines)
    if zookeeper_lines:
        inventory_lines.append("[zookeeper]")
        inventory_lines.extend(zookeeper_lines)
    if journalnode_lines:
        inventory_lines.append("[journalnode]")
        inventory_lines.extend(journalnode_lines)

    inventory_content = "\n".join(inventory_lines)
    global_vars = (
        "[all:vars]\n"
        "ansible_user=vagrant\n"
        "ansible_python_interpreter=/usr/bin/python3\n"
        "ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n\n"
        "java_home=/usr/lib/jvm/java-11-openjdk-amd64\n"
        "hadoop_home=/opt/hadoop\n"
    )
    inventory_content = global_vars + inventory_content

    inventory_path = os.path.join(cluster_folder, "inventory.ini")
    try:
        with open(inventory_path, "w", encoding="utf-8") as inv_file:
            inv_file.write(inventory_content)
    except Exception as e:
        return jsonify({"error": "Error writing inventory file", "details": str(e)}), 500

    # --- Installation d'Ansible sur le primary et standby NameNode ---
    try:
        namenode_hosts = [line.split()[0] for line in namenode_lines] + [line.split()[0] for line in namenode_standby_lines]

        for namenode in namenode_hosts:
            check_ansible_cmd = f'vagrant ssh {namenode} -c "which ansible-playbook"'
            result_ansible = subprocess.run(check_ansible_cmd, shell=True, cwd=cluster_folder,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            if not result_ansible.stdout.strip():
                install_ansible_cmd = f'vagrant ssh {namenode} -c "sudo apt-get update && sudo apt-get install -y ansible"'
                subprocess.run(install_ansible_cmd, shell=True, cwd=cluster_folder, check=True)
            else:
                print(f"Ansible est déjà installé sur {namenode}.")
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing Ansible on NameNodes", "details": str(e)}), 500

    # --- Configuration SSH pour les NameNodes et autres nœuds ---
    try:
        namenode_public_keys = {}

        for namenode in namenode_hosts:
            # Générer une clé SSH si elle n'existe pas
            gen_key_cmd = f'vagrant ssh {namenode} -c "test -f ~/.ssh/id_rsa.pub || ssh-keygen -t rsa -N \'\' -f ~/.ssh/id_rsa"'
            subprocess.run(gen_key_cmd, shell=True, cwd=cluster_folder, check=True)

            # Récupérer la clé publique
            get_pubkey_cmd = f'vagrant ssh {namenode} -c "cat ~/.ssh/id_rsa.pub"'
            result_pub = subprocess.run(get_pubkey_cmd, shell=True, cwd=cluster_folder,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, check=True)
            namenode_public_keys[namenode] = result_pub.stdout.strip()
            print(f"Public key de {namenode} récupérée :", namenode_public_keys[namenode])

        # Ajouter les clés dans les authorized_keys respectifs
        for namenode in namenode_hosts:
            for other_namenode, public_key in namenode_public_keys.items():
                add_key_cmd = (
                    f'vagrant ssh {namenode} -c "mkdir -p ~/.ssh && '
                    f'grep -q {shlex.quote(public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(public_key)} >> ~/.ssh/authorized_keys && '
                    f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                )
                subprocess.run(add_key_cmd, shell=True, cwd=cluster_folder, check=True)

        # Configuration SSH pour les autres nœuds
        for node in node_details:
            node_hostname = node.get("hostname")
            if node_hostname not in namenode_hosts:
                # Générer une clé SSH si elle n'existe pas
                gen_key_cmd = f'vagrant ssh {node_hostname} -c "test -f ~/.ssh/id_rsa.pub || ssh-keygen -t rsa -N \'\' -f ~/.ssh/id_rsa"'
                subprocess.run(gen_key_cmd, shell=True, cwd=cluster_folder, check=True)

                # Récupérer la clé publique
                get_pubkey_cmd = f'vagrant ssh {node_hostname} -c "cat ~/.ssh/id_rsa.pub"'
                result_pub = subprocess.run(get_pubkey_cmd, shell=True, cwd=cluster_folder,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            universal_newlines=True, check=True)
                node_public_key = result_pub.stdout.strip()
                print(f"Public key du nœud {node_hostname} récupérée :", node_public_key)

                # Ajouter la clé du nœud dans son authorized_keys
                add_self_key_cmd = (
                    f'vagrant ssh {node_hostname} -c "mkdir -p ~/.ssh && '
                    f'grep -q {shlex.quote(node_public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(node_public_key)} >> ~/.ssh/authorized_keys && '
                    f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                )
                subprocess.run(add_self_key_cmd, shell=True, cwd=cluster_folder, check=True)

                # Ajouter la clé des NameNodes dans l'authorized_keys du nœud
                for namenode, public_key in namenode_public_keys.items():
                    add_namenode_key_cmd = (
                        f'vagrant ssh {node_hostname} -c "mkdir -p ~/.ssh && '
                        f'grep -q {shlex.quote(public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(public_key)} >> ~/.ssh/authorized_keys && '
                        f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                    )
                    subprocess.run(add_namenode_key_cmd, shell=True, cwd=cluster_folder, check=True)

                    # Ajouter la clé du nœud dans l'authorized_keys des NameNodes
                    add_node_key_to_namenode_cmd = (
                        f'vagrant ssh {namenode} -c "mkdir -p ~/.ssh && '
                        f'grep -q {shlex.quote(node_public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(node_public_key)} >> ~/.ssh/authorized_keys && '
                        f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                    )
                    subprocess.run(add_node_key_to_namenode_cmd, shell=True, cwd=cluster_folder, check=True)

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error configuring SSH", "details": str(e)}), 500

# 5. Installation de ZooKeeper sur le NameNode (version corrigée pour respecter la structure souhaitée)
    nameNode_hostname = get_nameNode_hostname(cluster_data)

    """
    Installe ZooKeeper sur le NameNode :
      - Télécharge l'archive de ZooKeeper
      - Extrait l'archive dans /etc/zookeeper en supprimant les composants inutiles
      - Copie le fichier de configuration d'exemple (zoo_sample.cfg) en zoo.cfg
      - Crée les dossiers de données (/var/lib/zookeeper) et logs (/var/log/zookeeper)
      - Ajuste les droits et crée une archive compressée pour le transfert
    """
    try:
        prepare_cmd = (
            f'vagrant ssh {nameNode_hostname} -c "'
            'sudo apt-get update && '
            'sudo apt-get install -y wget && '
            'wget -O /tmp/zookeeper.tar.gz https://archive.apache.org/dist/zookeeper/zookeeper-3.6.3/apache-zookeeper-3.6.3-bin.tar.gz && '
            'sudo mkdir -p /etc/zookeeper && '
            'sudo tar -xzf /tmp/zookeeper.tar.gz -C /etc/zookeeper --strip-components=1 && '
            'sudo cp /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg && '
            'sudo mkdir -p /var/lib/zookeeper /var/log/zookeeper && '
            'sudo chown -R vagrant:vagrant /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && '
            'sudo tar -czf /tmp/zookeeper_etc.tar.gz -C /etc zookeeper"'
        )
        subprocess.run(prepare_cmd, shell=True, cwd=cluster_folder, check=True)
        print("Installation sur le NameNode réussie")
    
    except subprocess.CalledProcessError as e:
        print(f"Erreur d'installation ZooKeeper sur NameNode: {str(e)}")
# 6. Installation de Hadoop sur le primary NameNode et synchronisation de l'archive dans /vagrant
    try:
        primary_namenode = get_nameNode_hostname(cluster_data)
        if not primary_namenode:
            return jsonify({"error": "No NameNode found in cluster configuration"}), 400

        check_archive_cmd = f'vagrant ssh {primary_namenode} -c "test -f /vagrant/hadoop.tar.gz"'
        result = subprocess.run(check_archive_cmd, shell=True, cwd=cluster_folder)
        if result.returncode != 0:
            hadoop_install_cmd = (
                f'vagrant ssh {primary_namenode} -c "sudo apt-get update && sudo apt-get install -y wget && '
                f'wget -O /tmp/hadoop.tar.gz https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz && '
                f'test -s /tmp/hadoop.tar.gz && '
                f'sudo tar -xzvf /tmp/hadoop.tar.gz -C /opt && '
                f'sudo mv /opt/hadoop-3.3.1 /opt/hadoop && '
                f'rm /tmp/hadoop.tar.gz"'
            )
            subprocess.run(hadoop_install_cmd, shell=True, cwd=cluster_folder, check=True)
            tar_hadoop_cmd = f'vagrant ssh {primary_namenode} -c "sudo tar -czf /tmp/hadoop.tar.gz -C /opt hadoop"'
            subprocess.run(tar_hadoop_cmd, shell=True, cwd=cluster_folder, check=True)
            copy_to_shared_cmd = f'vagrant ssh {primary_namenode} -c "sudo cp /tmp/hadoop.tar.gz /vagrant/hadoop.tar.gz"'
            subprocess.run(copy_to_shared_cmd, shell=True, cwd=cluster_folder, check=True)
        else:
            print("L'archive Hadoop existe déjà dans /vagrant/hadoop.tar.gz, extraction sur le primary NameNode.")
            extract_cmd = f'vagrant ssh {primary_namenode} -c "sudo rm -rf /opt/hadoop && sudo tar -xzf /vagrant/hadoop.tar.gz -C /opt"'
            subprocess.run(extract_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing Hadoop on primary NameNode", "details": str(e)}), 500

    # 8.1 Synchroniser l'archive Hadoop sur les autres nœuds
    for node in cluster_data.get("nodeDetails", []):
        if node.get("hostname") != primary_namenode:
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
# 7. Transférer l’archive ZooKeeper aux autres nœuds (si besoin)
        """
    Transfère l'archive compressée du NameNode vers les nœuds ZooKeeper :
      - Utilise SCP pour copier l'archive depuis le NameNode vers /tmp sur le nœud cible
      - Sur le nœud cible, supprime l'ancien dossier /etc/zookeeper et extrait l'archive dans /etc
      - Crée les dossiers de données et logs et ajuste les permissions
    """
    for node in cluster_data.get("nodeDetails", []):
        if node.get("isZookeeper", False):
            target_hostname = node.get("hostname")
            print(target_hostname)
            target_ip = node.get("ip")  # Supposons que cluster_data contient les IPs
            
            if target_hostname and target_hostname != nameNode_hostname:
                try:
                    # Utiliser l'IP pour SCP
                    scp_cmd = (
                        f'vagrant ssh {nameNode_hostname} -c "'
                        f'scp -o StrictHostKeyChecking=no '
                        f'/tmp/zookeeper_etc.tar.gz vagrant@{target_ip}:/tmp/"'
                    )
                    subprocess.run(scp_cmd, shell=True, check=True, cwd=cluster_folder)

                    # Extraction sur le nœud cible
                    install_cmd = (
                        f'vagrant ssh {target_hostname} -c "'
                        #'sudo rm -rf /etc/zookeeper && '
                        'sudo tar -xzf /tmp/zookeeper_etc.tar.gz -C /etc && '
                        'sudo mkdir -p /etc/zookeeper/conf && '  # S'assure que conf existe
                        'sudo mkdir -p /var/lib/zookeeper /var/log/zookeeper && '
                        'sudo chown -R vagrant:vagrant /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper"'
                    )
                    subprocess.run(install_cmd, shell=True, cwd=cluster_folder, check=True)
                    
                    print(f"Transfert réussi sur {target_hostname}")
                
                except subprocess.CalledProcessError as e:
                    print(f"Erreur sur {target_hostname}: {str(e)}")

    """
    Configure le fichier /var/lib/zookeeper/myid pour chaque nœud ZooKeeper :
      - Pour chaque nœud identifié comme ZooKeeper, écrit l'ID (zookeeperId) dans le fichier myid
    """
    zk_nodes = [n for n in cluster_data.get("nodeDetails", []) if n.get("isZookeeper")]
    
    # Génération automatique des IDs manquants
    for idx, node in enumerate(zk_nodes, start=1):
        if "zookeeperId" not in node:
            node["zookeeperId"] = idx
            print(f"ATTENTION: ID généré pour {node.get('hostname')}: {idx}")
    for node in cluster_data.get("nodeDetails", []):
        if node.get("isZookeeper", False):
            hostname = node.get("hostname")
            print(hostname)
            server_id = node.get("zookeeperId")
            print(server_id)
            if hostname and server_id:
                try:
                    configure_cmd = (
                        f'vagrant ssh {hostname} -c "'
                        'sudo mkdir -p /var/lib/zookeeper && '
                        f'echo {server_id} | sudo tee /var/lib/zookeeper/myid"'
                    )
                    subprocess.run(configure_cmd, shell=True, cwd=cluster_folder, check=True)
                    print(f"Configuration myid réussie sur {hostname}")
                except subprocess.CalledProcessError as e:
                    print(f"Erreur de configuration myid sur {hostname}: {str(e)}")

# 8. Installer Java, net-tools, python3 et configurer l'environnement sur tous les nœuds
    for node in cluster_data.get("nodeDetails", []):
        target_hostname = node.get("hostname")
        try:
            install_java_net_cmd = (
                f'vagrant ssh {target_hostname} -c "sudo apt-get update && sudo apt-get install -y default-jdk net-tools python3"'
            )
            subprocess.run(install_java_net_cmd, shell=True, cwd=cluster_folder, check=True)

            # Configuration des variables d'environnement pour Hadoop
            configure_env_cmd1 = (
                f'vagrant ssh {target_hostname} -c "echo \'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64\' >> ~/.bashrc && '
                f'echo \'export HADOOP_HOME=/opt/hadoop\' >> ~/.bashrc && '
                f'echo \'export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin\' >> ~/.bashrc"'
            )
            subprocess.run(configure_env_cmd1, shell=True, cwd=cluster_folder, check=True)

            # Configuration des variables d'environnement pour ZooKeeper
            configure_env_cmd2 = (
                f'vagrant ssh {target_hostname} -c "echo \'export ZOOKEEPER_HOME=/etc/zookeeper\' >> ~/.bashrc && '
                f'echo \'export PATH=$PATH:$ZOOKEEPER_HOME/bin\' >> ~/.bashrc && '
                f'echo \'export ZOO_LOG_DIR=/var/log/zookeeper\' >> ~/.bashrc"'
                
                

            )
            subprocess.run(configure_env_cmd2, shell=True, cwd=cluster_folder, check=True)

            # Optionnel : recharger l'environnement (bien que dans un shell non-interactif, ce soit parfois inutile)
            refresh_env_cmd = f'vagrant ssh {target_hostname} -c "source ~/.bashrc"'
            subprocess.run(refresh_env_cmd, shell=True, cwd=cluster_folder, check=True)

            print(f"Configuration d'environnement terminée sur {target_hostname}")
        except subprocess.CalledProcessError as e:
            return jsonify({"error": f"Error configuring environment on node {target_hostname}", "details": str(e)}), 500

# On suppose que les variables cluster_folder, hadoop_home, java_home, cluster_data, etc. sont définies

##############################################
# Création des fichiers de configuration et playbooks HA
##############################################
    templates_dir = os.path.join(cluster_folder, "templates")
    os.makedirs(templates_dir, exist_ok=True)

    # ---- Template core-site.xml.j2 ----
    core_site_template = textwrap.dedent("""\
        <configuration>
        <!-- Point d'entrée HDFS (doit correspondre au nameservice défini dans hdfs-site.xml) -->
        <property>
            <name>fs.defaultFS</name>
            <value>hdfs://ha-cluster</value>
        </property>
        <!-- Proxy de failover pour le client HDFS -->
        <property>
            <name>dfs.client.failover.proxy.provider.ha-cluster</name>
            <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>
        </property>
        <!-- Quorum ZooKeeper pour le failover -->
        <property>
            <name>ha.zookeeper.quorum</name>
            <value>{% for zk in groups['zookeeper'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>
        </property>
        <!-- Autres paramètres utiles -->
        <property>
            <name>dfs.permissions.enabled</name>
            <value>true</value>
        </property>
        <property>
            <name>ipc.client.connect.max.retries</name>
            <value>3</value>
        </property>
        </configuration>
        """)
    with open(os.path.join(templates_dir, "core-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(core_site_template)

    # ---- Template hdfs-site.xml.j2 ----
    # On utilise ici les noms de machines tels qu'ils apparaissent dans l'inventaire (ex: ayoub12, ayoub16)
    hdfs_site_template = textwrap.dedent("""\
        <configuration>
        <!-- Réplication -->
        <property>
            <name>dfs.replication</name>
            <value>2</value>
        </property>
        <!-- Activation du mode HA -->
        <property>
            <name>dfs.nameservices</name>
            <value>ha-cluster</value>
        </property>
        <!-- Définir les deux NameNodes (utiliser les noms de machines de l'inventaire) -->
        <property>
            <name>dfs.ha.namenodes.ha-cluster</name>
            <value>{{ groups['namenode'][0] }},{{ groups['namenode_standby'][0] }}</value>
        </property>
        <!-- Adresses RPC et HTTP en se basant sur les noms de machines -->
        <property>
            <name>dfs.namenode.rpc-address.ha-cluster.{{ groups['namenode'][0] }}</name>
            <value>{{ hostvars[groups['namenode'][0]].ansible_host }}:8020</value>
        </property>
        <property>
            <name>dfs.namenode.rpc-address.ha-cluster.{{ groups['namenode_standby'][0] }}</name>
            <value>{{ hostvars[groups['namenode_standby'][0]].ansible_host }}:8020</value>
        </property>
        <property>
            <name>dfs.namenode.http-address.ha-cluster.{{ groups['namenode'][0] }}</name>
            <value>{{ hostvars[groups['namenode'][0]].ansible_host }}:50070</value>
        </property>
        <property>
            <name>dfs.namenode.http-address.ha-cluster.{{ groups['namenode_standby'][0] }}</name>
            <value>{{ hostvars[groups['namenode_standby'][0]].ansible_host }}:50070</value>
        </property>
        <!-- Répertoire partagé pour les shared edits -->
        <property>
            <name>dfs.namenode.shared.edits.dir</name>
            <value>qjournal://{% for jn in groups['journalnode'] %}{{ hostvars[jn].ansible_host }}:8485{% if not loop.last %};{% endif %}{% endfor %}/ha-cluster</value>
        </property>
        <!-- Bascule automatique -->
        <property>
            <name>dfs.ha.automatic-failover.enabled</name>
            <value>true</value>
        </property>
        <!-- Proxy failover (idem core-site) -->
        <property>
            <name>dfs.client.failover.proxy.provider.ha-cluster</name>
            <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>
        </property>
        <!-- Quorum ZooKeeper -->
        <property>
            <name>ha.zookeeper.quorum</name>
            <value>{% for zk in groups['zookeeper'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>
        </property>
        <!-- Répertoires locaux -->
        <property>
            <name>dfs.namenode.name.dir</name>
            <value>file:{{ hadoop_home }}/data/hdfs/namenode</value>
        </property>
        <property>
            <name>dfs.datanode.data.dir</name>
            <value>file:{{ hadoop_home }}/data/hdfs/datanode</value>
        </property>
        <property>
            <name>dfs.namenode.checkpoint.dir</name>
            <value>file:{{ hadoop_home }}/data/hdfs/namesecondary</value>
        </property>
        <!-- Fencing et timeout -->
        <property>
            <name>dfs.ha.fencing.methods</name>
            <value>shell(/bin/true)</value>
        </property>
        <property>
            <name>dfs.ha.failover-controller.active-standby-elector.zk.op.retries</name>
            <value>3</value>
        </property>
        </configuration>
        """)
    with open(os.path.join(templates_dir, "hdfs-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(hdfs_site_template)

    # ---- Template yarn-site.xml.j2 ----
    yarn_site_template = textwrap.dedent("""\
    <configuration>
        <!-- Paramètres HA de base -->
        <property>
            <name>yarn.resourcemanager.ha.enabled</name>
            <value>true</value>
        </property>
        <property>
            <name>yarn.resourcemanager.cluster-id</name>
            <value>yarn-cluster</value>
        </property>
        <property>
            <name>yarn.resourcemanager.ha.rm-ids</name>
            <value>rm1,rm2</value>
        </property>

        <!-- Configuration Zookeeper -->
        <property>
            <name>yarn.resourcemanager.zk-address</name>
            <value>{% for host in groups['zookeeper'] %}{{ host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>
        </property>

        <!-- Adresses des nœuds -->
        <property>
            <name>yarn.resourcemanager.hostname.rm1</name>
            <value>{{ groups['resourcemanager'][0] }}</value>
        </property>
        <property>
            <name>yarn.resourcemanager.hostname.rm2</name>
            <value>{{ groups['resourcemanager_standby'][0] }}</value>
        </property>

        <!-- Configuration du recovery -->
        <property>
            <name>yarn.resourcemanager.recovery.enabled</name>
            <value>true</value>
        </property>
        <property>
            <name>yarn.resourcemanager.store.class</name>
            <value>org.apache.hadoop.yarn.server.resourcemanager.recovery.ZKRMStateStore</value>
        </property>

        <!-- Configuration des ports -->
        <property>
            <name>yarn.resourcemanager.webapp.address.rm1</name>
            <value>{{ groups['resourcemanager'][0] }}:8088</value>
        </property>
        <property>
            <name>yarn.resourcemanager.webapp.address.rm2</name>
            <value>{{ groups['resourcemanager_standby'][0] }}:8088</value>
        </property>

        <!-- Configuration NodeManager -->
        <property>
            <name>yarn.nodemanager.resource.memory-mb</name>
            <value>4096</value>
        </property>
        <property>
            <name>yarn.nodemanager.resource.cpu-vcores</name>
            <value>4</value>
        </property>
    </configuration>
    """)
    with open(os.path.join(templates_dir, "yarn-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(yarn_site_template)

    # ---- Template mapred-site.xml.j2 ----
    mapred_site_template = textwrap.dedent("""\
        <configuration>
        <property>
            <name>mapreduce.framework.name</name>
            <value>yarn</value>
        </property>
        </configuration>
        """)
    with open(os.path.join(templates_dir, "mapred-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(mapred_site_template)

    # ---- Template masters.j2 ----
    masters_template = textwrap.dedent("""\
        {{ groups['namenode'][0] }}
        """)
    with open(os.path.join(templates_dir, "masters.j2"), "w", encoding="utf-8") as f:
        f.write(masters_template)

    # ---- Template workers.j2 ----
    workers_template = textwrap.dedent("""\
        {% for worker in groups['datanodes'] %}
        {{ worker }}
        {% endfor %}
        """)
    with open(os.path.join(templates_dir, "workers.j2"), "w", encoding="utf-8") as f:
        f.write(workers_template)

    # ---- Template zoo.cfg.j2 ----
    # Déployé dans le répertoire standard de ZooKeeper (/etc/zookeeper/conf)
    zoo_cfg_template = textwrap.dedent("""\
        tickTime=2000
        initLimit=10
        syncLimit=5
        dataDir=/var/lib/zookeeper
        clientPort=2181
        {% for zk in groups['zookeeper'] %}
        server.{{ loop.index }}={{ hostvars[zk].ansible_host }}:2888:3888
        {% endfor %}
        """)
    with open(os.path.join(templates_dir, "zoo.cfg.j2"), "w", encoding="utf-8") as f:
        f.write(zoo_cfg_template)

    # ---- Template hosts.j2 ----
    hosts_template = textwrap.dedent("""\
        # ANSIBLE GENERATED HOSTS FILE
        {% for host in groups['all'] %}
        {{ hostvars[host].ansible_host }} {{ host }}
        {% endfor %}
        """)
    with open(os.path.join(templates_dir, "hosts.j2"), "w", encoding="utf-8") as f:
        f.write(hosts_template)

    ######################################################################
    # Création du playbook de configuration HA Hadoop (hadoop_config.yml)
    ######################################################################
    hadoop_config_playbook = textwrap.dedent("""\
---
- name: Configurer HA Hadoop et mettre à jour /etc/hosts
  hosts: all
  become: yes
  vars:
    namenode_hostname: "{{ groups['namenode'][0] }}"
  tasks:
    - name: Déployer core-site.xml
      template:
        src: templates/core-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/core-site.xml"

    - name: Déployer hdfs-site.xml
      template:
        src: templates/hdfs-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/hdfs-site.xml"

    - name: Déployer yarn-site.xml
      template:
        src: templates/yarn-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/yarn-site.xml"

    - name: Déployer mapred-site.xml
      template:
        src: templates/mapred-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/mapred-site.xml"

    - name: Déployer masters
      template:
        src: templates/masters.j2
        dest: "{{ hadoop_home }}/etc/hadoop/masters"

    - name: Déployer workers
      template:
        src: templates/workers.j2
        dest: "{{ hadoop_home }}/etc/hadoop/workers"

    - name: Déployer zoo.cfg pour ZooKeeper
      template:
        src: templates/zoo.cfg.j2
        dest: "/etc/zookeeper/conf/zoo.cfg"

    - name: Mettre à jour /etc/hosts avec les hôtes du cluster
      template:
        src: templates/hosts.j2
        dest: /etc/hosts
        """)
    hadoop_config_playbook_path = os.path.join(cluster_folder, "hadoop_config.yml")
    try:
        with open(hadoop_config_playbook_path, "w", encoding="utf-8") as f:
            f.write(hadoop_config_playbook)
    except Exception as e:
        return jsonify({"error": "Error writing HA config playbook", "details": str(e)}), 500

    ############################################################################
    # Création du playbook de démarrage HA Hadoop (hadoop_start_services.yml)
    #############################################################################
    # Ordre important : démarrer ZooKeeper et JournalNodes avant le formatage du NameNode, 
    # puis initialiser HA dans ZooKeeper, formater le NameNode, et enfin démarrer HDFS/YARN.
    hadoop_start_playbook = textwrap.dedent("""\
---
- name: Démarrer ZooKeeper sur les nœuds ZooKeeper
  hosts: zookeeper
  become: yes
  tasks:
                                            
    - name: Démarrer ZooKeeper
      shell: "/etc/zookeeper/bin/zkServer.sh start"
      become_user: vagrant
      environment:
          ZOO_LOG_DIR: "/var/log/zookeeper"
          ZOO_CONF_DIR: "/etc/zookeeper/conf"
      executable: /bin/bash
                                            
    - name: Créer les répertoires de logs
      file:
        path: /opt/hadoop/logs
        state: directory
        owner: vagrant
        group: vagrant
        mode: 0755
                                            
    - name: Configurer hadoop-env.sh
      lineinfile:
        path: /opt/hadoop/etc/hadoop/hadoop-env.sh
        line: "export JAVA_HOME={{ java_home }}"
        state: present  
                                            
- name: Configuration des JournalNodes
  hosts: zookeeper
  become: yes
  tasks:
    - name: Créer le répertoire JournalNode
      file:
        path: /opt/hadoop/data/hdfs/journalnode
        state: directory
        owner: vagrant
        group: vagrant
        mode: '0755'

    - name: Démarrer JournalNode en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/hdfs --daemon start journalnode > /tmp/journalnode.log 2>&1 &"
      become_user: vagrant
      environment:
        JAVA_HOME: "{{ java_home }}"
        HADOOP_LOG_DIR: "/opt/hadoop/logs"

    - name: Vérifier que le JournalNode est actif
      wait_for:
        port: 8485
        timeout: 60

- name: Initialiser le HA dans ZooKeeper (uniquement sur le NameNode actif)
  hosts: namenode
  become: yes
  tasks:
    - name: Initialiser HA dans ZooKeeper
      shell: "{{ hadoop_home }}/bin/hdfs zkfc -formatZK -force -nonInteractive"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash
      when: inventory_hostname == groups['namenode'][0]
                                                          
- name: Formater le NameNode (si nécessaire)
  hosts: namenode
  become: yes
  tasks:
    - name: Créer le répertoire namenode
      file:
        path: "{{ hadoop_home }}/data/hdfs/namenode"
        state: directory
        owner: vagrant
        group: vagrant
        mode: '0755'
                                                                                                                               
    - name: Formater le NameNode (si nécessaire)
      shell: "{{ hadoop_home }}/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"
      args:
          creates: "{{ hadoop_home }}/data/hdfs/namenode/current/VERSION"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      when: inventory_hostname == groups['namenode'][0]
                                            
    - name: Démarrer les services HDFS
      shell: "{{ hadoop_home }}/sbin/start-dfs.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"

- name: Configurer le NameNode standby
  hosts: namenode_standby
  become: yes
  tasks:
    - name: Bootstrap du standby
      shell: "{{ hadoop_home }}/bin/hdfs namenode -bootstrapStandby -force"
      become_user: vagrant
      environment:
        JAVA_HOME: "{{ java_home }}"
      register: bootstrap_result
      failed_when: "bootstrap_result.rc != 0 or 'FATAL' in bootstrap_result.stderr"

- name: demarrer les services hdfs
  hosts: namenode
  become: yes
  tasks:                          
    - name: Démarrer les services HDFS
      shell: "{{ hadoop_home }}/sbin/start-dfs.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      ignore_errors: yes
                                                                                                                                                                                                                                                                                  
- name: Démarrer YARN sur les ResourceManagers
  hosts: resourcemanager
  become: yes
  tasks:
    - name: Démarrer Ressource Manager Active
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh start resourcemanager"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      when: inventory_hostname == groups['resourcemanager'][0]

    - name: "Wait for the active RM to start"
      pause:
          seconds: 10
      when: inventory_hostname == groups['resourcemanager'][0]                                                                                        
                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      ignore_errors: yes                                      
                                                  
    - name: Démarrer explicitement le ResourceManager en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/yarn --daemon start resourcemanager > /tmp/resourcemanager.log 2>&1 &"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash
      ignore_errors: yes                                      

    - name: Pause pour démarrage du ResourceManager
      pause:
          seconds: 20 

- name: Restart  ResourceManagers
  hosts: resourcemanager_standby
  become: yes
  tasks:
    - name: stopper Ressource Manager standby
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh stop resourcemanager"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      when: inventory_hostname == groups['resourcemanager_standby'][0]

    - name: "Wait for the active RM to start"
      pause:
          seconds: 10
      when: inventory_hostname == groups['resourcemanager_standby'][0]   

- name: Re-Démarrer YARN sur les ResourceManagers
  hosts: resourcemanager
  become: yes
  tasks:                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      ignore_errors: yes  
                                                                                        
- name: Vérifier les services Hadoop (jps)
  hosts: all
  become: yes
  tasks:
    - name: Vérifier les processus avec jps
      shell: "jps"
      register: jps_output
      become_user: vagrant
      executable: /bin/bash

    - name: Afficher la sortie de jps
      debug:
          var: jps_output.stdout
        """)
    hadoop_start_playbook_path = os.path.join(cluster_folder, "hadoop_start_services.yml")
    try:
        with open(hadoop_start_playbook_path, "w", encoding="utf-8") as f:
            f.write(hadoop_start_playbook)
    except Exception as e:
        return jsonify({"error": "Error writing HA start playbook", "details": str(e)}), 500

    ###########################################################
    # Définir le préfixe pour ansible-playbook (si nécessaire)
    ###########################################################
    ansible_cmd_prefix = ""
    if platform.system() == "Windows":
        ansible_cmd_prefix = ""

    ##############################################
    # Exécuter le playbook de configuration HA sur tous les nœuds
    ##############################################
    try:
        inventory_file_in_vm = os.path.basename(inventory_path)
        config_cmd = (
            f'vagrant ssh {namenode_lines[0].split()[0]} -c "cd /vagrant && {ansible_cmd_prefix}ansible-playbook -i {inventory_file_in_vm} hadoop_config.yml"'
        )
        subprocess.run(config_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error configuring HA Hadoop", "details": str(e)}), 500

    ##############################################
    # Exécuter le playbook de démarrage HA sur tous les nœuds
    ##############################################
    try:
        start_cmd = (
            f'vagrant ssh {namenode_lines[0].split()[0]} -c "cd /vagrant && {ansible_cmd_prefix}ansible-playbook -i {inventory_file_in_vm} hadoop_start_services.yml"'
        )
        subprocess.run(start_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error starting HA Hadoop services", "details": str(e)}), 500

    return jsonify({
        "message": f"Cluster HA '{cluster_data.get('clusterName')}' created successfully.",
        "cluster_folder": cluster_folder,
        "inventory_file": inventory_path,
        "haComponents": cluster_data.get("haComponents")
    }), 200

###################### SPARK/YARN #################################
@app.route('/create_cluster_ha_spark', methods=['POST'])
def create_cluster_ha_spark():
    # 1. Récupérer les données du front-end
    cluster_data = request.get_json()
    if not cluster_data:
        return jsonify({"error": "No data received"}), 400

    cluster_name = cluster_data.get("clusterName")
    if not cluster_name:
        return jsonify({"error": "Cluster name is required"}), 400

    print(cluster_data)

    # 2. Créer le dossier du cluster
    cluster_folder = get_cluster_folder(cluster_name)

    # 3. Générer et écrire le Vagrantfile
    vagrantfile_content = generate_vagrantfile(cluster_data)
    vagrantfile_path = os.path.join(cluster_folder, "Vagrantfile")
    try:
        with open(vagrantfile_path, "w", encoding="utf-8") as vf:
            vf.write(vagrantfile_content)
    except Exception as e:
        return jsonify({"error": "Error writing Vagrantfile", "details": str(e)}), 500

    # 4. Lancer les VMs via 'vagrant up'
    try:
        subprocess.run(["vagrant", "up"], cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error during 'vagrant up'", "details": str(e)}), 500

    # 5. Générer l'inventaire Ansible HA (similaire à votre code existant)
    node_details = cluster_data.get("nodeDetails", [])
    inventory_lines = []
    namenode_lines = []
    namenode_standby_lines = []
    resourcemanager_lines = []
    resourcemanager_standby_lines = []
    datanodes_lines = []
    nodemanagers_lines = []
    zookeeper_lines = []
    journalnode_lines = []
    spark_lines = []

    for node in node_details:
        hostname = node.get("hostname")
        ip = node.get("ip")
        if node.get("isNameNode", False):
            namenode_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isNameNodeStandby", False):
            namenode_standby_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isResourceManager", False):
            resourcemanager_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isResourceManagerStandby", False):
            resourcemanager_standby_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isDataNode", False):
            datanodes_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isNodeManager", False):
            nodemanagers_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isZookeeper", False):
            zookeeper_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isJournalNode", False):
            journalnode_lines.append(f"{hostname} ansible_host={ip}")
        if node.get("isSparkNode"):
            spark_lines.append(f"{hostname} ansible_host={ip}")

    if namenode_lines:
        inventory_lines.append("[namenode]")
        inventory_lines.extend(namenode_lines)
    if namenode_standby_lines:
        inventory_lines.append("[namenode_standby]")
        inventory_lines.extend(namenode_standby_lines)
    if resourcemanager_lines:
        inventory_lines.append("[resourcemanager]")
        inventory_lines.extend(resourcemanager_lines)
    if resourcemanager_standby_lines:
        inventory_lines.append("[resourcemanager_standby]")
        inventory_lines.extend(resourcemanager_standby_lines)
    if datanodes_lines:
        inventory_lines.append("[datanodes]")
        inventory_lines.extend(datanodes_lines)
    if nodemanagers_lines:
        inventory_lines.append("[nodemanagers]")
        inventory_lines.extend(nodemanagers_lines)
    if zookeeper_lines:
        inventory_lines.append("[zookeeper]")
        inventory_lines.extend(zookeeper_lines)
    if journalnode_lines:
        inventory_lines.append("[journalnode]")
        inventory_lines.extend(journalnode_lines)
    if spark_lines:
        inventory_lines.append("[spark]")
        inventory_lines.extend(spark_lines)

    global_vars = (
        "[all:vars]\n"
        "ansible_user=vagrant\n"
        "ansible_python_interpreter=/usr/bin/python3\n"
        "ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n\n"
        "java_home=/usr/lib/jvm/java-11-openjdk-amd64\n"
        "hadoop_home=/opt/hadoop\n"
    )
    inventory_content = global_vars + "\n".join(inventory_lines)
    inventory_path = os.path.join(cluster_folder, "inventory.ini")
    try:
        with open(inventory_path, "w", encoding="utf-8") as inv_file:
            inv_file.write(inventory_content)
    except Exception as e:
        return jsonify({"error": "Error writing inventory file", "details": str(e)}), 500

# 6. Installation d'Ansible sur les NameNodes
    try:
        namenode_hosts = [line.split()[0] for line in namenode_lines] + [line.split()[0] for line in namenode_standby_lines]

        for namenode in namenode_hosts:
            check_ansible_cmd = f'vagrant ssh {namenode} -c "which ansible-playbook"'
            result_ansible = subprocess.run(check_ansible_cmd, shell=True, cwd=cluster_folder,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            if not result_ansible.stdout.strip():
                install_ansible_cmd = f'vagrant ssh {namenode} -c "sudo apt-get update && sudo apt-get install -y ansible"'
                subprocess.run(install_ansible_cmd, shell=True, cwd=cluster_folder, check=True)
            else:
                print(f"Ansible est déjà installé sur {namenode}.")
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing Ansible on NameNodes", "details": str(e)}), 500

   # --- Configuration SSH pour les NameNodes et autres nœuds ---
    try:
        namenode_public_keys = {}

        for namenode in namenode_hosts:
            # Générer une clé SSH si elle n'existe pas
            gen_key_cmd = f'vagrant ssh {namenode} -c "test -f ~/.ssh/id_rsa.pub || ssh-keygen -t rsa -N \'\' -f ~/.ssh/id_rsa"'
            subprocess.run(gen_key_cmd, shell=True, cwd=cluster_folder, check=True)

            # Récupérer la clé publique
            get_pubkey_cmd = f'vagrant ssh {namenode} -c "cat ~/.ssh/id_rsa.pub"'
            result_pub = subprocess.run(get_pubkey_cmd, shell=True, cwd=cluster_folder,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, check=True)
            namenode_public_keys[namenode] = result_pub.stdout.strip()
            print(f"Public key de {namenode} récupérée :", namenode_public_keys[namenode])

        # Ajouter les clés dans les authorized_keys respectifs
        for namenode in namenode_hosts:
            for other_namenode, public_key in namenode_public_keys.items():
                add_key_cmd = (
                    f'vagrant ssh {namenode} -c "mkdir -p ~/.ssh && '
                    f'grep -q {shlex.quote(public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(public_key)} >> ~/.ssh/authorized_keys && '
                    f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                )
                subprocess.run(add_key_cmd, shell=True, cwd=cluster_folder, check=True)

        # Configuration SSH pour les autres nœuds
        for node in node_details:
            node_hostname = node.get("hostname")
            if node_hostname not in namenode_hosts:
                # Générer une clé SSH si elle n'existe pas
                gen_key_cmd = f'vagrant ssh {node_hostname} -c "test -f ~/.ssh/id_rsa.pub || ssh-keygen -t rsa -N \'\' -f ~/.ssh/id_rsa"'
                subprocess.run(gen_key_cmd, shell=True, cwd=cluster_folder, check=True)

                # Récupérer la clé publique
                get_pubkey_cmd = f'vagrant ssh {node_hostname} -c "cat ~/.ssh/id_rsa.pub"'
                result_pub = subprocess.run(get_pubkey_cmd, shell=True, cwd=cluster_folder,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            universal_newlines=True, check=True)
                node_public_key = result_pub.stdout.strip()
                print(f"Public key du nœud {node_hostname} récupérée :", node_public_key)

                # Ajouter la clé du nœud dans son authorized_keys
                add_self_key_cmd = (
                    f'vagrant ssh {node_hostname} -c "mkdir -p ~/.ssh && '
                    f'grep -q {shlex.quote(node_public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(node_public_key)} >> ~/.ssh/authorized_keys && '
                    f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                )
                subprocess.run(add_self_key_cmd, shell=True, cwd=cluster_folder, check=True)

                # Ajouter la clé des NameNodes dans l'authorized_keys du nœud
                for namenode, public_key in namenode_public_keys.items():
                    add_namenode_key_cmd = (
                        f'vagrant ssh {node_hostname} -c "mkdir -p ~/.ssh && '
                        f'grep -q {shlex.quote(public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(public_key)} >> ~/.ssh/authorized_keys && '
                        f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                    )
                    subprocess.run(add_namenode_key_cmd, shell=True, cwd=cluster_folder, check=True)

                    # Ajouter la clé du nœud dans l'authorized_keys des NameNodes
                    add_node_key_to_namenode_cmd = (
                        f'vagrant ssh {namenode} -c "mkdir -p ~/.ssh && '
                        f'grep -q {shlex.quote(node_public_key)} ~/.ssh/authorized_keys || echo {shlex.quote(node_public_key)} >> ~/.ssh/authorized_keys && '
                        f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"'
                    )
                    subprocess.run(add_node_key_to_namenode_cmd, shell=True, cwd=cluster_folder, check=True)

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error configuring SSH", "details": str(e)}), 500

# 7. Installation de ZooKeeper sur le NameNode (version corrigée pour respecter la structure souhaitée)
    nameNode_hostname = get_nameNode_hostname(cluster_data)

    """
    Installe ZooKeeper sur le NameNode :
      - Télécharge l'archive de ZooKeeper
      - Extrait l'archive dans /etc/zookeeper en supprimant les composants inutiles
      - Copie le fichier de configuration d'exemple (zoo_sample.cfg) en zoo.cfg
      - Crée les dossiers de données (/var/lib/zookeeper) et logs (/var/log/zookeeper)
      - Ajuste les droits et crée une archive compressée pour le transfert
    """
    try:
        prepare_cmd = (
            f'vagrant ssh {nameNode_hostname} -c "'
            'sudo apt-get update && '
            'sudo apt-get install -y wget && '
            'wget -O /tmp/zookeeper.tar.gz https://archive.apache.org/dist/zookeeper/zookeeper-3.6.3/apache-zookeeper-3.6.3-bin.tar.gz && '
            'sudo mkdir -p /etc/zookeeper && '
            'sudo tar -xzf /tmp/zookeeper.tar.gz -C /etc/zookeeper --strip-components=1 && '
            'sudo cp /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg && '
            'sudo mkdir -p /var/lib/zookeeper /var/log/zookeeper && '
            'sudo chown -R vagrant:vagrant /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && '
            'sudo tar -czf /tmp/zookeeper_etc.tar.gz -C /etc zookeeper"'
        )
        subprocess.run(prepare_cmd, shell=True, cwd=cluster_folder, check=True)
        print("Installation sur le NameNode réussie")
    
    except subprocess.CalledProcessError as e:
        print(f"Erreur d'installation ZooKeeper sur NameNode: {str(e)}")
# 6. Installation de Hadoop sur le primary NameNode et synchronisation de l'archive dans /vagrant
    try:
        primary_namenode = get_nameNode_hostname(cluster_data)
        if not primary_namenode:
            return jsonify({"error": "No NameNode found in cluster configuration"}), 400

        check_archive_cmd = f'vagrant ssh {primary_namenode} -c "test -f /vagrant/hadoop.tar.gz"'
        result = subprocess.run(check_archive_cmd, shell=True, cwd=cluster_folder)
        if result.returncode != 0:
            hadoop_install_cmd = (
                f'vagrant ssh {primary_namenode} -c "sudo apt-get update && sudo apt-get install -y wget && '
                f'wget -O /tmp/hadoop.tar.gz https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz && '
                f'test -s /tmp/hadoop.tar.gz && '
                f'sudo tar -xzvf /tmp/hadoop.tar.gz -C /opt && '
                f'sudo mv /opt/hadoop-3.3.1 /opt/hadoop && '
                f'rm /tmp/hadoop.tar.gz"'
            )
            subprocess.run(hadoop_install_cmd, shell=True, cwd=cluster_folder, check=True)
            tar_hadoop_cmd = f'vagrant ssh {primary_namenode} -c "sudo tar -czf /tmp/hadoop.tar.gz -C /opt hadoop"'
            subprocess.run(tar_hadoop_cmd, shell=True, cwd=cluster_folder, check=True)
            copy_to_shared_cmd = f'vagrant ssh {primary_namenode} -c "sudo cp /tmp/hadoop.tar.gz /vagrant/hadoop.tar.gz"'
            subprocess.run(copy_to_shared_cmd, shell=True, cwd=cluster_folder, check=True)
        else:
            print("L'archive Hadoop existe déjà dans /vagrant/hadoop.tar.gz, extraction sur le primary NameNode.")
            extract_cmd = f'vagrant ssh {primary_namenode} -c "sudo rm -rf /opt/hadoop && sudo tar -xzf /vagrant/hadoop.tar.gz -C /opt"'
            subprocess.run(extract_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing Hadoop on primary NameNode", "details": str(e)}), 500

    # 8.1 Synchroniser l'archive Hadoop sur les autres nœuds
    for node in cluster_data.get("nodeDetails", []):
        if node.get("hostname") != primary_namenode:
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
# 7. Transférer l’archive ZooKeeper aux autres nœuds (si besoin)
        """
    Transfère l'archive compressée du NameNode vers les nœuds ZooKeeper :
      - Utilise SCP pour copier l'archive depuis le NameNode vers /tmp sur le nœud cible
      - Sur le nœud cible, supprime l'ancien dossier /etc/zookeeper et extrait l'archive dans /etc
      - Crée les dossiers de données et logs et ajuste les permissions
    """
    for node in cluster_data.get("nodeDetails", []):
        if node.get("isZookeeper", False):
            target_hostname = node.get("hostname")
            print(target_hostname)
            target_ip = node.get("ip")  # Supposons que cluster_data contient les IPs
            
            if target_hostname and target_hostname != nameNode_hostname:
                try:
                    # Utiliser l'IP pour SCP
                    scp_cmd = (
                        f'vagrant ssh {nameNode_hostname} -c "'
                        f'scp -o StrictHostKeyChecking=no '
                        f'/tmp/zookeeper_etc.tar.gz vagrant@{target_ip}:/tmp/"'
                    )
                    subprocess.run(scp_cmd, shell=True, check=True, cwd=cluster_folder)

                    # Extraction sur le nœud cible
                    install_cmd = (
                        f'vagrant ssh {target_hostname} -c "'
                        #'sudo rm -rf /etc/zookeeper && '
                        'sudo tar -xzf /tmp/zookeeper_etc.tar.gz -C /etc && '
                        'sudo mkdir -p /etc/zookeeper/conf && '  # S'assure que conf existe
                        'sudo mkdir -p /var/lib/zookeeper /var/log/zookeeper && '
                        'sudo chown -R vagrant:vagrant /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper"'
                    )
                    subprocess.run(install_cmd, shell=True, cwd=cluster_folder, check=True)
                    
                    print(f"Transfert réussi sur {target_hostname}")
                
                except subprocess.CalledProcessError as e:
                    print(f"Erreur sur {target_hostname}: {str(e)}")

    """
    Configure le fichier /var/lib/zookeeper/myid pour chaque nœud ZooKeeper :
      - Pour chaque nœud identifié comme ZooKeeper, écrit l'ID (zookeeperId) dans le fichier myid
    """
    zk_nodes = [n for n in cluster_data.get("nodeDetails", []) if n.get("isZookeeper")]
    
    # Génération automatique des IDs manquants
    for idx, node in enumerate(zk_nodes, start=1):
        if "zookeeperId" not in node:
            node["zookeeperId"] = idx
            print(f"ATTENTION: ID généré pour {node.get('hostname')}: {idx}")
    for node in cluster_data.get("nodeDetails", []):
        if node.get("isZookeeper", False):
            hostname = node.get("hostname")
            print(hostname)
            server_id = node.get("zookeeperId")
            print(server_id)
            if hostname and server_id:
                try:
                    configure_cmd = (
                        f'vagrant ssh {hostname} -c "'
                        'sudo mkdir -p /var/lib/zookeeper && '
                        f'echo {server_id} | sudo tee /var/lib/zookeeper/myid"'
                    )
                    subprocess.run(configure_cmd, shell=True, cwd=cluster_folder, check=True)
                    print(f"Configuration myid réussie sur {hostname}")
                except subprocess.CalledProcessError as e:
                    print(f"Erreur de configuration myid sur {hostname}: {str(e)}")
# After Hadoop installation steps
# 9. Install Spark on Spark nodes
    try:
        spark_nodes = [node for node in cluster_data.get("nodeDetails", []) if node.get("isSparkNode")]
        if spark_nodes:
            primary_spark_node = spark_nodes[0].get("hostname")
            check_spark_archive_cmd = f'vagrant ssh {primary_spark_node} -c "test -f /vagrant/spark.tar.gz"'
            result = subprocess.run(check_spark_archive_cmd, shell=True, cwd=cluster_folder)
            if result.returncode != 0:
                # Download and install Spark on the primary Spark node
                spark_install_cmd = (
                    f'vagrant ssh {primary_spark_node} -c "sudo apt-get update && sudo apt-get install -y wget && '
                    f'wget -O /tmp/spark.tgz https://archive.apache.org/dist/spark/spark-3.3.1/spark-3.3.1-bin-hadoop3.tgz && '
                    f'sudo tar -xzf /tmp/spark.tgz -C /opt && '
                    f'sudo mv /opt/spark-3.3.1-bin-hadoop3 /opt/spark && '
                    f'sudo chown -R vagrant:vagrant /opt/spark && '
                    f'rm /tmp/spark.tgz && '
                    f'sudo tar -czf /tmp/spark.tar.gz -C /opt spark"'
                )
                subprocess.run(spark_install_cmd, shell=True, cwd=cluster_folder, check=True)
                copy_to_shared_cmd = f'vagrant ssh {primary_spark_node} -c "sudo cp /tmp/spark.tar.gz /vagrant/spark.tar.gz"'
                subprocess.run(copy_to_shared_cmd, shell=True, cwd=cluster_folder, check=True)
            else:
                # Extract existing Spark archive on primary Spark node
                extract_cmd = f'vagrant ssh {primary_spark_node} -c "sudo rm -rf /opt/spark && sudo tar -xzf /vagrant/spark.tar.gz -C /opt"'
                subprocess.run(extract_cmd, shell=True, cwd=cluster_folder, check=True)

            # Distribute Spark to other Spark nodes
            for node in spark_nodes[1:]:
                target_hostname = node.get("hostname")
                copy_spark_cmd = (
                    f'vagrant ssh {target_hostname} -c "sudo apt-get update && sudo apt-get install -y openssh-client && '
                    f'sudo rm -rf /opt/spark && '
                    f'sudo tar -xzf /vagrant/spark.tar.gz -C /opt && '
                    f'sudo chown -R vagrant:vagrant /opt/spark"'
                )
                subprocess.run(copy_spark_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing Spark", "details": str(e)}), 500


# 8. Installer Java, net-tools, python3 et configurer l'environnement sur tous les nœuds
    for node in cluster_data.get("nodeDetails", []):
        target_hostname = node.get("hostname")
        try:
            install_java_net_cmd = (
                f'vagrant ssh {target_hostname} -c "sudo apt-get update && sudo apt-get install -y default-jdk net-tools python3"'
            )
            subprocess.run(install_java_net_cmd, shell=True, cwd=cluster_folder, check=True)

            # Configuration des variables d'environnement pour Hadoop
            configure_env_cmd1 = (
                f'vagrant ssh {target_hostname} -c "echo \'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64\' >> ~/.bashrc && '
                f'echo \'export HADOOP_HOME=/opt/hadoop\' >> ~/.bashrc && '
                f'echo \'export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin\' >> ~/.bashrc"'
            )
            subprocess.run(configure_env_cmd1, shell=True, cwd=cluster_folder, check=True)

            # Configuration des variables d'environnement pour ZooKeeper
            configure_env_cmd2 = (
                f'vagrant ssh {target_hostname} -c "echo \'export ZOOKEEPER_HOME=/etc/zookeeper\' >> ~/.bashrc && '
                f'echo \'export PATH=$PATH:$ZOOKEEPER_HOME/bin\' >> ~/.bashrc && '
                f'echo \'export ZOO_LOG_DIR=/var/log/zookeeper\' >> ~/.bashrc"'
            )
            subprocess.run(configure_env_cmd2, shell=True, cwd=cluster_folder, check=True)

        # Configuration Spark UNIQUEMENT si c'est un nœud Spark
            if node.get("isSparkNode"):
                configure_spark_env_cmd = (
                    f'vagrant ssh {target_hostname} -c "'
                    'echo \'export SPARK_HOME=/opt/spark\' >> ~/.bashrc && '
                    'echo \'export PATH=$PATH:$SPARK_HOME/bin:$SPARK_HOME/sbin\' >> ~/.bashrc"'
                )
                subprocess.run(configure_spark_env_cmd, shell=True, cwd=cluster_folder, check=True)
                
            # Optionnel : recharger l'environnement (bien que dans un shell non-interactif, ce soit parfois inutile)
            refresh_env_cmd = f'vagrant ssh {target_hostname} -c "source ~/.bashrc"'
            subprocess.run(refresh_env_cmd, shell=True, cwd=cluster_folder, check=True)

            print(f"Configuration d'environnement terminée sur {target_hostname}")
        except subprocess.CalledProcessError as e:
            return jsonify({"error": f"Error configuring environment on node {target_hostname}", "details": str(e)}), 500


# 10. (Optionnel) Génération des templates de configuration pour Hadoop/YARN/ZooKeeper/Spark
    templates_dir = os.path.join(cluster_folder, "templates")
    os.makedirs(templates_dir, exist_ok=True)
    # Les templates core-site.xml, hdfs-site.xml, yarn-site.xml, mapred-site.xml, etc. sont générés ici...
    # (Code de génération des templates similaire à votre endpoint HA existant)
    # ---- Template core-site.xml.j2 ----
    core_site_template = textwrap.dedent("""\
        <configuration>
        <!-- Point d'entrée HDFS (doit correspondre au nameservice défini dans hdfs-site.xml) -->
        <property>
            <name>fs.defaultFS</name>
            <value>hdfs://ha-cluster</value>
        </property>
        <!-- Proxy de failover pour le client HDFS -->
        <property>
            <name>dfs.client.failover.proxy.provider.ha-cluster</name>
            <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>
        </property>
        <!-- Quorum ZooKeeper pour le failover -->
        <property>
            <name>ha.zookeeper.quorum</name>
            <value>{% for zk in groups['zookeeper'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>
        </property>
        <!-- Autres paramètres utiles -->
        <property>
            <name>dfs.permissions.enabled</name>
            <value>true</value>
        </property>
        <property>
            <name>ipc.client.connect.max.retries</name>
            <value>3</value>
        </property>
        </configuration>
        """)
    with open(os.path.join(templates_dir, "core-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(core_site_template)

    # ---- Template hdfs-site.xml.j2 ----
    # On utilise ici les noms de machines tels qu'ils apparaissent dans l'inventaire (ex: ayoub12, ayoub16)
    hdfs_site_template = textwrap.dedent("""\
        <configuration>
        <!-- Réplication -->
        <property>
            <name>dfs.replication</name>
            <value>2</value>
        </property>
        <!-- Activation du mode HA -->
        <property>
            <name>dfs.nameservices</name>
            <value>ha-cluster</value>
        </property>
        <!-- Définir les deux NameNodes (utiliser les noms de machines de l'inventaire) -->
        <property>
            <name>dfs.ha.namenodes.ha-cluster</name>
            <value>{{ groups['namenode'][0] }},{{ groups['namenode_standby'][0] }}</value>
        </property>
        <!-- Adresses RPC et HTTP en se basant sur les noms de machines -->
        <property>
            <name>dfs.namenode.rpc-address.ha-cluster.{{ groups['namenode'][0] }}</name>
            <value>{{ hostvars[groups['namenode'][0]].ansible_host }}:8020</value>
        </property>
        <property>
            <name>dfs.namenode.rpc-address.ha-cluster.{{ groups['namenode_standby'][0] }}</name>
            <value>{{ hostvars[groups['namenode_standby'][0]].ansible_host }}:8020</value>
        </property>
        <property>
            <name>dfs.namenode.http-address.ha-cluster.{{ groups['namenode'][0] }}</name>
            <value>{{ hostvars[groups['namenode'][0]].ansible_host }}:50070</value>
        </property>
        <property>
            <name>dfs.namenode.http-address.ha-cluster.{{ groups['namenode_standby'][0] }}</name>
            <value>{{ hostvars[groups['namenode_standby'][0]].ansible_host }}:50070</value>
        </property>
        <!-- Répertoire partagé pour les shared edits -->
        <property>
            <name>dfs.namenode.shared.edits.dir</name>
            <value>qjournal://{% for jn in groups['journalnode'] %}{{ hostvars[jn].ansible_host }}:8485{% if not loop.last %};{% endif %}{% endfor %}/ha-cluster</value>
        </property>
        <!-- Bascule automatique -->
        <property>
            <name>dfs.ha.automatic-failover.enabled</name>
            <value>true</value>
        </property>
        <!-- Proxy failover (idem core-site) -->
        <property>
            <name>dfs.client.failover.proxy.provider.ha-cluster</name>
            <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>
        </property>
        <!-- Quorum ZooKeeper -->
        <property>
            <name>ha.zookeeper.quorum</name>
            <value>{% for zk in groups['zookeeper'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>
        </property>
        <!-- Répertoires locaux -->
        <property>
            <name>dfs.namenode.name.dir</name>
            <value>file:{{ hadoop_home }}/data/hdfs/namenode</value>
        </property>
        <property>
            <name>dfs.datanode.data.dir</name>
            <value>file:{{ hadoop_home }}/data/hdfs/datanode</value>
        </property>
        <property>
            <name>dfs.namenode.checkpoint.dir</name>
            <value>file:{{ hadoop_home }}/data/hdfs/namesecondary</value>
        </property>
        <!-- Fencing et timeout -->
        <property>
            <name>dfs.ha.fencing.methods</name>
            <value>shell(/bin/true)</value>
        </property>
        <property>
            <name>dfs.ha.failover-controller.active-standby-elector.zk.op.retries</name>
            <value>3</value>
        </property>
        </configuration>
        """)
    with open(os.path.join(templates_dir, "hdfs-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(hdfs_site_template)

    # ---- Template yarn-site.xml.j2 ----
    yarn_site_template = textwrap.dedent("""\
    <configuration>
        <!-- Paramètres HA de base -->
        <property>
            <name>yarn.resourcemanager.ha.enabled</name>
            <value>true</value>
        </property>
        <property>
            <name>yarn.resourcemanager.cluster-id</name>
            <value>yarn-cluster</value>
        </property>
        <property>
            <name>yarn.resourcemanager.ha.rm-ids</name>
            <value>rm1,rm2</value>
        </property>

        <!-- Configuration Zookeeper -->
        <property>
            <name>yarn.resourcemanager.zk-address</name>
            <value>{% for host in groups['zookeeper'] %}{{ host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>
        </property>

        <!-- Adresses des nœuds -->
        <property>
            <name>yarn.resourcemanager.hostname.rm1</name>
            <value>{{ groups['resourcemanager'][0] }}</value>
        </property>
        <property>
            <name>yarn.resourcemanager.hostname.rm2</name>
            <value>{{ groups['resourcemanager_standby'][0] }}</value>
        </property>

        <!-- Configuration du recovery -->
        <property>
            <name>yarn.resourcemanager.recovery.enabled</name>
            <value>true</value>
        </property>
        <property>
            <name>yarn.resourcemanager.store.class</name>
            <value>org.apache.hadoop.yarn.server.resourcemanager.recovery.ZKRMStateStore</value>
        </property>

        <!-- Configuration des ports -->
        <property>
            <name>yarn.resourcemanager.webapp.address.rm1</name>
            <value>{{ groups['resourcemanager'][0] }}:8088</value>
        </property>
        <property>
            <name>yarn.resourcemanager.webapp.address.rm2</name>
            <value>{{ groups['resourcemanager_standby'][0] }}:8088</value>
        </property>

        <!-- Configuration NodeManager -->
        <property>
            <name>yarn.nodemanager.resource.memory-mb</name>
            <value>4096</value>
        </property>
        <property>
            <name>yarn.nodemanager.resource.cpu-vcores</name>
            <value>4</value>
        </property>
    </configuration>
    """)
    with open(os.path.join(templates_dir, "yarn-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(yarn_site_template)

    # ---- Template mapred-site.xml.j2 ----
    mapred_site_template = textwrap.dedent("""\
        <configuration>
        <property>
            <name>mapreduce.framework.name</name>
            <value>yarn</value>
        </property>
        </configuration>
        """)
    with open(os.path.join(templates_dir, "mapred-site.xml.j2"), "w", encoding="utf-8") as f:
        f.write(mapred_site_template)

    # ---- Template masters.j2 ----
    masters_template = textwrap.dedent("""\
        {{ groups['namenode'][0] }}
        """)
    with open(os.path.join(templates_dir, "masters.j2"), "w", encoding="utf-8") as f:
        f.write(masters_template)

    # ---- Template workers.j2 ----
    workers_template = textwrap.dedent("""\
        {% for worker in groups['datanodes'] %}
        {{ worker }}
        {% endfor %}
        """)
    with open(os.path.join(templates_dir, "workers.j2"), "w", encoding="utf-8") as f:
        f.write(workers_template)

    # ---- Template zoo.cfg.j2 ----
    # Déployé dans le répertoire standard de ZooKeeper (/etc/zookeeper/conf)
    zoo_cfg_template = textwrap.dedent("""\
        tickTime=2000
        initLimit=10
        syncLimit=5
        dataDir=/var/lib/zookeeper
        clientPort=2181
        {% for zk in groups['zookeeper'] %}
        server.{{ loop.index }}={{ hostvars[zk].ansible_host }}:2888:3888
        {% endfor %}
        """)
    with open(os.path.join(templates_dir, "zoo.cfg.j2"), "w", encoding="utf-8") as f:
        f.write(zoo_cfg_template)

    # ---- Template hosts.j2 ----
    hosts_template = textwrap.dedent("""\
        # ANSIBLE GENERATED HOSTS FILE
        {% for host in groups['all'] %}
        {{ hostvars[host].ansible_host }} {{ host }}
        {% endfor %}
        """)
    with open(os.path.join(templates_dir, "hosts.j2"), "w", encoding="utf-8") as f:
        f.write(hosts_template)

    # ---- Template spark-defaults.conf.j2 ----
    spark_defaults_template = textwrap.dedent("""\
        spark.master                     yarn
        spark.eventLog.enabled           true
        spark.eventLog.dir               hdfs://ha-cluster/spark-logs
        spark.history.fs.logDirectory    hdfs://ha-cluster/spark-logs
        spark.serializer                 org.apache.spark.serializer.KryoSerializer
        spark.hadoop.yarn.resourcemanager.ha.enabled   true
        spark.hadoop.yarn.resourcemanager.ha.rm-ids    rm1,rm2
        spark.hadoop.yarn.resourcemanager.hostname.rm1 {{ groups['resourcemanager'][0] }}
        spark.hadoop.yarn.resourcemanager.hostname.rm2 {{ groups['resourcemanager_standby'][0] }}
        spark.driver.memory              1g
        spark.executor.memory            2g
        spark.hadoop.yarn.resourcemanager.address {{ groups['resourcemanager'][0] }}:8032
        spark.hadoop.yarn.resourcemanager.scheduler.address {{ groups['resourcemanager'][0] }}:8030
        """)
    with open(os.path.join(templates_dir, "spark-defaults.conf.j2"), "w", encoding="utf-8") as f:
        f.write(spark_defaults_template)

    # ---- Template spark-env.sh.j2 ----
    spark_env_template = textwrap.dedent("""\
        export HADOOP_CONF_DIR={{ hadoop_home }}/etc/hadoop
        export SPARK_HOME=/opt/spark
        export SPARK_DIST_CLASSPATH=$({{ hadoop_home }}/bin/hadoop classpath)
        export JAVA_HOME={{ java_home }}
        """)
    with open(os.path.join(templates_dir, "spark-env.sh.j2"), "w", encoding="utf-8") as f:
        f.write(spark_env_template)


    # 11. (Optionnel) Génération du playbook Ansible HA pour déployer la configuration sur le cluster

    ######################################################################
    # Création du playbook de configuration HA Hadoop (hadoop_config.yml)
    ######################################################################
    hadoop_config_playbook = textwrap.dedent("""\
---
- name: Configurer HA Hadoop et mettre à jour /etc/hosts
  hosts: all
  become: yes
  vars:
    namenode_hostname: "{{ groups['namenode'][0] }}"
  tasks:
    - name: Déployer core-site.xml
      template:
        src: templates/core-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/core-site.xml"

    - name: Déployer hdfs-site.xml
      template:
        src: templates/hdfs-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/hdfs-site.xml"

    - name: Déployer yarn-site.xml
      template:
        src: templates/yarn-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/yarn-site.xml"

    - name: Déployer mapred-site.xml
      template:
        src: templates/mapred-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/mapred-site.xml"

    - name: Déployer masters
      template:
        src: templates/masters.j2
        dest: "{{ hadoop_home }}/etc/hadoop/masters"

    - name: Déployer workers
      template:
        src: templates/workers.j2
        dest: "{{ hadoop_home }}/etc/hadoop/workers"

    - name: Déployer zoo.cfg pour ZooKeeper
      template:
        src: templates/zoo.cfg.j2
        dest: "/etc/zookeeper/conf/zoo.cfg"

    - name: Mettre à jour /etc/hosts avec les hôtes du cluster
      template:
        src: templates/hosts.j2
        dest: /etc/hosts

- name: Configurer les nœuds Spark  # <-- Début d'une NOUVELLE play
  hosts: spark                      # Aligné avec '- name'
  become: yes                       # Aligné avec 'hosts'
  tasks:
    - name: Créer le répertoire de configuration Spark
      file:                         # Aligné sous 'tasks'
        path: /opt/spark/conf
        state: directory
        owner: vagrant
        group: vagrant
        mode: 0755

    - name: Déployer spark-defaults.conf
      template:                     # Aligné sous 'tasks'
        src: templates/spark-defaults.conf.j2
        dest: /opt/spark/conf/spark-defaults.conf

    - name: Déployer spark-env.sh
      template:                    # Aligné sous 'tasks'
        src: templates/spark-env.sh.j2
        dest: /opt/spark/conf/spark-env.sh
        """)
    hadoop_config_playbook_path = os.path.join(cluster_folder, "hadoop_config.yml")
    try:
        with open(hadoop_config_playbook_path, "w", encoding="utf-8") as f:
            f.write(hadoop_config_playbook)
    except Exception as e:
        return jsonify({"error": "Error writing HA config playbook", "details": str(e)}), 500

    ############################################################################
    # Création du playbook de démarrage HA Hadoop (hadoop_start_services.yml)
    #############################################################################
    # Ordre important : démarrer ZooKeeper et JournalNodes avant le formatage du NameNode, 
    # puis initialiser HA dans ZooKeeper, formater le NameNode, et enfin démarrer HDFS/YARN.
    hadoop_start_playbook = textwrap.dedent("""\
---
- name: Démarrer ZooKeeper sur les nœuds ZooKeeper
  hosts: zookeeper
  become: yes
  tasks:
                                            
    - name: Démarrer ZooKeeper
      shell: "/etc/zookeeper/bin/zkServer.sh start"
      become_user: vagrant
      environment:
          ZOO_LOG_DIR: "/var/log/zookeeper"
          ZOO_CONF_DIR: "/etc/zookeeper/conf"
      executable: /bin/bash
      ignore_errors: yes                                      
                                            
    - name: Créer les répertoires de logs
      file:
        path: /opt/hadoop/logs
        state: directory
        owner: vagrant
        group: vagrant
        mode: 0755
                                            
    - name: Configurer hadoop-env.sh
      lineinfile:
        path: /opt/hadoop/etc/hadoop/hadoop-env.sh
        line: "export JAVA_HOME={{ java_home }}"
        state: present  

- name: Créer le dossier Spark dans HDFS
  hosts: namenode
  become: yes
  tasks:
    - name: Créer le dossier Spark logs
      file:
        path: /spark-logs
        state: directory
        owner: vagrant
        group: vagrant
        mode: 0755
      when: inventory_hostname == groups['namenode'][0]
                                                                                        
- name: Configuration des JournalNodes
  hosts: zookeeper
  become: yes
  tasks:
    - name: Créer le répertoire JournalNode
      file:
        path: /opt/hadoop/data/hdfs/journalnode
        state: directory
        owner: vagrant
        group: vagrant
        mode: '0755'

    - name: Démarrer JournalNode en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/hdfs --daemon start journalnode > /tmp/journalnode.log 2>&1 &"
      become_user: vagrant
      environment:
        JAVA_HOME: "{{ java_home }}"
        HADOOP_LOG_DIR: "/opt/hadoop/logs"

    - name: Vérifier que le JournalNode est actif
      wait_for:
        port: 8485
        timeout: 60

- name: Initialiser le HA dans ZooKeeper (uniquement sur le NameNode actif)
  hosts: namenode
  become: yes
  tasks:
    - name: Initialiser HA dans ZooKeeper
      shell: "{{ hadoop_home }}/bin/hdfs zkfc -formatZK -force -nonInteractive"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash
      when: inventory_hostname == groups['namenode'][0]
                                                          
- name: Formater le NameNode (si nécessaire)
  hosts: namenode
  become: yes
  tasks:
    - name: Créer le répertoire namenode
      file:
        path: "{{ hadoop_home }}/data/hdfs/namenode"
        state: directory
        owner: vagrant
        group: vagrant
        mode: '0755'
                                                                                                                               
    - name: Formater le NameNode (si nécessaire)
      shell: "{{ hadoop_home }}/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"
      args:
          creates: "{{ hadoop_home }}/data/hdfs/namenode/current/VERSION"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      when: inventory_hostname == groups['namenode'][0]
                                            
    - name: Démarrer les services HDFS
      shell: "{{ hadoop_home }}/sbin/start-dfs.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"

- name: Configurer le NameNode standby
  hosts: namenode_standby
  become: yes
  tasks:
    - name: Bootstrap du standby
      shell: "{{ hadoop_home }}/bin/hdfs namenode -bootstrapStandby -force"
      become_user: vagrant
      environment:
        JAVA_HOME: "{{ java_home }}"
      register: bootstrap_result
      failed_when: "bootstrap_result.rc != 0 or 'FATAL' in bootstrap_result.stderr"

- name: demarrer les services hdfs
  hosts: namenode
  become: yes
  tasks:                          
    - name: Démarrer les services HDFS
      shell: "{{ hadoop_home }}/sbin/start-dfs.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      ignore_errors: yes
                                                                                                                                                                                                                                                                                  
- name: Démarrer YARN sur les ResourceManagers
  hosts: resourcemanager
  become: yes
  tasks:
    - name: Démarrer Ressource Manager Active
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh start resourcemanager"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      when: inventory_hostname == groups['resourcemanager'][0]

    - name: "Wait for the active RM to start"
      pause:
          seconds: 10
      when: inventory_hostname == groups['resourcemanager'][0]                                                                                        
                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      ignore_errors: yes                                      
                                                  
    - name: Démarrer explicitement le ResourceManager en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/yarn --daemon start resourcemanager > /tmp/resourcemanager.log 2>&1 &"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash
      ignore_errors: yes                                      

    - name: Pause pour démarrage du ResourceManager
      pause:
          seconds: 20 

- name: Restart  ResourceManagers
  hosts: resourcemanager_standby
  become: yes
  tasks:
    - name: stopper Ressource Manager standby
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh stop resourcemanager"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      when: inventory_hostname == groups['resourcemanager_standby'][0]

    - name: "Wait for the active RM to start"
      pause:
          seconds: 10
      when: inventory_hostname == groups['resourcemanager_standby'][0]   

- name: Re-Démarrer YARN sur les ResourceManagers
  hosts: resourcemanager
  become: yes
  tasks:                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: vagrant
      environment:
          JAVA_HOME: "{{ java_home }}"
      executable: /bin/bash"
      ignore_errors: yes  
                                                                                        
- name: Vérifier les services Hadoop (jps)
  hosts: all
  become: yes
  tasks:
    - name: Vérifier les processus avec jps
      shell: "jps"
      register: jps_output
      become_user: vagrant
      executable: /bin/bash

    - name: Afficher la sortie de jps
      debug:
          var: jps_output.stdout
        """)
    hadoop_start_playbook_path = os.path.join(cluster_folder, "hadoop_start_services.yml")
    try:
        with open(hadoop_start_playbook_path, "w", encoding="utf-8") as f:
            f.write(hadoop_start_playbook)
    except Exception as e:
        return jsonify({"error": "Error writing HA start playbook", "details": str(e)}), 500

    ###########################################################
    # Définir le préfixe pour ansible-playbook (si nécessaire)
    ###########################################################
    ansible_cmd_prefix = ""
    if platform.system() == "Windows":
        ansible_cmd_prefix = ""

    ##############################################
    # Exécuter le playbook de configuration HA sur tous les nœuds
    ##############################################
    try:
        inventory_file_in_vm = os.path.basename(inventory_path)
        config_cmd = (
            f'vagrant ssh {namenode_lines[0].split()[0]} -c "cd /vagrant && {ansible_cmd_prefix}ansible-playbook -i {inventory_file_in_vm} hadoop_config.yml"'
        )
        subprocess.run(config_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error configuring HA Hadoop", "details": str(e)}), 500

    ##############################################
    # Exécuter le playbook de démarrage HA sur tous les nœuds
    ##############################################
    try:
        start_cmd = (
            f'vagrant ssh {namenode_lines[0].split()[0]} -c "cd /vagrant && {ansible_cmd_prefix}ansible-playbook -i {inventory_file_in_vm} hadoop_start_services.yml"'
        )
        subprocess.run(start_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error starting HA Hadoop services", "details": str(e)}), 500

    # Retourne une réponse de succès
    return jsonify({
        "message": f"Cluster HA with Spark '{cluster_data.get('clusterName')}' created successfully.",
        "cluster_folder": cluster_folder,
        "inventory_file": inventory_path,
    }), 200

##############################DISTANT MODE#####################################################
###########################CLASSIC CLUSTER HADOOP##############################################
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
@app.route("/create-cluster-remote", methods=["POST"])
def create_cluster_remote():
    """
    Cet endpoint recrée l'intégralité de la logique de création d'un cluster Hadoop (comme dans /create_cluster)
    sur une machine distante. Les étapes réalisées sont :
      1. Récupération des données envoyées par le front-end.
      2. Connexion SSH à la machine distante (avec tentative de fallback via PowerShell en cas d'échec).
      3. Création du dossier du cluster sur la machine distante (dans "clusters/<clusterName>").
      4. Écriture du Vagrantfile dans ce dossier, généré dynamiquement à partir des informations de chaque nœud.
      5. Lancement de "vagrant up" dans ce dossier distant.
      6. Génération de l’inventaire Ansible et écriture d’un fichier inventory.ini dans le dossier distant.
      7. Installation d’Ansible sur le NameNode et configuration SSH entre les nœuds via commandes exécutées sur la machine distante.
      8. Installation de Hadoop sur le NameNode, création et diffusion de l’archive Hadoop, et extraction sur les autres nœuds.
      9. Installation de Java/net-tools et configuration des variables d’environnement sur chaque nœud.
      10. Création des playbooks Ansible et des templates Jinja2 pour configurer Hadoop.
      11. Exécution des playbooks via vagrant ssh sur le NameNode.
      12. Copie (au moins) du Vagrantfile depuis le dossier distant vers la machine source.
      13. Retour d’un JSON contenant les informations utiles.
    """
    try:
        # 1. Récupération des données
        cluster_data = request.get_json()
        if not cluster_data:
            return jsonify({"error": "No data received"}), 400
        cluster_name = cluster_data.get("clusterName")
        if not cluster_name:
            return jsonify({"error": "Cluster name is required"}), 400
        node_details = cluster_data.get("nodeDetails", [])
        if not node_details:
            return jsonify({"error": "nodeDetails is required"}), 400

        # Paramètres de connexion distante
        remote_ip = cluster_data.get("remote_ip")
        remote_user = cluster_data.get("remote_user")
        remote_password = cluster_data.get("remote_password")
        remote_os = cluster_data.get("remote_os", "windows").lower()  # Par défaut Windows, modifiez si nécessaire
        recipient_email = cluster_data.get("mail")  # Pour notification éventuelle

        # 2. Connexion SSH avec fallback via PowerShell
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            print(remote_ip,remote_user,remote_password)
            client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)
        except Exception as ssh_err:
            print("Échec de la connexion SSH :", ssh_err)
            print("Tentative de configuration SSH via PowerShell...")
            client.connect(remote_ip, username=remote_user, password=remote_password)
            client.exec_command('powershell -Command "Restart-Service sshd"')
            client.close()
            # Reconnexion
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(remote_ip, username=remote_user, password=remote_password, timeout=10)
        print("Connexion SSH établie avec la machine distante.")
        sftp = client.open_sftp()
        # 3. Création du dossier du cluster sur la machine distante
        if remote_os == "windows":
            home_dir = sftp.getcwd() or "."
        else:
            home_dir = f"/home/{remote_user}"
            try:
                sftp.chdir(home_dir)
            except IOError:
                sftp.mkdir(home_dir)
                sftp.chdir(home_dir)
        try:
            sftp.chdir("clusters")
        except IOError:
            sftp.mkdir("clusters")
            sftp.chdir("clusters")
        try:
            sftp.chdir(cluster_name)
        except IOError:
            sftp.mkdir(cluster_name)
            sftp.chdir(cluster_name)
        remote_cluster_folder = sftp.getcwd()
        print("DEBUG - Dossier du cluster sur machine distante :", remote_cluster_folder)

        # 4. Génération du Vagrantfile
        vagrantfile_content = 'Vagrant.configure("2") do |config|\n'
        
        for node in node_details:
            hostname = node.get("hostname")
            os_version = node.get("osVersion", "ubuntu/bionic64")
            ram = node.get("ram", 4)  # en GB
            cpu = node.get("cpu", 2)
            ip = node.get("ip")
            ram_mb = int(ram * 1024)
            print(os_version)
            vagrantfile_content += f'''  config.vm.define "{hostname}" do |machine|
    machine.vm.box = "{os_version}"
    machine.vm.hostname = "{hostname}"
    machine.vm.network "private_network", ip: "{ip}"
    machine.vm.provider "virtualbox" do |vb|
      vb.name = "{hostname}"
      vb.memory = "{ram_mb}"
      vb.cpus = {cpu} 
    end

    machine.vm.provision "shell", inline: <<-SHELL
      echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
    SHELL
  end
'''
        vagrantfile_content += "end\n"
        remote_vagrantfile_path = remote_cluster_folder + "/Vagrantfile"
        with sftp.open(remote_vagrantfile_path, "w") as f:
            f.write(vagrantfile_content)
        print("DEBUG - Vagrantfile écrit sur la machine distante.")
        # 5. Lancement des VMs via "vagrant up"
        if remote_os == "windows":
            folder = remote_cluster_folder.lstrip("/")
            cmd_vagrant = f'cd /d "{folder}" && vagrant up'
        else:
            cmd_vagrant = f'cd "{remote_cluster_folder}" && vagrant up'
        stdin, stdout, stderr = client.exec_command(cmd_vagrant)
        out_vagrant = stdout.read().decode("utf-8", errors="replace")
        err_vagrant = stderr.read().decode("utf-8", errors="replace")
        if err_vagrant.strip():
            sftp.close()
            client.close()
            return jsonify({"error": "Error during 'vagrant up'", "details": err_vagrant}), 500
        print("DEBUG - vagrant up exécuté :", out_vagrant)
        # 6. Génération de l'inventaire Ansible
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
        global_vars = ("[all:vars]\n"
                       "ansible_user=vagrant\n"
                       "ansible_python_interpreter=/usr/bin/python3\n"
                       "ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n\n")
        inventory_content = global_vars + "\n".join(inventory_lines)
        remote_inventory_path = remote_cluster_folder + "/inventory.ini"
        with sftp.open(remote_inventory_path, "w") as f:
            f.write(inventory_content)
        print(inventory_content)    
        sftp.chmod(remote_inventory_path, 0o644)  
        print("DEBUG - Inventaire Ansible écrit sur la machine distante.")

# 7. Vérification/Installation d'Ansible sur le NameNode
# Trouver le NameNode
        namenode = None
        for node in node_details:
            if node.get("isNameNode"):
                namenode = node
                break
        if not namenode:
            return jsonify({"error": "No NameNode defined"}), 400

        namenode_hostname = namenode.get("hostname")
        namenode_ip = namenode.get("ip")
        print("DEBUG - IP du NameNode :", namenode_ip)
# Connexion SSH vers le NameNode en utilisant le mot de passe (remote_password)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(namenode_ip, username='vagrant', password="vagrant")
        except Exception as e:
            return jsonify({"error": "Échec de la connexion SSH sur le NameNode", "details": str(e)}), 500
        print("conx etablie")
        # Vérification de l'installation d'Ansible sur le NameNode
        stdin, stdout, stderr = ssh.exec_command("which ansible || echo 'not-installed'")
        result = stdout.read().decode()
        if 'not-installed' in result:
            install_cmd = (
                "sudo apt-get update && "
                "sudo apt install -y software-properties-common && "
                "sudo apt install -y ansible"
            )
            stdin, stdout, stderr = ssh.exec_command(install_cmd, timeout=200)
            exit_status = stderr.channel.recv_exit_status()
            print(stdout, stderr)
            print("ansible installe")
            if exit_status != 0:
                error_details = {
                        "stdout": stdout.read().decode().strip(),
                        "stderr": stderr.read().decode().strip(),
                        "exit_code": exit_status
                }
                ssh.close()
                logging.error(f"Échec Ansible - Détails : {error_details}")
                return jsonify({"error": "Échec installation Ansible", "details": error_details}), 500
            else:
                print("DEBUG - Ansible installé avec succès sur le NameNode.")
        else:
            print("DEBUG - Ansible est déjà installé sur le NameNode.")

        ssh.close()

        # b) Configuration SSH pour le NameNode : génération et récupération de la clé
        try:
            # 1. Connexion SSH au NameNode
            app.logger.info("Tentative de connexion SSH à %s (%s)", namenode_hostname, namenode_ip)
            nn_ssh = paramiko.SSHClient()
            nn_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            try:
                nn_ssh.connect(namenode_ip, username='vagrant', password="vagrant")
                app.logger.debug("Connexion SSH établie - Version transport : %s", 
                                nn_ssh.get_transport().get_security_options().kex)
            except paramiko.SSHException as ssh_ex:
                app.logger.error("Échec connexion SSH - Détails : %s", str(ssh_ex), exc_info=True)
                raise

            # 2. Génération clé SSH
            app.logger.info("Génération des clés SSH sur %s", namenode_hostname)
            gen_key_cmd = 'mkdir -p ~/.ssh && ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa -q'
            stdin, stdout, stderr = nn_ssh.exec_command(gen_key_cmd, timeout=30)
            
            exit_status = stdout.channel.recv_exit_status()
            # Correction décodage
            gen_key_output = stdout.read().decode('utf-8', errors='replace').strip()
            gen_key_errors = stderr.read().decode('utf-8', errors='replace')
            
            app.logger.debug("Sortie génération clé - Code:%d | Sortie:%s | Erreurs:%s", 
                            exit_status, gen_key_output, gen_key_errors)
            
            if exit_status != 0:
                app.logger.error("Échec génération clé SSH - Code sortie:%d | Erreurs:%s", 
                                exit_status, gen_key_errors)
                raise Exception("Échec lors de la génération des clés SSH")

            # 4. Récupération clé publique
            app.logger.info("Récupération clé publique sur %s", namenode_hostname)
            get_key_cmd = 'cat ~/.ssh/id_rsa.pub 2>&1'
            stdin, stdout, stderr = nn_ssh.exec_command(get_key_cmd, timeout=15)
            
            # Correction décodage
            namenode_public_key = stdout.read().decode('utf-8', errors='replace').strip()
            key_retrieval_errors = stderr.read().decode('utf-8', errors='replace')
            
            app.logger.debug("Clé brute récupérée : %s", namenode_public_key[:80] + "...")
            
            if not namenode_public_key.startswith("ssh-rsa"):
                app.logger.error("Format clé invalide - Début clé:%s | Erreurs:%s", 
                                namenode_public_key[:50], key_retrieval_errors)
                raise ValueError("Clé publique corrompue ou vide")
            
            app.logger.info("Clé publique validée avec succès (empreinte : %s)", 
                        hashlib.sha256(namenode_public_key.encode()).hexdigest()[:12])

        except Exception as e:
            app.logger.exception("ERREUR CRITIQUE dans configuration SSH - Type: %s | Détails: %s", 
                                type(e).__name__, str(e))
            return jsonify({
                "error": f"Échec configuration SSH sur NameNode: {str(e)}",
                "technical_details": {
                    "timestamp": datetime.utcnow().isoformat(),  # Nécessite 'from datetime import datetime'
                    "component": "ssh_keygen",
                    "error_type": type(e).__name__
                }
            }), 500

        finally:
            if 'nn_ssh' in locals():
                nn_ssh.close()
                app.logger.debug("Connexion SSH fermée proprement")
        # C-Configuration SSH pour les autres nœuds
        
            nn_ssh.connect(namenode_ip, username='vagrant', password="vagrant")
            app.logger.debug("Connexion SSH établie 2 avec namenode - Version transport : %s", 
                            nn_ssh.get_transport().get_security_options().kex)
      
        for node in node_details:
            node_hostname = node.get("hostname")
            node_ip = node.get("ip")
            print(node_ip)
            
            if node_hostname == namenode_hostname:
                continue  # Passer le NameNode déjà configuré

            ssh_node = None
            try:
                # 1. Connexion SSH au nœud
                ssh_node = paramiko.SSHClient()
                ssh_node.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_node.connect(node_ip, username='vagrant', password="vagrant")
                app.logger.info(f"Connexion établie avec {node_hostname} ({node_ip})")
                print("Connexion établie avec {node_hostname} ({node_ip})")
                # 2. Génération des clés SSH
                gen_key_cmd = '''
                    [ -f ~/.ssh/id_rsa.pub ] || 
                    ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa -q
                '''
                stdin, stdout, stderr = ssh_node.exec_command(gen_key_cmd)
                if stdout.channel.recv_exit_status() != 0:
                    raise Exception("Échec génération clé SSH : " + stderr.read().decode())

                # 3. Récupération clé publique
                stdin, stdout, stderr = ssh_node.exec_command("cat ~/.ssh/id_rsa.pub")
                node_pubkey = stdout.read().decode('utf-8', 'replace').strip()
                if not node_pubkey.startswith('ssh-rsa'):
                    raise ValueError("Format de clé invalide")

                # 4. Configuration autorized_keys
                cmds = [
                    # Sur le nœud courant
                    f"echo {shlex.quote(node_pubkey)} >> ~/.ssh/authorized_keys",
                    f"echo {shlex.quote(namenode_public_key)} >> ~/.ssh/authorized_keys",
                    
                    # Sur le NameNode
                    f"echo {shlex.quote(node_pubkey)} >> ~/.ssh/authorized_keys"
                ]

                # Exécution sur le nœud
                for cmd in cmds[:2]:
                    stdin, stdout, stderr = ssh_node.exec_command(f"mkdir -p ~/.ssh && {cmd}")
                    if stdout.channel.recv_exit_status() != 0:
                        raise Exception(f"Échec configuration : {stderr.read().decode()}")

                # Exécution sur le NameNode
                stdin, stdout, stderr = nn_ssh.exec_command(f"mkdir -p ~/.ssh && {cmds[2]}")
                if stdout.channel.recv_exit_status() != 0:
                    raise Exception(f"Échec configuration NameNode : {stderr.read().decode()}")

                # 5. Vérification finale
                verify_cmd = "ssh -o StrictHostKeyChecking=no {} hostname".format(namenode_ip)
                stdin, stdout, stderr = ssh_node.exec_command(verify_cmd, timeout=10)
                if stdout.channel.recv_exit_status() != 0:
                    raise Exception("Échec connexion SSH inversée : " + stderr.read().decode())

                app.logger.info(f"Configuration SSH réussie pour {node_hostname}")
                print(" ssh terminée")

            except Exception as e:
                app.logger.error(f"ERREUR sur {node_hostname}", exc_info=True)
                return jsonify({
                    "error": f"Échec configuration SSH pour {node_hostname}",
                    "details": str(e),
                    "node_ip": node_ip,
                    "logs": {
                        "pubkey": node_pubkey[:100] + "..." if node_pubkey else None,
                        "last_command": cmd if 'cmd' in locals() else None
                    }
                }), 500

            finally:
                if ssh_node:
                    ssh_node.close()
        # 8. Installation de Hadoop sur le NameNode et mise à jour de l'archive dans le dossier partagé
       
# 8. Installation de Hadoop sur le NameNode
        namenode_ssh = None
        try:
            # Connexion SSH directe au NameNode
            namenode_ssh = paramiko.SSHClient()
            namenode_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Configuration avec timeout et keepalive
            namenode_ssh.connect(
                namenode_ip,
                username='vagrant',
                password='vagrant',
                timeout=20,
                banner_timeout=40
            )
            
            # Activer le keepalive
            transport = namenode_ssh.get_transport()
            transport.set_keepalive(30)

            # Vérifier si l'archive existe
            stdin, stdout, stderr = namenode_ssh.exec_command('[ -f /vagrant/hadoop.tar.gz ] && echo "exists"')
            archive_exists = "exists" in stdout.read().decode()
            print(stdout, archive_exists)

            if not archive_exists:
                # Téléchargement et installation
                commands = [
                    'sudo apt-get update -qq',
                    'sudo apt-get install -y wget',
                    'wget -q -O /tmp/hadoop.tar.gz https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz',
                    'sudo tar -xzf /tmp/hadoop.tar.gz -C /opt',
                    'sudo mv /opt/hadoop-3.3.1 /opt/hadoop',
                    'sudo tar -czf /tmp/hadoop.tar.gz -C /opt hadoop',
                    'sudo cp /tmp/hadoop.tar.gz /vagrant/'
                ]

                for cmd in commands:
                    app.logger.info(f"Exécution: {cmd[:60]}...")  # Log partiel pour éviter le spam
                    stdin, stdout, stderr = namenode_ssh.exec_command(cmd, timeout=300)
                    
                    # Attendre la fin de l'exécution
                    exit_status = stdout.channel.recv_exit_status()
                    if exit_status != 0:
                        error = stderr.read().decode('utf-8', 'replace')
                        raise Exception(f"Échec commande '{cmd}': {error}")
                print("fin d'execution de la commande de creation!")

            # Extraction de l'archive (toujours nécessaire)
            extract_cmd = 'sudo rm -rf /opt/hadoop && sudo tar -xzf /vagrant/hadoop.tar.gz -C /opt'
            stdin, stdout, stderr = namenode_ssh.exec_command(extract_cmd, timeout=600)
            print("extracté")
            # Vérification finale
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error = stderr.read().decode('utf-8', 'replace')
                raise Exception(f"Échec extraction Hadoop: {error}")
# 9. Copier l'archive Hadoop vers les autres nœuds
            for node in node_details:
                node_hostname = node.get("hostname")
                node_ip = node.get("ip")
                
                if node_hostname == namenode_hostname:
                    continue

                ssh_node = None
                try:
                    # Connexion SSH au nœud cible
                    ssh_node = paramiko.SSHClient()
                    ssh_node.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh_node.connect(
                        node_ip,
                        username='vagrant',
                        password='vagrant',
                        timeout=15,
                        banner_timeout=30
                    )
                    
                    # Commandes d'installation
                    install_commands = [
                        'sudo apt-get update -qq',
                        'sudo rm -rf /opt/hadoop',
                        'sudo tar -xzf /vagrant/hadoop.tar.gz -C /opt'
                    ]
                    
                    for cmd in install_commands:
                        stdin, stdout, stderr = ssh_node.exec_command(cmd, timeout=300)
                        if stdout.channel.recv_exit_status() != 0:
                            error = stderr.read().decode('utf-8', 'replace')
                            raise Exception(f"Échec sur {node_hostname}: {error}")

                    app.logger.info(f"Hadoop installé avec succès sur {node_hostname}")

                except Exception as e:
                    app.logger.error(f"ERREUR {node_hostname}", exc_info=True)
                    return jsonify({
                        "error": f"Échec configuration {node_hostname}",
                        "details": str(e),
                        "node_ip": node_ip
                    }), 500
                finally:
                    if ssh_node:
                        ssh_node.close()
        except Exception as e:
            app.logger.error("ERREUR installation Hadoop: %s", str(e), exc_info=True)
            return jsonify({
                "error": "Échec configuration Hadoop",
                "details": str(e),
                "component": "hadoop_install"
            }), 500

        finally:
            # Fermeture propre de la connexion
            if namenode_ssh:
                namenode_ssh.close()
                app.logger.debug("Connexion NameNode fermée")
# 10. Installer Java, net-tools et configurer l'environnement sur tous les nœuds
        
# 10. Configuration de l'environnement sur tous les nœuds
        for node in node_details:
            node_hostname = node.get("hostname")
            node_ip = node.get("ip")
            
            ssh_node = None
            try:
                # Connexion SSH directe au nœud
                ssh_node = paramiko.SSHClient()
                ssh_node.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_node.connect(
                    node_ip,
                    username='vagrant',
                    password='vagrant',
                    timeout=15,
                    banner_timeout=30
                )
                
                # Installation des paquets
                install_cmd = '''
                    sudo apt-get update -qq && 
                    sudo apt-get install -yq default-jdk net-tools python3
                '''
                stdin, stdout, stderr = ssh_node.exec_command(install_cmd, timeout=300)
                if stdout.channel.recv_exit_status() != 0:
                    error = stderr.read().decode('utf-8', 'replace')
                    raise Exception(f"Échec installation paquets: {error}")

                # Configuration de l'environnement
                env_config = '''
                    echo 'export JAVA_HOME=/usr/lib/jvm/default-java' | sudo tee -a /etc/profile.d/hadoop.sh && 
                    echo 'export HADOOP_HOME=/opt/hadoop' | sudo tee -a /etc/profile.d/hadoop.sh && 
                    echo 'export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin' | sudo tee -a /etc/profile.d/hadoop.sh && 
                    sudo chmod +x /etc/profile.d/hadoop.sh
                '''
                stdin, stdout, stderr = ssh_node.exec_command(env_config)
                if stdout.channel.recv_exit_status() != 0:
                    error = stderr.read().decode('utf-8', 'replace')
                    raise Exception(f"Échec configuration environnement: {error}")

                # Appliquer immédiatement la configuration
                stdin, stdout, stderr = ssh_node.exec_command('source /etc/profile.d/hadoop.sh')
                
                app.logger.info(f"Configuration réussie pour {node_hostname}")

            except Exception as e:
                app.logger.error(f"ERREUR sur {node_hostname}", exc_info=True)
                return jsonify({
                    "error": f"Échec configuration {node_hostname}",
                    "details": str(e),
                    "node_ip": node_ip,
                    "component": "env_config"
                }), 500

            finally:
                if ssh_node:
                    ssh_node.close()
# 11. Création des playbooks Ansible et templates Jinja2 pour la configuration Hadoop
        remote_templates_dir = remote_cluster_folder + "/templates"
        try:
            sftp.chdir(remote_templates_dir)
        except IOError:
            sftp.mkdir("templates")
        # core-site.xml.j2
        with sftp.open(remote_templates_dir + "/core-site.xml.j2", "w") as f:
            f.write("""<configuration>
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://{{ namenode_hostname }}:9000</value>
  </property>
</configuration>
""")
        # hdfs-site.xml.j2
        with sftp.open(remote_templates_dir + "/hdfs-site.xml.j2", "w") as f:
            f.write("""<configuration>
  <property>
    <name>dfs.replication</name>
    <value>2</value>
  </property>
  <property>
    <name>dfs.namenode.http-address</name>
    <value>{{ namenode_hostname }}:9870</value>
  </property>
</configuration>
""")
        # yarn-site.xml.j2
        with sftp.open(remote_templates_dir + "/yarn-site.xml.j2", "w") as f:
            f.write("""<configuration>
  <property>
    <name>yarn.resourcemanager.hostname</name>
    <value>{{ groups['resourcemanager'][0] }}</value>
  </property>
</configuration>
""")
        # mapred-site.xml.j2
        with sftp.open(remote_templates_dir + "/mapred-site.xml.j2", "w") as f:
            f.write("""<configuration>
  <property>
    <name>mapreduce.framework.name</name>
    <value>yarn</value>
  </property>
</configuration>
""")
        # masters.j2
        with sftp.open(remote_templates_dir + "/masters.j2", "w") as f:
            f.write("{{ groups['namenode'][0] }}\n")
        # workers.j2
        with sftp.open(remote_templates_dir + "/workers.j2", "w") as f:
            f.write("""{% for worker in groups['datanodes'] %}
{{ worker }}
{% endfor %}
""")
        # hosts.j2
        with sftp.open(remote_templates_dir + "/hosts.j2", "w") as f:
            f.write("""# ANSIBLE GENERATED CLUSTER HOSTS
{% for host in groups['all'] %}
{{ hostvars[host]['ansible_host'] }} {{ host }}
{% endfor %}
""")
        remote_config_playbook = remote_cluster_folder + "/hadoop_config.yml"
        with sftp.open(remote_config_playbook, "w") as f:
            f.write("""---
- name: Configurer les fichiers de configuration Hadoop et /etc/hosts
  hosts: all
  sudo: yes
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
    - name: Mettre à jour /etc/hosts
      template:
        src: templates/hosts.j2
        dest: /etc/hosts
""")
        remote_start_playbook = remote_cluster_folder + "/hadoop_start_services.yml"
        with sftp.open(remote_start_playbook, "w") as f:
            f.write("""---
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
    - name: Créer /opt/hadoop/logs si nécessaire
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
      executable: /bin/bash
- name: Démarrer le ResourceManager
  hosts: resourcemanager
  become: yes
  tasks:
    - name: Démarrer YARN
      shell: "/opt/hadoop/sbin/start-yarn.sh"
      become_user: vagrant
      environment:
        JAVA_HOME: /usr/lib/jvm/default-java
      executable: /bin/bash
    - name: Démarrer explicitement le ResourceManager
      shell: "nohup /opt/hadoop/bin/yarn --daemon start resourcemanager > /tmp/resourcemanager.log 2>&1 &"
      become_user: vagrant
      environment:
        JAVA_HOME: /usr/lib/jvm/default-java
      executable: /bin/bash
    - name: Pause pour démarrer
      pause:
        seconds: 10
    - name: Vérifier les services Hadoop (jps)
      shell: "jps"
      register: jps_output
      become_user: vagrant
      executable: /bin/bash
    - name: Afficher les processus Hadoop
      debug:
        var: jps_output.stdout
""")
# 11. Exécution des playbooks via vagrant ssh sur le NameNode
        namenode_ssh = None
        try:
            # Connexion SSH avec vérification de stabilité
            namenode_ssh = paramiko.SSHClient()
            namenode_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            namenode_ssh.connect(
                namenode_ip,
                username='vagrant',
                password='vagrant',
                timeout=20,
                banner_timeout=45
            )
            
            # Configuration keepalive et vérification de la connexion
            transport = namenode_ssh.get_transport()
            transport.set_keepalive(15)  # Envoi d'un paquet NULL toutes les 15s
            
            # Forcer la copie du fichier d'inventaire vers un répertoire local qui gère bien les permissions
            fix_perm_cmd = "cp /vagrant/inventory.ini /tmp/inventory.ini && chmod 0644 /tmp/inventory.ini"
            stdin, stdout, stderr = namenode_ssh.exec_command(fix_perm_cmd)
            stdout.channel.recv_exit_status()  # attendre la fin de la commande

            # Utiliser le nouvel emplacement de l'inventaire pour l'exécution des playbooks
            inventory_path = "/tmp/inventory.ini"
            config_playbook = "/vagrant/hadoop_config.yml"
            start_playbook = "/vagrant/hadoop_start_services.yml"

            # Vérification préalable des fichiers (inventory et playbook de configuration)
            check_files_cmd = f"""
            [ -f {inventory_path} ] && \
            [ -f {config_playbook} ] || \
            (echo 'FICHIER MANQUANT' && exit 1)
            """
            stdin, stdout, stderr = namenode_ssh.exec_command(check_files_cmd)
            if stdout.channel.recv_exit_status() != 0:
                raise Exception("Fichier inventory ou playbook manquant")

            # Exécution du playbook de configuration
            config_cmd = f"""
            cd /vagrant && \
            ansible-playbook -i {inventory_path} {config_playbook} --verbose
            """
            stdin, stdout, stderr = namenode_ssh.exec_command(config_cmd, timeout=600)

            # Lecture en temps réel des sorties de la commande
            output = []
            while True:
                line = stdout.readline()
                if not line:
                    break
                output.append(line)
                app.logger.debug(f"ANSIBLE: {line.strip()}")

            exit_status = stdout.channel.recv_exit_status()
            full_output = ''.join(output)
            if exit_status != 0:
                error_details = {
                    "exit_code": exit_status,
                    "output": full_output,
                    "error": stderr.read().decode('utf-8', 'replace')
                }
                app.logger.error("ÉCHEC CONFIGURATION: %s", error_details)
                raise Exception(f"Échec configuration Hadoop: {error_details}")

            print("Playbook de configuration exécuté avec succès.")

            # Exécution du playbook de démarrage
            start_cmd = f"ansible-playbook -i {inventory_path} {start_playbook}"
            app.logger.info(f"Exécution: {start_cmd}")
            
            stdin, stdout, stderr = namenode_ssh.exec_command(start_cmd, timeout=300)
            exit_status = stdout.channel.recv_exit_status()
            start_output = stdout.read().decode('utf-8', 'replace')
            start_errors = stderr.read().decode('utf-8', 'replace')
            
            if exit_status != 0:
                app.logger.error("Échec démarrage services:\n%s\n%s", start_output, start_errors)
                return jsonify({
                    "error": "Échec démarrage services Hadoop",
                    "details": {
                        "stdout": start_output,
                        "stderr": start_errors
                    }
                }), 500

            app.logger.info("Configuration Hadoop terminée avec succès")
            print("Playbooks exécutés avec succès.")

        except Exception as e:
            app.logger.exception("ERREUR EXÉCUTION PLAYBOOK")
            return jsonify({
                "error": "Erreur critique pendant l'exécution Ansible",
                "details": str(e)
            }), 500

        finally:
            if namenode_ssh:
                namenode_ssh.close()


  # -------------------- 12. Copie du dossier du cluster depuis la machine distante vers la machine source --------------------
        local_cluster_local_folder = os.path.join("clusters_local", cluster_name)
        if not os.path.exists(local_cluster_local_folder):
            os.makedirs(local_cluster_local_folder)
        # Ici, on copie au moins le Vagrantfile (vous pouvez étendre à d'autres fichiers)
        local_vagrantfile_path = os.path.join(local_cluster_local_folder, "Vagrantfile")
        with sftp.open(remote_vagrantfile_path, "rb") as remote_vf:
            vagrant_data = remote_vf.read()
        with open(local_vagrantfile_path, "wb") as local_vf:
            local_vf.write(vagrant_data)
        print("DEBUG - Vagrantfile copié localement :", local_vagrantfile_path)

        # 13. Fermeture des connexions
        sftp.close()
        client.close()

        # Préparation de la réponse
        cluster_details = {
            "message": f"Cluster '{cluster_name}' created remotely with full configuration",
            "remote_cluster_folder": remote_cluster_folder,
            "vagrant_up_output": out_vagrant,
            "local_vagrantfile": os.path.abspath(local_vagrantfile_path)
        }
        # (Optionnel) Envoi d'email avec les infos du cluster via votre fonction send_email_with_cluster_credentials
        # if recipient_email:
        # send_email_with_cluster_credentials(recipient_email, cluster_details)

        return jsonify(cluster_details), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)