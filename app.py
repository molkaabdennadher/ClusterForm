from flask import Flask, request, jsonify,render_template
from email.message import EmailMessage

from flask_cors import CORS
import paramiko
import subprocess
import time
import requests
#################################################
import os
import re
import traceback
import random
import shutil
import platform
import glob
import smtplib
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import tempfile

app = Flask(__name__)
CORS(app)
NODE_MAPPING = {
    "192.168.1.5": "serveur1",
    "192.168.1.100": "serveur",
}


# Fonction de connexion à Proxmox
def connect_to_proxmox(proxmoxIp, username, password):
    url = f"https://{proxmoxIp}:8006/api2/json/access/ticket"
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
    #################################################################################################################################
@app.route("/add_server", methods=["POST"])
def add_server():
    # Récupérer les données envoyées par le frontend
    data = request.get_json()
    proxmox_ip = data.get("serverIp")
    node = data.get("node")
    user = data.get("user")
    password = data.get("password")

    # Exemple d'URL pour l'API Proxmox, à adapter selon ton cas
    proxmox_url = f"https://{proxmox_ip}:8006/api2/json/nodes/{node}/status"

    # Authentification avec l'API Proxmox
    auth = (user, password)

    # Essayer de récupérer l'état du serveur ou effectuer une autre action via l'API
    try:
        response = requests.get(proxmox_url, auth=auth, verify=False)  # verify=False pour ignorer SSL (à ne pas faire en production)
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Serveur ajouté avec succès"})
        else:
            return jsonify({"status": "error", "message": "Erreur avec l'API Proxmox"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    #################################################################################################################################
    # Fonction pour récupérer la RAM totale
@app.route('/get_limits', methods=['GET'])
def get_limits():
    try:
        ram_result = subprocess.check_output(["powershell", "-Command", "Get-ComputerInfo | Select-Object -ExpandProperty CsTotalPhysicalMemory"], text=True).strip()
        cpu_result = subprocess.check_output(["powershell", "-Command", "Get-WmiObject -Class Win32_Processor | Select-Object NumberOfLogicalProcessors"], text=True).strip()
        
        # Convertir la RAM de bytes à Mo
        total_ram_mb = int(ram_result) / (1024 * 1024)
        total_cpu = int(cpu_result.split()[-1])

        return jsonify({
            "max_ram": int(total_ram_mb),
            "max_cpu": total_cpu
        })
    except Exception as e:
        return jsonify({"error": str(e)})

#################################################################################################################################

@app.route('/clone_template', methods=['POST'])
def clone_template():
    try:
        print(f"Utilisateur en cours d'exécution : {os.getpid()}")
        print("[INFO] Requête reçue pour le clonage...")

        # Récupération des données du formulaire
        data = request.get_json()
        source_proxmox_ip = data.get('sourceProxmoxIp')
        target_proxmox_ip = data.get('targetProxmoxIp')
        template_id = data.get('template_id')
        username = data.get('username')
        password = data.get('password')
        target_vm_id = data.get('target_vm_id', 9000)

        if not all([source_proxmox_ip, target_proxmox_ip, template_id, username, password]):
            return jsonify({"success": False, "message": "Tous les champs sont requis"}), 400

        print(f"[INFO] Export de la VM {template_id} depuis {source_proxmox_ip}")
        vzdump_command = f"vzdump {template_id} --dumpdir /var/lib/vz/dump --mode stop --compress zstd"

        # Connexion SSH au serveur source
        ssh_source = paramiko.SSHClient()
        ssh_source.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_source.connect(source_proxmox_ip, username=username, password=password)

        # Exécution de la commande vzdump
        stdin, stdout, stderr = ssh_source.exec_command(vzdump_command)
        exit_status = stdout.channel.recv_exit_status()
        vzdump_error = stderr.read().decode()

        if exit_status != 0:
            print(f"[ERROR] Erreur lors de l'exportation : {vzdump_error}")
            ssh_source.close()
            return jsonify({"success": False, "message": f"Erreur lors de l'exportation : {vzdump_error}"}), 500

        print("[INFO] Export terminé, recherche du fichier généré...")

        # Recherche du fichier vzdump sur le serveur Proxmox
        vzdump_path = None
        timeout = 30  # Attente max de 30 secondes
        while timeout > 0:
            vzdump_path = find_latest_vzdump(ssh_source, template_id)
            if vzdump_path:
                print(f"[INFO] Fichier trouvé : {vzdump_path}")
                break
            print(f"[ATTENTE] Fichier non trouvé, réessai dans 2 secondes...")
            time.sleep(2)
            timeout -= 2

        if not vzdump_path:
            print(f"[ERREUR] Aucun fichier vzdump trouvé après 30 secondes")
            ssh_source.close()
            return jsonify({"success": False, "message": "Aucun fichier vzdump trouvé après l'exportation !"}), 500

        vzdump_filename = os.path.basename(vzdump_path)
        print(f"[INFO] Fichier vzdump trouvé : {vzdump_filename}, début du transfert vers {target_proxmox_ip}...")

        # Transfert du fichier vzdump vers le serveur cible avec scp
        scp_command = f"scp -o StrictHostKeyChecking=no {vzdump_path} {username}@{target_proxmox_ip}:/var/lib/vz/dump/"
        stdin, stdout, stderr = ssh_source.exec_command(scp_command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        print(f"[DEBUG] Sortie de scp : {output}")
        print(f"[DEBUG] Erreurs de scp : {error}")
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            print(f"[ERROR] Erreur lors du transfert scp : {error}")
            ssh_source.close()
            return jsonify({"success": False, "message": "Erreur lors du transfert scp"}), 500

        print("[INFO] Transfert terminé, restauration en cours sur le serveur cible...")

        # Restauration de la VM sur le serveur cible
        ssh_target = paramiko.SSHClient()
        ssh_target.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_target.connect(target_proxmox_ip, username=username, password=password)

        qmrestore_command = f"qmrestore /var/lib/vz/dump/{vzdump_filename} {target_vm_id}"
        stdin, stdout, stderr = ssh_target.exec_command(qmrestore_command)
        exit_status = stdout.channel.recv_exit_status()
        restore_error = stderr.read().decode()
        ssh_target.close()

        if exit_status != 0:
            print(f"[ERROR] Erreur lors de la restauration : {restore_error}")
            return jsonify({"success": False, "message": f"Erreur lors de la restauration : {restore_error}"}), 500

        print(f"[SUCCESS] Clonage réussi sur {target_proxmox_ip} avec l'ID {target_vm_id}")
        return jsonify({"success": True, "message": f"Clonage réussi sur {target_proxmox_ip} avec l'ID {target_vm_id}"}), 200

    except Exception as e:
        print(f"[EXCEPTION] {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


def find_latest_vzdump(ssh_client, template_id):
    dump_dir = "/var/lib/vz/dump"
    # Commande pour lister les fichiers correspondant au motif
    command = f"ls -t {dump_dir}/vzdump-qemu-{template_id}-*.vma.zst 2>/dev/null | head -n 1"
    print(f"[DEBUG] Commande exécutée : {command}")

    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    vzdump_path = stdout.read().decode().strip()
    error_output = stderr.read().decode()

    if exit_status != 0:
        print(f"[DEBUG] Erreur lors de l'exécution de la commande : {error_output}")
        return None

    print(f"[DEBUG] Fichier trouvé : {vzdump_path}")
    return vzdump_path if vzdump_path else None

#################################################################################################################################
@app.route('/create_vmprox', methods=['POST'])  
def create_vmprox():
    data = request.json
    vm_id = request.form.get('vm_id')
    print(data)  

    proxmoxIp = data.get('proxmoxIp')  
    password = data.get('password')
    hostname = data.get('hostname')
    ram = data.get('ram')
    cpu = data.get('cpu')
    target_node = data.get('targetNode')
    network = data.get('network', 'nat')  
    vm_id = data.get('vm_id')  # Corriger ici
    if not all([proxmoxIp, password, hostname, ram, cpu, target_node, vm_id]):
        return jsonify({"error": "Missing required fields"}), 400
    # Créer un fichier variables.tfvars pour Terraform
    terraform_vars = f"""
proxmox_ip = "{proxmoxIp}"
password = "{password}"
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
        
        # Exécution de la commande Terraform pour créer la VM en clonant le template
        print("Creating VM with Terraform...")
        result = subprocess.run(["terraform", "apply", "-auto-approve", "-var-file=variables.tfvars"], capture_output=True, text=True)

        # Vérifiez si l'erreur "plugin crashed" apparaît dans la sortie
        if "Error: The terraform-provider-proxmox_v2.9.11.exe plugin crashed!" in result.stderr:
            print("Terraform plugin crash detected, proceeding with conf_vm...")
            # Appeler la fonction conf_vm ici
            conf_vmprox()

        print("VM created successfully.")
        return jsonify({"message": f"VM {vm_id} cloned from template {hostname} successfully!"}), 200

    except subprocess.CalledProcessError as e:
        print(f"Error during Terraform execution: {e}")
        return jsonify({"error": "Failed to create VM"}), 500
    #################################################################################################################################
@app.route('/conf_vmprox', methods=['POST'])
def conf_vmprox():
    data = request.json

    proxmoxIp = data.get('proxmoxIp')
    password = data.get('password')
    username = 'root'
    vm_id = data.get('vm_id')
    ram = data.get('ram')
    cpu = data.get('cpu')

    if not all([proxmoxIp, password, vm_id, ram, cpu]):
        return jsonify({"error": "Missing required fields"}), 400

    # Création de la session SSH
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Connexion SSH à Proxmox
        print(f"Connecting to Proxmox server at {proxmoxIp}...")
        ssh.connect(proxmoxIp, username=username, password=password, look_for_keys=False)
        print(f"Connected to {proxmoxIp}")

        # Commande pour configurer la VM (mémoire et CPU)
        command = f"qm set {vm_id} --memory {ram} --cores {cpu}"
        print(f"Running command: {command}")
        stdin, stdout, stderr = ssh.exec_command(command)

        # Lire la sortie et les erreurs
        output = stdout.read().decode()
        error = stderr.read().decode()
        print(f"Command output: {output}")
        if error:
            print(f"Command error: {error}")
            return jsonify({"error": f"Error: {error}"}), 500

        # Démarrer la VM si elle n'est pas en cours d'exécution
        start_command = f"qm start {vm_id}"
        print(f"Running start command: {start_command}")
        stdin, stdout, stderr = ssh.exec_command(start_command)
        start_output = stdout.read().decode()
        start_error = stderr.read().decode()
        if start_error:
            print(f"Start command error: {start_error}")
            return jsonify({"error": f"Error starting VM: {start_error}"}), 500
        print(f"VM started: {start_output}")

        # Attendre 30 secondes pour que la VM récupère son IP
        print("Waiting 30 seconds for the VM to initialize and get an IP address...")
        time.sleep(60)

        # Récupérer l'adresse IP avec la commande 'qm guest exec'
        ip_command = f"qm guest exec {vm_id} -- ip a"
        print(f"Running IP fetch command: {ip_command}")
        stdin, stdout, stderr = ssh.exec_command(ip_command)
        ip_output = stdout.read().decode()
        ip_error = stderr.read().decode()

        if ip_error:
            print(f"IP fetch command error: {ip_error}")
            return jsonify({"error": f"Error fetching IP address: {ip_error}"}), 500

        print(f"VM IP address information: {ip_output}")

        return jsonify({"message": "VM configured and started successfully!", "ip_info": ip_output})

    except Exception as e:
        print(f"Error during SSH connection or execution: {e}")
        return jsonify({"error": f"Error during SSH connection or execution: {str(e)}"}), 500
    finally:
        # Fermer la connexion SSH
        ssh.close()


    #################################################################################################################################
    
@app.route('/start_vmprox', methods=['POST'])
def start_vmprox():
    try:
        data = request.json  # Récupère les données JSON envoyées
        proxmox_ip = data.get('proxmox_ip')
        username = data.get('username')
        password = data.get('password')
        vm_id = data.get('vm_id')

        # Création de la session SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connexion au serveur Proxmox
        ssh.connect(proxmox_ip, username=username, password=password)

        # Commande à exécuter pour démarrer la VM
        command = f"qm start {vm_id}"

        # Exécution de la commande
        stdin, stdout, stderr = ssh.exec_command(command)

        # Lecture de la sortie de la commande
        output = stdout.read().decode()
        error = stderr.read().decode()

        if output:
            return jsonify({"message": f"VM started successfully: {output}"}), 200
        if error:
            return jsonify({"error": f"Error: {error}"}), 500

        return jsonify({"status": "success", "message": "Machine virtuelle démarrée avec succès!"})

    except Exception as e:
        # Retourner une erreur si quelque chose se passe mal
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        # Fermeture de la connexion SSH
        ssh.close()

    #################################################################################################################################
@app.route('/stop_vmprox', methods=['POST'])
def stop_vmprox():
    try:
        data = request.json  # Récupère les données JSON envoyées
        print("Données reçues:", data)  # Affiche les données dans les logs pour déboguer

        proxmox_ip = data.get('proxmox_ip')
        username = data.get('username')
        password = data.get('password')
        vm_id = data.get('vm_id')
        # Connexion SSH à Proxmox
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(proxmox_ip, username=username, password=password)

        # Arrêter la VM
        ssh.exec_command(f'qm stop {vm_id}')
        ssh.close()

        # Réponse en cas de succès
        return jsonify({"status": "success", "message": "Machine virtuelle arrêtée avec succès!"})

    except Exception as e:
        # Retourner une erreur si quelque chose se passe mal
        return jsonify({"status": "error", "message": str(e)}), 500


    #################################################################################################################################
@app.route('/delete_vmprox', methods=['POST'])
def delete_vmprox   ():
    ssh = None  # Initialisation de la variable ssh avant le bloc try
    try:
        # Vérifier les données reçues
        data = request.json
        print("Données reçues depuis la requête POST : ", data)  # Affiche les données reçues

        proxmoxIp = data.get('proxmoxIp')  # Si l'orthographe est incorrecte, vérifie ici
        vm_id = data.get('vm_id')
        username = data.get('username')
        password = data.get('password')

        print(f"Proxmox IP: {proxmoxIp}, VM ID: {vm_id}, Username: {username}, Password: {password}")

        # Vérifier si les paramètres nécessaires sont présents
        if not all([proxmoxIp, username, password, vm_id]):
            return jsonify({"error": "Missing required parameters"}), 400

        # Création de la session SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(proxmoxIp, username=username, password=password)

        # Commande pour supprimer la VM
        command = f"qm destroy {vm_id}"

        # Exécution de la commande
        stdin, stdout, stderr = ssh.exec_command(command)

        # Lire la sortie et les erreurs
        output = stdout.read().decode()
        error = stderr.read().decode()

        if output:
            return jsonify({"message": f"VM deleted successfully: {output}"}), 200
        if error:
            return jsonify({"error": f"Error: {error}"}), 500

        return jsonify({"status": "success", "message": "Machine virtuelle supprimée avec succès!"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if ssh:  # Vérifier si ssh a été créé avant de la fermer
            ssh.close()

    #################################################################################################################################
@app.route('/open_console', methods=['POST'])
def open_console():
        try:
            data = request.json
            print("Données reçues pour la console :", data)

            proxmoxIp = data.get('proxmoxIp')
            username = data.get('username')
            password = data.get('password')

            if not all([proxmoxIp, username, password]):
                return jsonify({"error": "Paramètres manquants"}), 400

            # Commande pour ouvrir SSH dans un terminal
            cmd = f'start cmd /k ssh {username}@{proxmoxIp}'
            
            # Exécuter la commande dans un nouveau terminal
            subprocess.Popen(cmd, shell=True)

            return jsonify({"success": True, "message": "Console ouverte avec succès"}), 200

        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
        


        #####################################################################################################
 

@app.route('/migrate_vm', methods=['POST'])
def migrate_vm():
    try:
        # Récupérer les données de la requête
        data = request.get_json()
        source_proxmox_ip = data.get('sourceProxmoxIp')
        target_proxmox_ip = data.get('targetProxmoxIp')
        vm_id = data.get('vm_id')
        username = data.get('username')
        password = data.get('password')

        # Valider les données
        if not all([source_proxmox_ip, target_proxmox_ip, vm_id, username, password]):
            return jsonify({"success": False, "message": "Tous les champs sont requis"}), 400

        # Récupérer le nom du nœud cible à partir de l'adresse IP
        target_node = NODE_MAPPING.get(target_proxmox_ip)
        if not target_node:
            return jsonify({"success": False, "message": "Adresse IP cible non reconnue"}), 400

        # Commande de migration
        migrate_command = f"qm migrate {vm_id} {target_node} --online"

        # Exécuter la commande sur le serveur source via SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(source_proxmox_ip, username=username, password=password)

        stdin, stdout, stderr = ssh.exec_command(migrate_command)
        output = stdout.read().decode()
        error = stderr.read().decode()

        ssh.close()

        # Vérifier si la migration a réussi
        if "migration finished" in output:  # Adapter cette condition selon la sortie de la commande
            return jsonify({"success": True, "message": f"VM {vm_id} migrée avec succès vers {target_node}"})
        else:
            return jsonify({"success": False, "message": f"Erreur lors de la migration : {error}"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur lors de la migration : {str(e)}"}), 500
        #####################################################################################################
        #####################################################################################################
                ####################################################################################################
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
    inventory_path = os.path.join(cluster_folder, "inventory.ini")
    try:
        with open(inventory_path, "w") as inv_file:
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

    # b. Générer une clé SSH sur le NameNode si elle n'existe pas et récupérer la clé publique
    try:
        gen_key_cmd = f'vagrant ssh {namenode_hostname} -c "test -f ~/.ssh/id_rsa.pub || ssh-keygen -t rsa -N \'\' -f ~/.ssh/id_rsa"'
        subprocess.run(gen_key_cmd, shell=True, cwd=cluster_folder, check=True)
        get_pubkey_cmd = f'vagrant ssh {namenode_hostname} -c "cat ~/.ssh/id_rsa.pub"'
        result_pub = subprocess.run(get_pubkey_cmd, shell=True, cwd=cluster_folder,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
        public_key = result_pub.stdout.strip()
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error generating or retrieving SSH key on NameNode", "details": str(e)}), 500

    # c. Configurer SSH sur les autres nœuds en ajoutant la clé publique dans leur authorized_keys
    for node in node_details:
        if node.get("hostname") != namenode_hostname:
            target_hostname = node.get("hostname")
            try:
                copy_key_cmd = f'vagrant ssh {target_hostname} -c "mkdir -p ~/.ssh && echo \'{public_key}\' >> ~/.ssh/authorized_keys"'
                subprocess.run(copy_key_cmd, shell=True, cwd=cluster_folder, check=True)
            except subprocess.CalledProcessError as e:
                return jsonify({"error": f"Error configuring SSH on node {target_hostname}", "details": str(e)}), 500

    # 6. Installation de Hadoop sur le NameNode, copie de l'installation sur les autres nœuds,
    try:
        # Install Hadoop on the NameNode with error handling
        hadoop_install_cmd = (
            f'vagrant ssh {namenode_hostname} -c "sudo apt-get update && sudo apt-get install -y wget && '
            f'wget -O /tmp/hadoop.tar.gz https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz && '
            f'test -s /tmp/hadoop.tar.gz && '  # Check file exists and size > 0
            f'sudo tar -xzvf /tmp/hadoop.tar.gz -C /opt && '
            f'sudo mv /opt/hadoop-3.3.1 /opt/hadoop && '
            f'rm /tmp/hadoop.tar.gz"'
        )
        subprocess.run(hadoop_install_cmd, shell=True, cwd=cluster_folder, check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Error installing Hadoop on NameNode", "details": str(e)}), 500



# Installer Java et net-tools et configurer les variables d'environnement sur tous les nœuds
    for node in node_details:
        target_hostname = node.get("hostname")
        try:
            install_java_net_cmd = (
                f'vagrant ssh {target_hostname} -c "sudo apt-get update && sudo apt-get install -y default-jdk net-tools"'
            )
            subprocess.run(install_java_net_cmd, shell=True, cwd=cluster_folder, check=True)
            configure_env_cmd = (
                f'vagrant ssh {target_hostname} -c "echo \'export JAVA_HOME=/usr/lib/jvm/default-java\' >> ~/.bashrc && '
                f'echo \'export HADOOP_HOME=/opt/hadoop\' >> ~/.bashrc && '
                f'echo \'export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin\' >> ~/.bashrc"'
            )
            subprocess.run(configure_env_cmd, shell=True, cwd=cluster_folder, check=True)
        except subprocess.CalledProcessError as e:
            return jsonify({"error": f"Error installing Java/net or configuring environment on node {target_hostname}", "details": str(e)}), 500

    return jsonify({
        "message": "Cluster created successfully, inventory generated, ansible installed on NameNode, SSH configured, "
                   "Hadoop installed and copied, Java and net-tools installed and environment variables configured",
        "cluster_folder": cluster_folder,
        "inventory_file": inventory_path
    }), 200

    return jsonify({
        "message": "Cluster created successfully, inventory generated, ansible installed on NameNode, SSH configured, "
                   "Hadoop installed and copied, Java and net-tools installed and environment variables configured",
        "cluster_folder": cluster_folder,
        "inventory_file": inventory_path
    }), 200
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
