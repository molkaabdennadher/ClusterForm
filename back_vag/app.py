
from flask import Flask, request, jsonify, render_template
import subprocess
import os
import paramiko
import traceback
import random
import shutil
import smtplib
from email.message import EmailMessage
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def check_and_install_vagrant():
    """
    Vérifie si Vagrant est installé et, sinon, tente de l'installer via Winget.
    """
    vagrant_path = shutil.which("vagrant")
    if vagrant_path is None:
        print("Vagrant n'est pas installé. Tentative d'installation via winget...")
        try:
            # Winget installe Vagrant (nécessite d'être en mode administrateur)
            subprocess.run(
                ["winget", "install", "--id", "HashiCorp.Vagrant", "-e", "--accept-package-agreements", "--accept-source-agreements"],
                check=True
            )
            vagrant_path = shutil.which("vagrant")
            if vagrant_path:
                print("Vagrant installé avec succès.")
            else:
                raise Exception("Installation terminée mais Vagrant n'a pas été trouvé dans le PATH.")
        except subprocess.CalledProcessError as e:
            raise Exception("Échec de l'installation automatique de Vagrant: " + str(e))

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
    # Création locale de la VM (similaire à votre code existant)
    try:
        check_and_install_vagrant()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
