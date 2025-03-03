
from flask import Flask, request, jsonify, render_template
import subprocess
import os
import paramiko
import re
import traceback
import random
import shutil
import platform
import smtplib
from email.message import EmailMessage
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
@app.route('/get-vm-status', methods=['POST'])
def get_vm_status():
    data = request.get_json()
    vm_name = data.get('vm_name')
    mode = data.get('mode', 'local').lower()

    if mode == 'local':
        try:
            vm_path = os.path.join(".", "vms", vm_name)
            if not os.path.exists(vm_path):
                return jsonify({"error": "VM non trouvée"}), 404
            result = subprocess.check_output(
                ["vagrant", "status"], 
                cwd=vm_path, 
                universal_newlines=True,
                stderr=subprocess.STDOUT
            )
            state_line = [line for line in result.splitlines() if line.strip().startswith("Current state:")]
            if state_line:
                state = state_line[0].split(': ')[1]
                return jsonify({"status": state}), 200
            else:
                return jsonify({"status": "Statut inconnu"}), 200
        except subprocess.CalledProcessError as e:
            return jsonify({"status": "Erreur"}), 200
    else:
        return jsonify({"status": "Not allowed"}), 200
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
            ip_address_generated = f"192.168.56.{random.randint(2,254)}"
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

if __name__ == '__main__':
    app.run(debug=True)
