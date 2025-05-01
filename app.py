from flask import Flask, request, jsonify,render_template
from email.message import EmailMessage

from flask_cors import CORS
import paramiko
import subprocess
import time
import requests
import logging
from jinja2 import Environment, FileSystemLoader
import sys
import json
import re
from datetime import datetime, timezone
#################################################
import os
import traceback
from pathlib import Path
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
# Liste pour stocker les serveurs (en mémoire)
servers = []

@app.route('/add_server', methods=['POST'])
def add_server():
    data = request.json
    server_ip = data.get('serverIp')
    node = data.get('node')
    user = data.get('user')
    password = data.get('password')

    # Vérification des champs obligatoires
    if not all([server_ip, node, user, password]):
        return jsonify({"success": False, "message": "Missing required fields"}), 400

    # Ajouter le serveur à la liste
    new_server = {
        "serverIp": server_ip,
        "node": node,
        "user": user,
        "password": password
    }
    servers.append(new_server)

    return jsonify({"success": True, "message": "Server added successfully"})
###################################################

@app.route('/connect_and_get_templates', methods=['POST'])
def connect_and_get_templates():
    data = request.json
    proxmox_ip = data.get('proxmox_ip')
    username = data.get('username')
    password = data.get('password')

    # Vérification des champs obligatoires
    if not all([proxmox_ip, username, password]):
        return jsonify({"success": False, "error": "Tous les champs obligatoires (proxmox_ip, username, password) doivent être fournis."}), 400

    ssh = None  # Initialiser la variable ssh pour la fermeture dans le bloc finally
    try:
        # Connexion SSH au serveur Proxmox
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(proxmox_ip, username=username, password=password, timeout=10)  # Ajouter un timeout

        # Exécution de la commande `qm list`
        stdin, stdout, stderr = ssh.exec_command("qm list")
        output = stdout.read().decode()
        error_output = stderr.read().decode()

        # Vérifier s'il y a des erreurs
        if error_output:
            raise Exception(f"Erreur lors de l'exécution de la commande 'qm list' : {error_output}")

        # Extraction des templates et leurs IDs
        templates = []
        for line in output.splitlines()[1:]:  # Ignorer la première ligne (en-tête)
            parts = line.split()
            if len(parts) > 1:
                template_id = parts[0]  # L'ID du template est dans la première colonne
                template_name = parts[1]  # Le nom du template est dans la deuxième colonne
                templates.append({"id": template_id, "name": template_name})  # Ajouter un objet avec ID et nom

        return jsonify({
            "success": True,
            "message": "Connexion réussie",
            "templates": templates  # Retourner la liste des templates avec leurs IDs
        })
    except paramiko.AuthenticationException:
        return jsonify({"success": False, "error": "Échec de l'authentification SSH. Vérifiez les informations d'identification."}), 401
    except paramiko.SSHException as e:
        return jsonify({"success": False, "error": f"Échec de la connexion SSH : {str(e)}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Erreur inattendue : {str(e)}"}), 500
    finally:
        if ssh:  # Fermer la connexion SSH si elle a été établie
            ssh.close()

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

        # Validation des champs requis
        if not all([source_proxmox_ip, target_proxmox_ip, template_id, username, password]):
            return jsonify({"success": False, "message": "Tous les champs sont requis"}), 400

        # Validation de template_id
        try:
            template_id = int(template_id)
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "template_id doit être un nombre entier valide"}), 400

        print(f"[INFO] Export de la VM {template_id} depuis {source_proxmox_ip}")

        # Connexion SSH au serveur source
        ssh_source = paramiko.SSHClient()
        ssh_source.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_source.connect(source_proxmox_ip, username=username, password=password, timeout=30)

        # Vérifier si le template existe
        check_template_command = f"qm list | grep {template_id}"
        stdin, stdout, stderr = ssh_source.exec_command(check_template_command)
        template_exists = stdout.read().decode().strip()

        if not template_exists:
            ssh_source.close()
            return jsonify({"success": False, "message": f"Le template avec l'ID {template_id} n'existe pas sur le serveur source"}), 400

        # Exécution de la commande vzdump
        vzdump_command = f"vzdump {template_id} --dumpdir /var/lib/vz/dump --mode stop --compress zstd"
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

        # Appeler create_vmprox et conf_vmprox après la restauration
        create_data = {
            "proxmoxIp": target_proxmox_ip,
            "password": password,
            "hostname": "molkatest",
            "targetNode": "serveur",  # Remplacez par le nœud cible approprié
            "network": "bridged",  # Type de réseau par défaut
            "template": "ubuntu-template",  # Template par défaut
            "vm_id": template_id
        }
        create_response = requests.post(
                    "http://localhost:5000/create_vmprox",
                    json=create_data,
                    headers={"Content-Type": "application/json"}
                )
        if create_response.status_code != 200:
            return create_response


        return jsonify({"success": True, "message": f"Clonage, création et configuration réussis sur {target_proxmox_ip} avec l'ID {target_vm_id}"}), 200

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



##############################################################################################################""


#################################################################################################################################

#################################################################################################################################
#################################################################################################################################
@app.route('/start_vmprox', methods=['POST'])
def start_vmprox():
    try:
        # 1. Normalisation des noms de champs
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Normaliser les noms de champs (gère 'proxmox_ip' et 'proxmoxIp')
        proxmox_ip = data.get('proxmox_ip') or data.get('proxmoxIp')
        username = data.get('username')
        password = data.get('password')
        vm_id = data.get('vm_id')

        # 2. Validation des champs obligatoires
        missing_fields = []
        if not proxmox_ip:
            missing_fields.append("proxmox_ip")
        if not username:
            missing_fields.append("username")
        if not password:
            missing_fields.append("password")
        if not vm_id:
            missing_fields.append("vm_id")

        if missing_fields:
            return jsonify({
                "error": "Missing required fields",
                "missing": missing_fields,
                "received": list(data.keys())
            }), 400

        # 3. Connexion SSH améliorée
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            ssh.connect(
                hostname=proxmox_ip,
                username=username,
                password=password,
                timeout=15
            )
        except paramiko.AuthenticationException:
            return jsonify({"error": "Authentication failed"}), 401
        except Exception as e:
            return jsonify({"error": f"Connection error: {str(e)}"}), 502

        # 4. Exécution de la commande avec gestion du timeout
        try:
            command = f"qm start {vm_id}"
            stdin, stdout, stderr = ssh.exec_command(command, timeout=20)
            
            # Attendre la complétion
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            time.sleep(90)


            if exit_status == 0:
                return jsonify({
                    "status": "success",
                    "vm_id": vm_id,
                    "message": output or "VM started successfully"
                }), 200
            else:
                return jsonify({
                    "error": error or f"Failed to start VM (exit code: {exit_status})",
                    "vm_id": vm_id
                }), 500

        except Exception as e:
            return jsonify({
                "error": f"Command execution failed: {str(e)}",
                "vm_id": vm_id
            }), 500

    except Exception as e:
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500

    finally:
        if 'ssh' in locals():
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
    data = request.json  # Récupérer les données JSON de la requête POST
    vm_ip = data.get('vmIp')  # Adresse IP de la VM
    username = data.get('username')  # Nom d'utilisateur SSH
    password = data.get('password')  # Mot de passe SSH

    if not all([vm_ip, username, password]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        # Construire la commande SSH
        ssh_command = f"ssh {username}@{vm_ip}"

        # Ouvrir un terminal et exécuter la commande SSH
        if sys.platform == "win32":
            # Sur Windows, utiliser PowerShell
            subprocess.Popen(["start", "powershell", "-NoExit", "-Command", ssh_command], shell=True)
        else:
            # Sur Linux/Mac, utiliser le terminal natif
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{ssh_command}; exec bash"])

        return jsonify({
            "success": True,
            "message": f"Terminal ouvert avec succès. Connexion SSH en cours vers {vm_ip}.",
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Erreur lors de l'ouverture du terminal : {str(e)}",
        }), 500
#################################################################################################################################
@app.route('/conf_vmprox', methods=['POST'])
def conf_vmprox():
    data = request.json  # Récupérer les données de la requête POST
    proxmoxIp = data.get('proxmoxIp')
    password = data.get('password')
    username = 'root'
    vm_id = data.get('vm_id')

    if not all([proxmoxIp, password, vm_id]):
        return jsonify({"error": "Missing required fields"}), 400

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"Connecting to Proxmox server at {proxmoxIp}...")
        ssh.connect(proxmoxIp, username=username, password=password, look_for_keys=False)
        print(f"Connected to {proxmoxIp}")

        # Vérifier l'état de la VM
        status_command = f"qm status {vm_id}"
        stdin, stdout, stderr = ssh.exec_command(status_command)
        status_output = stdout.read().decode()
        status_error = stderr.read().decode()

        if status_error:
            print(f"Error checking VM status: {status_error}")
            return jsonify({"error": f"Error checking VM status: {status_error}"}), 500

        if "running" not in status_output.lower():
            # Démarrer la VM seulement si elle n'est pas déjà en cours d'exécution
            start_command = f"qm start {vm_id}"
            stdin, stdout, stderr = ssh.exec_command(start_command)
            start_error = stderr.read().decode()
            if start_error and "already running" not in start_error.lower():
                print(f"Start command error: {start_error}")
                return jsonify({"error": f"Error starting VM: {start_error}"}), 500
            print("VM started successfully.")
        else:
            print("VM is already running.")

        # Attendre que la VM soit complètement démarrée
        print("Waiting for VM to boot up...")
        time.sleep(90)  # Augmentez ce délai si nécessaire

        # Retrieve the IP address of the VM
        ip_command = f"qm guest exec {vm_id} -- ip a"
        print(f"Executing command: {ip_command}")
        stdin, stdout, stderr = ssh.exec_command(ip_command)
        ip_output = stdout.read().decode()
        ip_error = stderr.read().decode()

        if ip_error:
            print(f"Error executing 'qm guest exec': {ip_error}")
            return jsonify({"error": f"Error retrieving VM IP: {ip_error}"}), 500

        # Extract the IP address from the output
        extracted_ip = extract_ip(ip_output)
        if not extracted_ip:
            return jsonify({"error": "No IP address found"}), 500

        print("Extracted IP:", extracted_ip)
        return jsonify({
            "message": "VM configured and started successfully!",
            "ip": extracted_ip,  # Inclure l'adresse IP dans la réponse
        })
    except Exception as e:
        print(f"Error during SSH connection or execution: {e}")
        return jsonify({"error": f"Error during SSH connection or execution: {str(e)}"}), 500
    finally:
        ssh.close()

def extract_ip(ip_output):
    try:
        # Analyser la sortie JSON
        output_json = json.loads(ip_output)
        out_data = output_json.get("out-data", "")

        # Chercher l'IP dans la sortie de la commande "ip a"
        for line in out_data.splitlines():
            if "inet" in line and "scope global" in line:  # Filtrer les lignes avec "inet" et "scope global"
                parts = line.split()
                if len(parts) >= 2:  # Vérifier que la ligne contient une adresse IP
                    ip_with_prefix = parts[1]  # L'IP se trouve après "inet"
                    if "/" in ip_with_prefix:  # Vérifier que c'est une adresse IP valide
                        return f"inet {ip_with_prefix.split('/')[0]}"  # Retourne "inet <adresse_ip>"
        
        # Si aucune adresse IPv4 n'est trouvée
        return None
    except Exception as e:
        print(f"Error extracting IP: {e}")
        return None

#################################################################################################################################

@app.route('/create_vmprox', methods=['POST'])  
def create_vmprox():
    # Récupérer les données de la requête
    data = request.get_json()
    print("Data received:", data)  

    # Validation des données requises
    required_fields = ['proxmoxIp', 'password', 'hostname', 'targetNode', 'vm_id']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    # Extraction des données
    proxmox_ip = data.get('proxmoxIp')  
    password = data.get('password')
    hostname = data.get('hostname')
    target_node = data.get('targetNode')
    network = data.get('network', 'nat')  
    vm_id = data.get('vm_id')
    template = data.get('template', 'lubuntu-template')

    # Préparation des variables Terraform
    terraform_vars = f"""
proxmox_ip = "{proxmox_ip}"
password = "{password}"
hostname = "{hostname}"
target_node = "{target_node}"
network_ip = "{network}"
vm_id = {vm_id}
template = "{template}"
"""

    # Écriture du fichier de variables Terraform
    with open('variables.tfvars', 'w') as f:
        f.write(terraform_vars.strip())

    try:
        print("Initializing Terraform...")
        subprocess.run(["terraform", "init"], check=True)
        
        print("Applying Terraform configuration...")
        result = subprocess.run(
            ["terraform", "apply", "-auto-approve", "-var-file=variables.tfvars"],
            capture_output=True,
            text=True
        )

        # Vérifiez si l'erreur "plugin crashed" apparaît dans la sortie
        if "Error: The terraform-provider-proxmox_v2.9.11.exe plugin crashed!" in result.stderr:
            print("Terraform plugin crash detected, proceeding with conf_vm...")
            # Appeler la fonction conf_vm ici
            time.sleep(120)

        print("VM created successfully")
        return jsonify({
            "message": f"VM {vm_id} created successfully",
            "ip": "IP_TO_BE_DETERMINED"  # Vous devrez implémenter cette partie
        }), 200

    except subprocess.CalledProcessError as e:
        print(f"Subprocess error: {str(e)}")
        return jsonify({"error": f"Terraform execution failed: {str(e)}"}), 500
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
 #################################################################################################################################
 # #################################################################################################################################   
@app.route('/get_vmip', methods=['POST'])
def get_vmip():
    data = request.json
    proxmox_ip = data.get('proxmoxIp')
    password = data.get('password')
    vm_id = data.get('vm_id')

    if not all([proxmox_ip, password, vm_id]):
        return jsonify({"error": "Missing required fields"}), 400

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(proxmox_ip, username='root', password=password, timeout=15)

        # Vérification du statut de la VM
        status_cmd = f"qm status {vm_id}"
        stdin, stdout, stderr = ssh.exec_command(status_cmd)
        if "running" not in stdout.read().decode().lower():
            return jsonify({"error": "VM is not running"}), 400

        # Exécution de la commande IP
        ip_command = f"qm guest exec {vm_id} -- ip a"
        stdin, stdout, stderr = ssh.exec_command(ip_command)
        raw_output = stdout.read().decode().strip()
        error_output = stderr.read().decode()

        if error_output:
            return jsonify({"error": f"Command failed: {error_output}"}), 500

        if not raw_output:
            return jsonify({"error": "Empty response from command"}), 500

        # Extraction de l'IP
        ip_address = extract_ip_from_output(raw_output)
        if not ip_address:
            return jsonify({"error": "No valid IP address found"}), 500

        return jsonify({
            "message": "IP retrieved successfully",
            "ip": f"inet {ip_address}"
        })

    except paramiko.ssh_exception.AuthenticationException:
        return jsonify({"error": "SSH authentication failed"}), 401
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    finally:
        ssh.close()

def extract_ip_from_output(raw_output):
    """Extrait l'IP de la sortie brute"""
    try:
        import re
        # Recherche toutes les IPs non loopback
        ip_matches = re.findall(r'inet (192\.168\.[0-9]+\.[0-9]+)', raw_output)
        for ip in ip_matches:
            if ip != '127.0.0.1':
                return ip
        return None
    except Exception as e:
        print(f"IP extraction error: {str(e)}")
        return None
#################################################################################################################################
#Cluster Proxmox et configuration géneration des fichiers ansible
#####################################################################################################
logging.basicConfig(filename='hadoop_deploy.log', level=logging.INFO)
logger = logging.getLogger(__name__)

def log_step(message):
    logger.info(f"[{datetime.now()}] {message}")
    print(message)

# ==================== CONSTANTES ====================
@app.route('/clustercreate_vmprox', methods=['POST'])
def clustercreate_vmprox():
        data = request.get_json()
        print(f"Starting cluster creation: {data['cluster_name']}")
        
        # Validation des données
        required = ['proxmox_ip', 'password', 'target_node', 'vm_id_start',
                   'template', 'cluster_name', 'node_count']
        if not all(field in data for field in required):
            return jsonify({"error": "Missing required fields"}), 400

        vm_id = int(data['vm_id_start'])
        results = []
        ip_map = {}
        errors = []

        # 1ère BOUCLE: Création de toutes les machines
        print("=== PHASE 1: Création des VMs ===")
        vm_ids = []
        for i in range(data['node_count'] + 1):  # +1 pour l'ansible
            is_ansible = (i == data['node_count'])
            vm_type = "ansible" if is_ansible else "namenode" if i == 0 else "datanode"
            hostname = f"{data['cluster_name']}-{vm_type}-{i}" if not is_ansible else f"ansible-{data['cluster_name']}"
            current_vm_id = str(vm_id + i)
            vm_ids.append(current_vm_id)
            
            try:
                create_data = {
                    "proxmoxIp": data['proxmox_ip'],
                    "password": data['password'],
                    "hostname": hostname,
                    "targetNode": data['target_node'],
                    "vm_id": current_vm_id,
                    "template": data['template'],
                    "network": data.get('network_type', 'nat'),
                    "vm_type": vm_type
                }
                
                create_response = create_vmprox_direct(create_data)
                
                if create_response[1] != 200:
                    error_msg = create_response[0].get_json().get('error', '')
                    if "plugin crashed" in error_msg:
                        print(f"[VM {current_vm_id}] Warning: Terraform plugin crashed but continuing")
                        results.append({
                            "vm_id": current_vm_id,
                            "type": vm_type,
                            "status": "created_with_warning",
                            "warning": "Terraform plugin crashed"
                        })
                    else:
                        raise Exception(f"Creation failed: {error_msg}")
                else:
                    print(f"[VM {current_vm_id}] Successfully created")
                    results.append({
                        "vm_id": current_vm_id,
                        "type": vm_type,
                        "status": "created"
                    })

            except Exception as e:
                error_msg = f"[VM {current_vm_id}] Creation error: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                results.append({
                    "vm_id": current_vm_id,
                    "type": vm_type,
                    "status": "failed",
                    "error": str(e)
                })

        # 2ème BOUCLE: Démarrage des machines et attente
        print("\n=== PHASE 2: Démarrage des VMs ===")
        for vm in results:
            if vm['status'] not in ['created', 'created_with_warning']:
                continue
                
            current_vm_id = vm['vm_id']
            try:
                print(f"[VM {current_vm_id}] Starting...")
                start_response = start_vmprox_direct({
                    "proxmox_ip": data['proxmox_ip'],
                    "username": "root",
                    "password": data['password'],
                    "vm_id": current_vm_id
                })
                
                if start_response[1] != 200:
                    raise Exception(f"Start failed: {start_response[0].get_json()}")
                
                print(f"[VM {current_vm_id}] Waiting 90 seconds...")
                time.sleep(90)  # Attente fixe pour toutes les VMs
                vm['status'] = "started"

            except Exception as e:
                error_msg = f"[VM {current_vm_id}] Start error: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                vm['status'] = "start_failed"
                vm['error'] = str(e)

        # 3ème BOUCLE: Récupération des IPs
        ansible_ip = None
        namenode_ip = None
        datanode_ips = []
        retry_attempts = 10  # Nombre de tentatives
        retry_delay = 30    # Délai d'attente entre les tentatives en secondes

        for vm in results:
            if vm['status'] != 'started':
                continue
                
            current_vm_id = vm['vm_id']
            vm_type = vm['type']
            
            for attempt in range(retry_attempts):
                try:
                    print(f"[VM {current_vm_id}] Tentative {attempt + 1}/{retry_attempts} pour obtenir l'IP... (Type: {vm_type})")
                    ip_data, status_code = get_vmip_direct({
                        "proxmoxIp": data['proxmox_ip'],
                        "password": data['password'],
                        "vm_id": current_vm_id
                    })
                    
                    if status_code != 200:
                        raise Exception(f"Erreur: {ip_data.get('error', 'Inconnue')}")
                    
                    vm_ip = ip_data['ip'] if isinstance(ip_data, dict) else ip_data
                    vm_ip = vm_ip.strip().replace("inet ", "")
                    vm['ip'] = vm_ip
                    
                    # Log spécifique pour le nœud Ansible
                    if vm_type == "ansible":
                        ansible_ip = vm_ip
                        print(f"!!! NŒUD ANSIBLE TROUVÉ !!! IP: {ansible_ip} (VM ID: {current_vm_id})")
                    elif vm_type == "namenode":
                        namenode_ip = vm_ip
                    elif vm_type == "datanode":
                        datanode_ips.append(vm_ip)

                    if vm_type not in ip_map:
                        ip_map[vm_type] = []
                    ip_map[vm_type].append(vm_ip)
                    
                    print(f"[VM {current_vm_id}] IP attribuée: {vm_ip}")
                    break  # Sortir de la boucle si l'IP a été récupérée avec succès

                except Exception as e:
                    error_msg = f"[VM {current_vm_id}] Erreur IP: {str(e)}"
                    print(error_msg)
                    errors.append(error_msg)
                    vm['status'] = "ip_failed"
                    vm['error'] = str(e)

                    if attempt < retry_attempts - 1:
                        print(f"Aucune IP obtenue, attente de {retry_delay} secondes avant de réessayer...")
                        time.sleep(retry_delay)  # Attendre avant de réessayer

        # Vérification finale des IPs
        if not ansible_ip:
            raise Exception("ERREUR CRITIQUE: Aucune IP trouvée pour le nœud Ansible")

        print(f"""
        === VÉRIFICATION IP ===
        IP Ansible: {ansible_ip}
        IP NameNode: {ip_map.get('namenode', ['N/A'])[0]}
        IP DataNodes: {', '.join(ip_map.get('datanode', []))}
        """)

        # Vérification des IPs récupérées
        if not ansible_ip or not namenode_ip or len(datanode_ips) < 2:
            raise Exception("ERREUR CRITIQUE: Aucune IP trouvée pour le nœud Ansible ou NameNode/Datanodes manquants.")

        # 4ème PHASE: Configuration Ansible et installation Hadoop
        def execute_ssh_command(ssh, command):
            """Exécute une commande SSH et retourne le résultat"""
            stdin, stdout, stderr = ssh.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            return exit_status, output, error

        def create_ssh_client(host):
            """Crée une connexion SSH"""
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(
                    host, 
                    username="molka", 
                    password="molka",
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=30
                )
                return ssh
            except Exception as e:
                print(f"Échec de connexion SSH à {host}: {str(e)}")
                return None

        # Installe Hadoop sur le nœud contrôleur.
        try:
            # Créer une connexion SSH vers le contrôleur Ansible
            ssh = create_ssh_client(ansible_ip)
            if not ssh:
                print("Échec de la connexion SSH.")
                return False

            # Télécharger Hadoop
            commands = [
                'sudo apt update && sudo apt install -y wget openjdk-11-jdk net-tools sshpass pdsh',
                'sudo apt install -y python3 python3-pip',
                'sudo apt install -y ansible',
                
                'mkdir -p ~/.ssh',
                '[ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa',
                f'ssh-keyscan -H {ansible_ip} >> ~/.ssh/known_hosts',
                f'ssh-keyscan -H {namenode_ip} >> ~/.ssh/known_hosts',
                f'ssh-keyscan -H {datanode_ips } >> ~/.ssh/known_hosts',

                f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{ansible_ip}',
                f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{namenode_ip}',
                f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{datanode_ips[0]}',
                f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{datanode_ips[1]}',

                'chmod 600 ~/.ssh/id_rsa',
                'chmod 644 ~/.ssh/id_rsa.pub',
                'chmod 700 ~/.ssh',
                
                'wget https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz',
                'sudo mv hadoop-3.3.1.tar.gz /opt',
                'sudo chown -R molka:molka /opt',

                'echo "export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64" >> /home/molka/.bashrc',
                'echo "export HADOOP_HOME=/opt/hadoop" >> /home/molka/.bashrc',
                'echo "export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin" >> /home/molka/.bashrc',
                # Copie du .bashrc sur les différents nœuds
                f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{ansible_ip}:/home/molka/.bashrc',
                f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{namenode_ip}:/home/molka/.bashrc',
                f'for datanode in {" ".join(datanode_ips)}; do sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@${{datanode}}:/home/molka/.bashrc; done',


                'mkdir -p ~/templates',
                'echo "<configuration>\n  <property>\n    <name>fs.defaultFS</name>\n    <value>hdfs://{{ namenode_hostname }}:9000</value>\n  </property>\n</configuration>" > ~/templates/core-site.xml.j2',
                'echo "<configuration>\n  <property>\n    <name>dfs.replication</name>\n    <value>2</value>\n  </property>\n</configuration>" > ~/templates/hdfs-site.xml.j2',
                'echo "<configuration>\n  <property>\n    <name>yarn.resourcemanager.hostname</name>\n    <value>{{ namenode_hostname }}</value>\n  </property>\n</configuration>" > ~/templates/yarn-site.xml.j2',
                'echo "<configuration>\n  <property>\n    <name>mapreduce.framework.name</name>\n    <value>yarn</value>\n  </property>\n</configuration>" > ~/templates/mapred-site.xml.j2',
                'echo "{{ groups[\'namenode\'][0] }}" > ~/templates/masters.j2',
                'echo "{% for worker in groups[\'datanodes\'] %}\n{{ worker }}\n{% endfor %}" > ~/templates/workers.j2',
                'echo "# ANSIBLE GENERATED CLUSTER HOSTS\n{% for host in groups[\'all\'] %}\n{{ hostvars[host][\'ansible_host\'] }} {{ host }}\n{% endfor %}" > ~/templates/hosts.j2',
                f'echo "[namenode]\n{namenode_ip} ansible_host={namenode_ip}\n\n[datanodes]\n{datanode_ips[0]} ansible_host={datanode_ips[0]}\n{datanode_ips[1]} ansible_host={datanode_ips[1]}\n\n[all:vars]\nansible_user=molka\nansible_ssh_private_key_file=~/.ssh/id_rsa\nansible_ssh_common_args=\'-o StrictHostKeyChecking=no\'\nansible_python_interpreter=/usr/bin/python3" > ~/inventory.ini',
                f'echo """[namenode]\n{namenode_ip} ansible_host={namenode_ip}\n\n[datanodes]\n{datanode_ips[0]} ansible_host={datanode_ips[0]}\n{datanode_ips[1]} ansible_host={datanode_ips[1]}\n\n[resource_manager]\n{namenode_ip} ansible_host={namenode_ip}\n\n[all:vars]\nansible_user=molka\nansible_ssh_private_key_file=~/.ssh/id_rsa\nansible_ssh_common_args=\'-o StrictHostKeyChecking=no\'\nansible_python_interpreter=/usr/bin/python3""" > ~/inventory.ini'
            ]
            for command in commands:
                exit_status, output, error = execute_ssh_command(ssh, command)
                if exit_status != 0:
                    print(f"Erreur lors de l'exécution de: {command}\n{error}")
                    ssh.close()
                    return False  # Arrêter dès qu'une commande échoue
                    
            # Définir les playbooks avec une syntaxe YAML correcte
            playbooks = {
                'deploy_hadoop.yml': """---
- name: Déploiement Hadoop via extraction
  hosts: all
  become: yes
  gather_facts: no

  tasks:
    # 1. Créer /opt si nécessaire
    - name: Créer répertoire /opt
      file:
        path: /opt
        state: directory
        owner: root
        group: root
        mode: '0755'

    # 2. Installer les dépendances
    - name: Installer paquets requis
      apt:
        name:
          - openjdk-11-jdk
          - sshpass
          - net-tools
          - pdsh
          - rsync
          - tar
        state: present
        update_cache: yes

    - name: Transférer Hadoop via SCP
      command: >
        scp -r -i /home/molka/.ssh/id_rsa
        -o StrictHostKeyChecking=no
        -o UserKnownHostsFile=/dev/null
        /opt/hadoop-3.3.1.tar.gz 
        molka@{{ inventory_hostname }}:/tmp/
      delegate_to: localhost

    - name: Déplacer l'archive
      become: yes
      shell: |
        mv /tmp/hadoop-3.3.1.tar.gz /opt/
        chown molka:molka /opt/hadoop-3.3.1.tar.gz

    - name: Créer le répertoire Hadoop
      file:
        path: /opt/hadoop
        state: directory
        owner: molka
        group: molka
        mode: '0755'

    - name: S'assurer que .bashrc appartient à molka
      file:
        path: /home/molka/.bashrc
        owner: molka
        group: molka
        mode: '644'
      ignore_errors: yes  # Ignore si le fichier n'existe pas encore

    - name: Extraire Hadoop sur chaque nœud
      become: yes
      shell: |
        tar xzf /opt/hadoop-3.3.1.tar.gz -C /opt/hadoop --strip-components=1 || (echo "Échec extraction" && exit 1)
        chown -R molka:molka /opt/hadoop
        rm -f /opt/hadoop-3.3.1.tar.gz
      args:
        executable: /bin/bash
      register: extraction
      retries: 3
      delay: 10
      until: extraction.rc == 0

    - name: Configurer les variables d'environnement
      blockinfile:
        path: /home/molka/.bashrc
        block: |
          export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
          export HADOOP_HOME=/opt/hadoop
          export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin
        marker: "# {mark} HADOOP CONFIG"
        owner: molka
        group: molka
      notify: Reload bashrc

    - debug:
        var: hadoop_check.stdout_lines

  handlers:
    - name: Reload bashrc
      shell: "bash -lc 'source ~/.bashrc'"
      args:
        executable: /bin/bash
""",
                'hadoop_config.yml': """---
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
""",
                'hadoop_start.yml': """---
- name: Configurer SSH sans mot de passe entre nœuds
  hosts: all
  become: yes
  tasks:
    - name: Installer sshpass
      apt:
        name: sshpass
        state: present

    - name: Générer une clé SSH si inexistante
      become_user: molka
      shell: |
        [ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa
      args:
        executable: /bin/bash

    - name: Distribuer la clé publique
      become_user: molka
      shell:
            shell: |
        sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no molka@{{ item }}
      with_items: "{{ groups['all'] }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['namenode'][0]

- name: Démarrer les services Hadoop
  hosts: namenode
  become: yes
  tasks:
    - name: Mettre à jour hadoop-env.sh pour définir JAVA_HOME
      shell: |
        if grep -q '^export JAVA_HOME=' /opt/hadoop/etc/hadoop/hadoop-env.sh; then
          sed -i 's|^export JAVA_HOME=.*|export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64|' /opt/hadoop/etc/hadoop/hadoop-env.sh;
        else
          echo 'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64' >> /opt/hadoop/etc/hadoop/hadoop-env.sh;
        fi
      args:
        executable: /bin/bash

    - name: Créer le répertoire /opt/hadoop/logs si nécessaire
      file:
        path: /opt/hadoop/logs
        state: directory
        owner: molka
        group: molka
        mode: '0755'

    - name: Formater le NameNode (si nécessaire)
      become: yes
      become_user: molka
      shell: "/opt/hadoop/bin/hdfs namenode -format -force"
      args:
        creates: /opt/hadoop/hdfs/name/current/VERSION
        executable: /bin/bash
      environment:
        JAVA_HOME: /usr/lib/jvm/java-11-openjdk-amd64

    - name: Démarrer HDFS
      become: yes
      become_user: molka
      shell: |
        export PDSH_RCMD_TYPE=ssh
        /opt/hadoop/sbin/start-dfs.sh
      args:
        executable: /bin/bash
      environment:
        JAVA_HOME: /usr/lib/jvm/java-11-openjdk-amd64
        HADOOP_SSH_OPTS: "-o StrictHostKeyChecking=no"
        HDFS_NAMENODE_USER: molka
        HDFS_DATANODE_USER: molka
        HDFS_SECONDARYNAMENODE_USER: molka

- name: Démarrer le ResourceManager sur le NameNode
  hosts: namenode
  become: yes
  tasks:
    - name: Démarrer le ResourceManager
      become_user: molka
      shell: "/opt/hadoop/sbin/yarn-daemon.sh start resourcemanager"
      args:
        executable: /bin/bash
      environment:
        JAVA_HOME: /usr/lib/jvm/java-11-openjdk-amd64
      register: start_rm

    - name: Vérifier le démarrage des services Hadoop (jps)
      become: yes
      become_user: molka
      shell: "jps"
      args:
        executable: /bin/bash
      register: jps_output

- name: Démarrer les DataNodes manuellement
  hosts: datanodes
  become: yes
  tasks:
    - name: Démarrer DataNode
      become_user: molka
      shell: "/opt/hadoop/bin/hdfs --daemon start datanode"
      args:
        executable: /bin/bash
      environment:
        JAVA_HOME: /usr/lib/jvm/java-11-openjdk-amd64

    - name: Vérifier les DataNodes
      become_user: molka
      shell: "jps"
      register: datanode_jps

    - name: Afficher les processus Hadoop
      debug:
        var: datanode_jps.stdout
"""
            }

            # Écrire les playbooks
            for filename, content in playbooks.items():
                # Échapper les caractères spéciaux pour la commande echo
                escaped_content = content.replace('"', '\\"').replace('$', '\\$')
                cmd = f'cat > ~/{filename} <<EOF\n{escaped_content}\nEOF'
                exit_status, output, error = execute_ssh_command(ssh, cmd)
                if exit_status != 0:
                    print(f"Erreur création {filename}: {error}")
                    return False

            # Exécuter les playbooks Ansible
            for filename in playbooks.keys():
                cmd = f'ansible-playbook -i ~/inventory.ini ~/{filename}'
                exit_status, output, error = execute_ssh_command(ssh, cmd)
                if exit_status != 0:
                    print(f"Erreur exécution {filename}: {error}")
                    return False

            return jsonify({
                "status": "success",
                "vms": results,
                "ip_map": ip_map,
                "errors": errors
            })

        except Exception as e:
            log_step(f"ERREUR FATALE: {str(e)}")
            return jsonify({
                "status": "error",
                "error": str(e),
                "cluster_name": data.get('cluster_name', 'unknown')
            }), 500

#####################################################################################################
#####################################################################################################
#####################################################################################################
#####################################################################################################
#####################################################################################################
# Fonctions utilitaires (à adapter selon votre implémentation)
def create_vmprox_direct(data):
    with app.test_request_context('/create_vmprox', method='POST', json=data):
        return create_vmprox()

def start_vmprox_direct(data):
    with app.test_request_context('/start_vmprox', method='POST', json=data):
        return start_vmprox()

def get_vmip_direct(data):
    """Nouvelle version simplifiée"""
    with app.test_request_context('/get_vmip', method='POST', json=data):
        response = get_vmip()
        return response.get_json(), response.status_code

#####################################################################################################
##################################################################################################
import logging
from datetime import datetime
from flask import jsonify, request
import paramiko

# Configuration du logging
logging.basicConfig(filename='hadoop_deploy.log', level=logging.INFO)
logger = logging.getLogger(__name__)

def log_step(message):
    logger.info(f"[{datetime.now()}] {message}")
    print(message)

def execute_ssh_command(ssh, command):
    """Exécute une commande SSH et retourne le résultat"""
    stdin, stdout, stderr = ssh.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode().strip()
    error = stderr.read().decode().strip()
    return exit_status, output, error

def create_ssh_client(host):
    """Crée une connexion SSH"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            host, 
            username="molka", 
            password="molka",
            look_for_keys=False,
            allow_agent=False,
            timeout=30
        )
        return ssh
    except Exception as e:
        print(f"Échec de connexion SSH à {host}: {str(e)}")
        return None

@app.route('/clusterha_vmprox', methods=['POST'])
def clusterha_vmprox():
    data = request.get_json()
    print(f"Starting HA cluster creation: {data['cluster_name']}")
    
    # Validation des données
    required = ['proxmox_ip', 'password', 'target_node', 'vm_id_start',
                'template', 'cluster_name', 'node_count']
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    vm_id = int(data['vm_id_start'])
    results = []
    ip_map = {}
    errors = []

    # 1ère BOUCLE: Création de toutes les machines
    print("=== PHASE 1: Création des VMs ===")
    vm_ids = []
    for i in range(data['node_count'] + 2):  # +2 pour l'ansible et le standby
        if i == data['node_count']:
            vm_type = "ansible"  # Ansible Controller
        elif i == data['node_count'] + 1:
            vm_type = "standby"  # Standby Node
        else:
            vm_type = "namenode" if i == 0 else "datanode"  # NameNode ou DataNode
        
        hostname = f"{data['cluster_name']}-{vm_type}-{i}" if vm_type != "ansible" else f"ansible-{data['cluster_name']}"
        current_vm_id = str(vm_id + i)
        vm_ids.append(current_vm_id)
        
        try:
            create_data = {
                "proxmoxIp": data['proxmox_ip'],
                "password": data['password'],
                "hostname": hostname,
                "targetNode": data['target_node'],
                "vm_id": current_vm_id,
                "template": data['template'],
                "network": data.get('network_type', 'nat'),
                "vm_type": vm_type
            }
            
            create_response = create_vmprox_direct(create_data)
            
            if create_response[1] != 200:
                error_msg = create_response[0].get_json().get('error', '')
                if "plugin crashed" in error_msg:
                    print(f"[VM {current_vm_id}] Warning: Terraform plugin crashed but continuing")
                    results.append({
                        "vm_id": current_vm_id,
                        "type": vm_type,
                        "status": "created_with_warning",
                        "warning": "Terraform plugin crashed"
                    })
                else:
                    raise Exception(f"Creation failed: {error_msg}")
            else:
                print(f"[VM {current_vm_id}] Successfully created")
                results.append({
                    "vm_id": current_vm_id,
                    "type": vm_type,
                    "status": "created"
                })

        except Exception as e:
            error_msg = f"[VM {current_vm_id}] Creation error: {str(e)}"
            print(error_msg)
            errors.append(error_msg)
            results.append({
                "vm_id": current_vm_id,
                "type": vm_type,
                "status": "failed",
                "error": str(e)
            })

    # 2ème BOUCLE: Démarrage des machines et attente
    print("\n=== PHASE 2: Démarrage des VMs ===")
    for vm in results:
        if vm['status'] not in ['created', 'created_with_warning']:
            continue
            
        current_vm_id = vm['vm_id']
        try:
            print(f"[VM {current_vm_id}] Starting...")
            start_response = start_vmprox_direct({
                "proxmox_ip": data['proxmox_ip'],
                "username": "root",
                "password": data['password'],
                "vm_id": current_vm_id
            })
            
            if start_response[1] != 200:
                raise Exception(f"Start failed: {start_response[0].get_json()}")
            
            print(f"[VM {current_vm_id}] Waiting 90 seconds...")
            time.sleep(90)  # Attente fixe pour toutes les VMs
            vm['status'] = "started"

        except Exception as e:
            error_msg = f"[VM {current_vm_id}] Start error: {str(e)}"
            print(error_msg)
            errors.append(error_msg)
            vm['status'] = "start_failed"
            vm['error'] = str(e)

    # 3ème BOUCLE: Récupération des IPs
    ansible_ip = None
    namenode_ip = None
    standby_ip = None
    datanode_ips = []
    retry_attempts = 10  # Nombre de tentatives
    retry_delay = 30    # Délai d'attente entre les tentatives en secondes

    for vm in results:
        if vm['status'] != 'started':
            continue
            
        current_vm_id = vm['vm_id']
        vm_type = vm['type']
        
        for attempt in range(retry_attempts):
            try:
                print(f"[VM {current_vm_id}] Tentative {attempt + 1}/{retry_attempts} pour obtenir l'IP... (Type: {vm_type})")
                ip_data, status_code = get_vmip_direct({
                    "proxmoxIp": data['proxmox_ip'],
                    "password": data['password'],
                    "vm_id": current_vm_id
                })
                
                if status_code != 200:
                    raise Exception(f"Erreur: {ip_data.get('error', 'Inconnue')}")
                
                vm_ip = ip_data['ip'] if isinstance(ip_data, dict) else ip_data
                vm_ip = vm_ip.strip().replace("inet ", "")
                vm['ip'] = vm_ip
                
                # Log spécifique pour le nœud Ansible
                if vm_type == "ansible":
                    ansible_ip = vm_ip
                    print(f"!!! NŒUD ANSIBLE TROUVÉ !!! IP: {ansible_ip} (VM ID: {current_vm_id})")
                elif vm_type == "namenode":
                    namenode_ip = vm_ip
                elif vm_type == "standby":
                    standby_ip = vm_ip
                elif vm_type == "datanode":
                    datanode_ips.append(vm_ip)

                if vm_type not in ip_map:
                    ip_map[vm_type] = []
                ip_map[vm_type].append(vm_ip)
                
                print(f"[VM {current_vm_id}] IP attribuée: {vm_ip}")
                break  # Sortir de la boucle si l'IP a été récupérée avec succès

            except Exception as e:
                error_msg = f"[VM {current_vm_id}] Erreur IP: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                vm['status'] = "ip_failed"
                vm['error'] = str(e)

                if attempt < retry_attempts - 1:
                    print(f"Aucune IP obtenue, attente de {retry_delay} secondes avant de réessayer...")
                    time.sleep(retry_delay)  # Attendre avant de réessayer

    # Vérification finale des IPs
    if not ansible_ip:
        raise Exception("ERREUR CRITIQUE: Aucune IP trouvée pour le nœud Ansible")

    print(f"""
    === VÉRIFICATION IP ===
    IP Ansible: {ansible_ip}
    IP NameNode: {namenode_ip}
    IP Standby: {standby_ip}
    IP DataNodes: {', '.join(datanode_ips)}
    """)

    # Vérification des IPs récupérées
    if not ansible_ip or not namenode_ip or not standby_ip or len(datanode_ips) < 2:
        raise Exception("ERREUR CRITIQUE: Aucune IP trouvée pour le nœud Ansible ou NameNode/Datanodes manquants.")

    # 4ème PHASE: Configuration Ansible et installation Hadoop
    try:
        # Créer une connexion SSH vers le contrôleur Ansible
        ssh = create_ssh_client(ansible_ip)
        if not ssh:
            print("Échec de la connexion SSH.")
            return False

        # Télécharger Hadoop et configurer
        commands = [
            'sudo apt update && sudo apt install -y wget openjdk-11-jdk net-tools sshpass pdsh',
            'sudo apt install -y python3 python3-pip',
            'sudo apt install -y ansible',

            #########################################jareb
            'mkdir -p ~/.ssh',
            '[ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa',
            f'ssh-keyscan -H {ansible_ip} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {namenode_ip} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {standby_ip} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {datanode_ips } >> ~/.ssh/known_hosts',
        ]
        # Ajout des commandes pour copier la clé SSH sur chaque datanode
        for ip in datanode_ips:
            commands.append(f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{ip}')

        # Ajout des commandes pour copier la clé SSH sur d'autres hôtes
        commands.extend([
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{ansible_ip}',
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{namenode_ip}',
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{standby_ip}',

            'chmod 600 ~/.ssh/id_rsa',
            'chmod 644 ~/.ssh/id_rsa.pub',
            'chmod 700 ~/.ssh',
################################################################################################################################
#ZOOKEEPER
#################################################################################################################################
           'wget https://archive.apache.org/dist/zookeeper/zookeeper-3.6.3/apache-zookeeper-3.6.3-bin.tar.gz',
           'sudo mv apache-zookeeper-3.6.3-bin.tar.gz /tmp',

           # Copier vers Namenode et Standby
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{namenode_ip}:/tmp/',
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{standby_ip}:/tmp/',
            # Copier vers seulement le premier datanode (pour avoir 3 nœuds ZooKeeper)
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{datanode_ips[0]}:/tmp/',

            # Créer /etc/zookeeper et déplacer le fichier
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',

            # Extraire Zookeeper
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',

            # Renommer zoo_sample.cfg en zoo.cfg
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',

            # Créer d'abord le dossier puis écrire l'ID
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /var/lib/zookeeper && echo 1 | sudo tee /var/lib/zookeeper/myid"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /var/lib/zookeeper && echo 2 | sudo tee /var/lib/zookeeper/myid"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /var/lib/zookeeper && echo 3 | sudo tee /var/lib/zookeeper/myid"',

            # 📂 Ajouter la création des dossiers logs avec bonne permission
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /etc/zookeeper/logs /var/lib/zookeeper /var/log/zookeeper && sudo chown -R molka:molka /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && sudo chmod -R 755 /etc/zookeeper"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /etc/zookeeper/logs /var/lib/zookeeper /var/log/zookeeper && sudo chown -R molka:molka /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && sudo chmod -R 755 /etc/zookeeper"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /etc/zookeeper/logs /var/lib/zookeeper /var/log/zookeeper && sudo chown -R molka:molka /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && sudo chmod -R 755 /etc/zookeeper"',
        
################################################################################################################################
#HADOOP
#################################################################################################################################
            'wget https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz',
            'sudo mv hadoop-3.3.1.tar.gz /tmp',
            'sudo chown -R molka:molka /opt',
            # Copier vers Namenode et Standby
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/hadoop-3.3.1.tar.gz molka@{namenode_ip}:/tmp/',
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/hadoop-3.3.1.tar.gz molka@{standby_ip}:/tmp/',
            f'for datanode in {" ".join(datanode_ips)}; do sshpass -p "molka" scp -o StrictHostKeyChecking=no /tmp/hadoop-3.3.1.tar.gz molka@${{datanode}}:/tmp/; done',

            # Créer /opt/hadoop et déplacer le fichier
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /opt/hadoop && sudo mv /tmp/hadoop-3.3.1.tar.gz /opt/hadoop/"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /opt/hadoop && sudo mv /tmp/hadoop-3.3.1.tar.gz /opt/hadoop/"',
            f'for datanode in {" ".join(datanode_ips)}; do ssh -o StrictHostKeyChecking=no molka@${{datanode}} "sudo mkdir -p /opt/hadoop && sudo mv /tmp/hadoop-3.3.1.tar.gz /opt/hadoop/"; done',

            # Extraire hadoop
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "cd /opt/hadoop && sudo tar xzf hadoop-3.3.1.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "cd /opt/hadoop && sudo tar xzf hadoop-3.3.1.tar.gz --strip-components=1"',
            f'for datanode in {" ".join(datanode_ips)}; do ssh -o StrictHostKeyChecking=no molka@${{datanode}} "cd /opt/hadoop && sudo tar xzf hadoop-3.3.1.tar.gz --strip-components=1"; done',



################################################################################################################################
#BASHRC
#################################################################################################################################
            # modification ."bashrc
          ############################################
            'echo "export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64" >> /home/molka/.bashrc',
            'echo "export HADOOP_HOME=/opt/hadoop" >> /home/molka/.bashrc',
            'echo "export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin" >> /home/molka/.bashrc',

            # Copie du .bashrc sur les différents nœuds
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{ansible_ip}:/home/molka/.bashrc',
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{namenode_ip}:/home/molka/.bashrc',
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{standby_ip}:/home/molka/.bashrc',
            f'for datanode in {" ".join(datanode_ips)}; do sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@${{datanode}}:/home/molka/.bashrc; done',
             
              # Recharger le .bashrc pour que les changements prennent effet immédiatement (source)
            f'ssh -o StrictHostKeyChecking=no molka@{ansible_ip} "source /home/molka/.bashrc"',
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "source /home/molka/.bashrc"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "source /home/molka/.bashrc"',
            f'for datanode in {" ".join(datanode_ips)}; do ssh -o StrictHostKeyChecking=no molka@${{datanode}} "source /home/molka/.bashrc"; done',
          
################################################################################################################################
#################################################################################################################################

            # 📂 Créer le dossier "templates" pour Ansible
            'mkdir -p ~/templates',
            # 📝 Ajouter les fichiers de configuration Hadoop
            # core-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>fs.defaultFS</name>\n        <value>hdfs://ha-cluster</value>\n    </property>\n    <property>\n        <name>dfs.client.failover.proxy.provider.ha-cluster</name>\n        <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>\n    </property>\n    <property>\n        <name>ha.zookeeper.quorum</name>\n        <value>{% for zk in groups[\'zookeeper\'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>\n    </property>\n    <property>\n        <name>dfs.permissions.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>ipc.client.connect.max.retries</name>\n        <value>3</value>\n    </property>\n</configuration>" > ~/templates/core-site.xml.j2',
            
            # hdfs-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>dfs.replication</name>\n        <value>2</value>\n    </property>\n    <property>\n        <name>dfs.nameservices</name>\n        <value>ha-cluster</value>\n    </property>\n    <property>\n        <name>dfs.ha.namenodes.ha-cluster</name>\n        <value>{{ groups[\'namenode\'][0] }},{{ groups[\'standby\'][0] }}</value>\n    </property>\n    <property>\n        <name>dfs.namenode.rpc-address.ha-cluster.{{ groups[\'namenode\'][0] }}</name>\n        <value>{{ hostvars[groups[\'namenode\'][0]].ansible_host }}:8020</value>\n    </property>\n    <property>\n        <name>dfs.namenode.rpc-address.ha-cluster.{{ groups[\'standby\'][0] }}</name>\n        <value>{{ hostvars[groups[\'standby\'][0]].ansible_host }}:8020</value>\n    </property>\n    <property>\n        <name>dfs.namenode.http-address.ha-cluster.{{ groups[\'namenode\'][0] }}</name>\n        <value>{{ hostvars[groups[\'namenode\'][0]].ansible_host }}:50070</value>\n    </property>\n    <property>\n        <name>dfs.namenode.http-address.ha-cluster.{{ groups[\'standby\'][0] }}</name>\n        <value>{{ hostvars[groups[\'standby\'][0]].ansible_host }}:50070</value>\n    </property>\n    <property>\n        <name>dfs.namenode.shared.edits.dir</name>\n        <value>qjournal://{% for jn in groups[\'journalnode\'] %}{{ hostvars[jn].ansible_host }}:8485{% if not loop.last %};{% endif %}{% endfor %}/ha-cluster</value>\n    </property>\n    <property>\n        <name>dfs.ha.automatic-failover.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>dfs.client.failover.proxy.provider.ha-cluster</name>\n        <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>\n    </property>\n    <property>\n        <name>ha.zookeeper.quorum</name>\n        <value>{% for zk in groups[\'zookeeper\'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>\n    </property>\n    <property>\n        <name>dfs.namenode.name.dir</name>\n        <value>file:{{ hadoop_home }}/data/hdfs/namenode</value>\n    </property>\n    <property>\n        <name>dfs.datanode.data.dir</name>\n        <value>file:{{ hadoop_home }}/data/hdfs/datanode</value>\n    </property>\n    <property>\n        <name>dfs.namenode.checkpoint.dir</name>\n        <value>file:{{ hadoop_home }}/data/hdfs/namesecondary</value>\n    </property>\n    <property>\n        <name>dfs.ha.fencing.methods</name>\n        <value>shell(/bin/true)</value>\n    </property>\n    <property>\n        <name>dfs.ha.failover-controller.active-standby-elector.zk.op.retries</name>\n        <value>3</value>\n    </property>\n</configuration>" > ~/templates/hdfs-site.xml.j2',
            
            # yarn-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>yarn.resourcemanager.ha.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.cluster-id</name>\n        <value>yarn-cluster</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.ha.rm-ids</name>\n        <value>rm1,rm2</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.zk-address</name>\n        <value>{% for host in groups[\'zookeeper\'] %}{{ host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.hostname.rm1</name>\n        <value>{{ groups[\'resourcemanager\'][0] }}</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.hostname.rm2</name>\n        <value>{{ groups[\'resourcemanager_standby\'][0] }}</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.recovery.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.store.class</name>\n        <value>org.apache.hadoop.yarn.server.resourcemanager.recovery.ZKRMStateStore</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.webapp.address.rm1</name>\n        <value>{{ groups[\'resourcemanager\'][0] }}:8088</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.webapp.address.rm2</name>\n        <value>{{ groups[\'resourcemanager_standby\'][0] }}:8088</value>\n    </property>\n    <property>\n        <name>yarn.nodemanager.resource.memory-mb</name>\n        <value>4096</value>\n    </property>\n    <property>\n        <name>yarn.nodemanager.resource.cpu-vcores</name>\n        <value>4</value>\n    </property>\n</configuration>" > ~/templates/yarn-site.xml.j2',
            
            # mapred-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>mapreduce.framework.name</name>\n        <value>yarn</value>\n    </property>\n</configuration>" > ~/templates/mapred-site.xml.j2',

            # masters.j2
            'echo "{{ groups[\'namenode\'][0] }}" > ~/templates/masters.j2',

            # workers.j2
            'echo "{% for worker in groups[\'datanodes\'] %}{{ worker }}\n{% endfor %}" > ~/templates/workers.j2',

            # zoo.cfg.j2
            'echo "tickTime=2000\ninitLimit=10\nsyncLimit=5\ndataDir=/var/lib/zookeeper\ndataLogDir=/var/log/zookeeper\nclientPort=2181\n{% for zk in groups[\'zookeeper\'] %}server.{{ loop.index }}={{ hostvars[zk].ansible_host }}:2888:3888\n{% endfor %}" > ~/templates/zoo.cfg.j2',

            # hosts.j2
            'echo "# ANSIBLE GENERATED HOSTS FILE\n{% for host in groups[\'all\'] %}{{ hostvars[host].ansible_host }} {{ host }}\n{% endfor %}" > ~/templates/hosts.j2',
            
            # Créer le fichier inventory.ini
            f'echo """[namenode]\n{namenode_ip} ansible_host={namenode_ip}\n{standby_ip} ansible_host={standby_ip}\n\n[standby]\n{standby_ip} ansible_host={standby_ip}\n\n[datanodes]\n{"\n".join([f"{ip} ansible_host={ip}" for ip in datanode_ips])}\n\n[resourcemanager]\n{namenode_ip} ansible_host={namenode_ip}\n\n[resourcemanager_standby]\n{standby_ip} ansible_host={standby_ip}\n\n[zookeeper]\n{namenode_ip} ansible_host={namenode_ip}\n{standby_ip} ansible_host={standby_ip}\n{datanode_ips[0]} ansible_host={datanode_ips[0]}\n\n[journalnode]\n{namenode_ip} ansible_host={namenode_ip}\n{standby_ip} ansible_host={standby_ip}\n{datanode_ips[0]} ansible_host={datanode_ips[0]}\n\n[all:vars]\nansible_user=molka\nansible_ssh_private_key_file=~/.ssh/id_rsa\nansible_ssh_common_args=-o StrictHostKeyChecking=no\nansible_python_interpreter=/usr/bin/python3""" > ~/inventory.ini'        
            ])
        
        for idx, command in enumerate(commands, start=1):
            print(f"\n[Commande {idx}/{len(commands)}] Exécution : {command}")
            exit_status, output, error = execute_ssh_command(ssh, command)

            if exit_status == 0:
                print(f"✅ Commande réussie : {command}")
            else:
                print(f"❌ Erreur lors de l'exécution de la commande : {command}")
                print(f"Code de sortie : {exit_status}")
                print(f"Message d'erreur :\n{error.strip()}")
                ssh.close()
                return False  # Stop dès qu'une commande échoue        
        # Définir les playbooks avec une syntaxe YAML correcte
        playbooks = {
            'deploy_hadoop.yml': """---
- name: Déploiement Hadoop via extraction
  hosts: all
  become: yes
  gather_facts: no

  tasks:
    # 1. Créer /opt si nécessaire
    - name: Créer répertoire /opt
      file:
        path: /opt
        state: directory
        owner: root
        group: root
        mode: '0755'

    # 2. Installer les dépendances
    - name: Installer paquets requis
      apt:
        name:
          - openjdk-11-jdk
          - sshpass
          - net-tools
          - pdsh
          - rsync
          - tar
        state: present
        update_cache: yes

""",
          'hadoop_config.yml': """---
- name: Configurer les fichiers de configuration Hadoop et /etc/hosts
  hosts: all
  become: yes
  vars:
    namenode_hostname: "{{ groups['namenode'][0] }}"
    standby_hostname: "{{ groups['standby'][0] | default('default_standby_hostname') }}"
    hadoop_home: /opt/hadoop  # Ajout de la variable hadoop_home

  tasks:
    - name: Déployer core-site.xml
      template:
        src: /home/molka/templates/core-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/core-site.xml"

    - name: Déployer hdfs-site.xml
      template:
        src: /home/molka/templates/hdfs-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/hdfs-site.xml"

    - name: Déployer yarn-site.xml
      template:
        src: /home/molka/templates/yarn-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/yarn-site.xml"

    - name: Déployer mapred-site.xml
      template:
        src: /home/molka/templates/mapred-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/mapred-site.xml"

    - name: Déployer masters
      template:
        src: /home/molka/templates/masters.j2
        dest: "{{ hadoop_home }}/etc/hadoop/masters"

    - name: Déployer workers
      template:
        src: /home/molka/templates/workers.j2
        dest: "{{ hadoop_home }}/etc/hadoop/workers"

    - name: Déployer zoo.cfg pour ZooKeeper
      template:
        src: /home/molka/templates/zoo.cfg.j2
        dest: "/etc/zookeeper/conf/zoo.cfg"

    - name: Mettre à jour /etc/hosts avec les hôtes du cluster
      template:
        src: /home/molka/templates/hosts.j2
        dest: /etc/hosts
""",
            'hadoop_start.yml': """---
- name: Vérifier et démarrer ZooKeeper sur les nœuds ZooKeeper
  hosts: zookeeper
  become: yes
  vars:
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
    hadoop_home: "/opt/hadoop"
    zookeeper_home: "/etc/zookeeper"
  tasks:
    - name: Vérifier la configuration de ZooKeeper
      stat:
        path: "{{ zookeeper_home }}/conf/zoo.cfg"
      register: zoo_cfg_exists

    - name: Afficher le contenu de zoo.cfg
      shell: "cat {{ zookeeper_home }}/conf/zoo.cfg"
      register: zoo_cfg_content
      when: zoo_cfg_exists.stat.exists
      
    - name: Afficher le contenu de zoo.cfg
      debug:
        var: zoo_cfg_content.stdout_lines
      when: zoo_cfg_exists.stat.exists
    
    - name: Créer le répertoire /var/lib/zookeeper s'il n'existe pas
      file:
        path: /var/lib/zookeeper
        state: directory
        owner: molka
        group: molka
        mode: '0755'

    - name: Déplacer le fichier myid vers /var/lib/zookeeper
      command: mv /etc/zookeeper/myid /var/lib/zookeeper/myid
      args:
        removes: /etc/zookeeper/myid
      become_user: molka
      ignore_errors: yes

    - name: Stopper ZooKeeper si déjà en cours d'exécution
      shell: "{{ zookeeper_home }}/bin/zkServer.sh stop"
      become_user: molka
      environment:
        ZOO_LOG_DIR: "/var/log/zookeeper"
        ZOO_CONF_DIR: "{{ zookeeper_home }}/conf"
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes
      
    - name: Attendre que ZooKeeper s'arrête
      pause:
        seconds: 5
    
    - name: Démarrer ZooKeeper
      shell: "{{ zookeeper_home }}/bin/zkServer.sh start"
      become_user: molka
      environment:
        ZOO_LOG_DIR: "/var/log/zookeeper"
        ZOO_CONF_DIR: "{{ zookeeper_home }}/conf"
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      register: zk_status
      
    - name: Attendre le démarrage de ZooKeeper
      pause:
        seconds: 10
        
    - name: Vérifier le démarrage de ZooKeeper
      shell: "{{ zookeeper_home }}/bin/zkServer.sh status"
      become_user: molka
      environment:
        ZOO_LOG_DIR: "/var/log/zookeeper"
        ZOO_CONF_DIR: "{{ zookeeper_home }}/conf"
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      register: zk_status_check
      ignore_errors: yes
      
    - name: Afficher le statut de ZooKeeper
      debug:
        var: zk_status_check.stdout
        
    - name: Afficher les journaux ZooKeeper
      shell: "tail -n 30 /var/log/zookeeper/zookeeper.log"
      become_user: molka
      register: zk_logs
      ignore_errors: yes
      
    - name: Afficher les journaux de ZooKeeper
      debug:
        var: zk_logs.stdout_lines
    
    - name: Créer les répertoires de logs
      file:
        path: /opt/hadoop/logs
        state: directory
        owner: molka
        group: molka
        mode: 0755
    
    - name: Configurer hadoop-env.sh
      lineinfile:
        path: /opt/hadoop/etc/hadoop/hadoop-env.sh
        line: "export JAVA_HOME={{ java_home }}"
        state: present  
                                            
- name: Configuration des JournalNodes
  hosts: zookeeper
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Créer le répertoire JournalNode
      file:
        path: /opt/hadoop/data/hdfs/journalnode
        state: directory
        owner: molka
        group: molka
        mode: '0755'

    - name: Démarrer JournalNode en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/hdfs --daemon start journalnode > /tmp/journalnode.log 2>&1 &"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
        HADOOP_LOG_DIR: "/opt/hadoop/logs"
      args:
        executable: /bin/bash

    - name: Attendre le démarrage du JournalNode
      pause:
        seconds: 10

    - name: Vérifier que le JournalNode est actif
      wait_for:
        port: 8485
        timeout: 60
        
    - name: Vérifier les journaux du JournalNode
      shell: "tail -n 30 {{ hadoop_home }}/logs/hadoop-molka-journalnode-*.log"
      become_user: molka
      register: jn_logs
      ignore_errors: yes
      
    - name: Afficher les journaux du JournalNode
      debug:
        var: jn_logs.stdout_lines

- name: Nettoyer et démarrer les services sur le NameNode actif
  hosts: namenode
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Nettoyer les processus existants
      shell: "ps -ef | grep -i hadoop | grep -v grep | awk '{print $2}' | xargs -r kill"
      become_user: molka
      ignore_errors: yes
      
    - name: Attendre que tous les processus s'arrêtent
      pause:
        seconds: 5

    - name: Initialiser HA dans ZooKeeper
      shell: "{{ hadoop_home }}/bin/hdfs zkfc -formatZK -force -nonInteractive"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['namenode'][0]
      register: zkfc_result
      failed_when: false
      
    - name: Afficher le résultat de formatZK
      debug:
        var: zkfc_result
      when: inventory_hostname == groups['namenode'][0]
                                                          
    - name: Créer le répertoire namenode
      file:
        path: "{{ hadoop_home }}/data/hdfs/namenode"
        state: directory
        owner: molka
        group: molka
        mode: '0755'
                                                                                                                               
    - name: Formater le NameNode (si nécessaire)
      shell: "{{ hadoop_home }}/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"
      args:
        creates: "{{ hadoop_home }}/data/hdfs/namenode/current/VERSION"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      when: inventory_hostname == groups['namenode'][0]
      
    - name: Démarrer le NameNode explicitement
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start namenode"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
        
    - name: Démarrer ZKFC explicitement
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start zkfc"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
        
    - name: Attendre que le NameNode commence à écouter
      wait_for:
        host: "{{ inventory_hostname }}"
        port: 8020
        timeout: 60
                                            
    - name: Démarrer les autres services HDFS
      shell: "{{ hadoop_home }}/sbin/start-dfs.sh"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes

- name: Vérifier la connectivité entre nœuds
  hosts: standby
  become: yes
  tasks:
    - name: Vérifier la connectivité avec le NameNode actif
      shell: "ping -c 4 {{ groups['namenode'][0] }}"
      register: ping_result
      ignore_errors: yes
      
    - name: Afficher le résultat du ping
      debug:
        var: ping_result.stdout_lines
        
    - name: Vérifier le port 8020 sur le NameNode actif
      shell: "nc -zv {{ groups['namenode'][0] }} 8020"
      register: nc_result
      ignore_errors: yes
      
    - name: Afficher le résultat de la vérification de port
      debug:
        var: nc_result

- name: Configurer le NameNode standby
  hosts: standby
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Créer le répertoire standby namenode
      file:
        path: "{{ hadoop_home }}/data/hdfs/namenode"
        state: directory
        owner: molka
        group: molka
        mode: '0755'
        
    - name: Bootstrap du standby avec timeout augmenté
      shell: "{{ hadoop_home }}/bin/hdfs namenode -bootstrapStandby -force"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
        HADOOP_CLIENT_OPTS: "-Dfs.defaultFS=hdfs://{{ groups['namenode'][0] }}:8020 -Ddfs.namenode.rpc-address.nn1={{ groups['namenode'][0] }}:8020"
      register: bootstrap_result
      failed_when: false
      
    - name: Afficher le résultat du bootstrap
      debug:
        var: bootstrap_result
        
    - name: Démarrer le standby NameNode
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start namenode"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes
      
    - name: Démarrer ZKFC sur le standby
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start zkfc"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes

- name: Démarrer YARN sur les ResourceManagers
  hosts: resourcemanager
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Démarrer Ressource Manager Active
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh start resourcemanager"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['resourcemanager'][0]
      ignore_errors: yes

    - name: Attendre le démarrage du ResourceManager actif
      pause:
        seconds: 10
      when: inventory_hostname == groups['resourcemanager'][0]                                                                                        
                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes                                      
                                                  
    - name: Démarrer explicitement le ResourceManager en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/yarn --daemon start resourcemanager > /tmp/resourcemanager.log 2>&1 &"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes                                      

    - name: Pause pour démarrage du ResourceManager
      pause:
        seconds: 20 

- name: Restart ResourceManagers Standby
  hosts: resourcemanager_standby
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Stopper Ressource Manager standby
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh stop resourcemanager"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['resourcemanager_standby'][0]
      ignore_errors: yes

    - name: Attendre l'arrêt du ResourceManager standby
      pause:
        seconds: 10
      when: inventory_hostname == groups['resourcemanager_standby'][0]
      
    - name: Démarrer Ressource Manager Standby
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh start resourcemanager"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['resourcemanager_standby'][0]
      ignore_errors: yes

- name: Re-Démarrer YARN sur tous les nœuds
  hosts: resourcemanager
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes  
                                                                                        
- name: Vérifier les services Hadoop (jps)
  hosts: all
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
  tasks:
    - name: Vérifier les processus avec jps
      shell: "jps"
      register: jps_output
      become_user: molka
      args:
        executable: /bin/bash

    - name: Afficher la sortie de jps
      debug:
        var: jps_output.stdout
"""
        }  
        # Écriture des playbooks dans des fichiers dans le répertoire home
        for filename, content in playbooks.items():
            remote_path = f"~/{filename}"  # Chemin vers le home de l'utilisateur
            command = f'echo "{content.replace("\"", "\\\"")}" > {remote_path}'  # Échapper les guillemets

            print(f"Exécution de la commande pour écrire le playbook : {filename}")
            exit_status, output, error = execute_ssh_command(ssh, command)

            if exit_status == 0:
                print(f"✅ Playbook écrit avec succès : {filename}")
            else:
                print(f"❌ Erreur lors de l'écriture du playbook : {filename}")
                print(f"Code de sortie : {exit_status}")
                print(f"Message d'erreur :\n{error.strip()}")
                ssh.close()
                return False  # Stop dès qu'une commande échoue

        # Exécution des playbooks un par un
        for filename in playbooks.keys():
            print(f"Exécution du playbook : {filename}")
            command = f'ansible-playbook ~/{filename} -i ~/inventory.ini -vvv'  # Assurez-vous que l'inventaire est correctement défini

            exit_status, output, error = execute_ssh_command(ssh, command)

            if exit_status == 0:
                print(f"✅ Exécution réussie du playbook : {filename}")
            else:
                print(f"❌ Erreur lors de l'exécution du playbook : {filename}")
                print(f"Code de sortie : {exit_status}")
                print(f"Message d'erreur :\n{error.strip()}")
         # 2. Commandes post-installation structurées
        post_playbooks_commands = [
            # Cluster HDFS
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"', "Formatage Namenode"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"', "Formatage Standby"),

            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/hdfs --daemon start namenode"', "Démarrage Namenode principal"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/hdfs --daemon start namenode"', "Démarrage Namenode secondaire"),
            
            # DataNodes
            *[(f'ssh -o StrictHostKeyChecking=no molka@{ip} "/opt/hadoop/bin/hdfs --daemon start datanode"', f"Démarrage Datanode {ip}") for ip in datanode_ips],
            *[(f'ssh -o StrictHostKeyChecking=no molka@{ip} "/opt/hadoop/bin/hdfs --daemon start journalnode"', f"Démarrage Journalnode {ip}") for ip in datanode_ips],
            
            # ZooKeeper Cluster
            # Démarrage explicite de ZooKeeper sur Namenode, Standby et Datanode1
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/etc/zookeeper/bin/zkServer.sh start"', f"Démarrage ZooKeeper {namenode_ip}"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/etc/zookeeper/bin/zkServer.sh start"', f"Démarrage ZooKeeper {standby_ip}"),
            (f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "/etc/zookeeper/bin/zkServer.sh start"', f"Démarrage ZooKeeper {datanode_ips[0]}"),
                          
            # Mécanismes HA
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/hdfs --daemon start zkfc"', "Démarrage ZKFC principal"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/hdfs --daemon start zkfc"', "Démarrage ZKFC secondaire"),
            
            # Services YARN
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/yarn --daemon start resourcemanager"', "Démarrage ResourceManager principal"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/yarn --daemon start resourcemanager"', "Démarrage ResourceManager secondaire"),
            *[(f'ssh -o StrictHostKeyChecking=no molka@{ip} "/opt/hadoop/bin/yarn --daemon start nodemanager"', f"Démarrage NodeManager {ip}") for ip in datanode_ips],
        ]
        # 3. Exécution séquentielle avec vérification
        print("\n🚀 Phase de démarrage des services...")
        for cmd, service_name in post_playbooks_commands:
            exit_code, output, error = execute_ssh_command(ssh, cmd)
            
            if exit_code != 0:
                print(f"⛔ Échec sur {service_name}")
                ssh.close()
                return jsonify({
                    "status": "error",
                    "error": f"{service_name} : {error.strip()}", 
                    "commande": cmd
                }), 500
            print(f"✅ {service_name} opérationnel")
        # Fermez la connexion SSH après l'exécution
        ssh.close()
        # Toujours succès à la fin
        return jsonify({
            "status": "success",
            "vms": results,
            "ip_map": ip_map,
            "errors": {}
        })

    except Exception as e:
        log_step(f"ERREUR FATALE: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "cluster_name": data.get('cluster_name', 'unknown')
        }), 500

# Fonctions utilitaires (à adapter selon votre implémentation)
def create_vmprox_direct(data):
    with app.test_request_context('/create_vmprox', method='POST', json=data):
        return create_vmprox()

def start_vmprox_direct(data):
    with app.test_request_context('/start_vmprox', method='POST', json=data):
        return start_vmprox()

def get_vmip_direct(data):
    """Nouvelle version simplifiée"""
    with app.test_request_context('/get_vmip', method='POST', json=data):
        response = get_vmip()
        return response.get_json(), response.status_code
#########################################################################################################################"
########################################################################################################################
###########################################################################################################################"
@app.route('/clusterspark_vmprox', methods=['POST'])
def clusterspark_vmprox():
    data = request.get_json()
    print(f"Starting HA cluster creation: {data['cluster_name']}")
    
    # Validation des données
    required = ['proxmox_ip', 'password', 'target_node', 'vm_id_start',
                'template', 'cluster_name', 'node_count']
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    vm_id = int(data['vm_id_start'])
    results = []
    ip_map = {}
    errors = []

    # 1ère BOUCLE: Création de toutes les machines
    print("=== PHASE 1: Création des VMs ===")
    vm_ids = []
    for i in range(data['node_count'] + 2):  # +2 pour l'ansible et le standby
        if i == data['node_count']:
            vm_type = "ansible"  # Ansible Controller
        elif i == data['node_count'] + 1:
            vm_type = "standby"  # Standby Node
        else:
            vm_type = "namenode" if i == 0 else "datanode"  # NameNode ou DataNode
        
        hostname = f"{data['cluster_name']}-{vm_type}-{i}" if vm_type != "ansible" else f"ansible-{data['cluster_name']}"
        current_vm_id = str(vm_id + i)
        vm_ids.append(current_vm_id)
        
        try:
            create_data = {
                "proxmoxIp": data['proxmox_ip'],
                "password": data['password'],
                "hostname": hostname,
                "targetNode": data['target_node'],
                "vm_id": current_vm_id,
                "template": data['template'],
                "network": data.get('network_type', 'nat'),
                "vm_type": vm_type
            }
            
            create_response = create_vmprox_direct(create_data)
            
            if create_response[1] != 200:
                error_msg = create_response[0].get_json().get('error', '')
                if "plugin crashed" in error_msg:
                    print(f"[VM {current_vm_id}] Warning: Terraform plugin crashed but continuing")
                    results.append({
                        "vm_id": current_vm_id,
                        "type": vm_type,
                        "status": "created_with_warning",
                        "warning": "Terraform plugin crashed"
                    })
                else:
                    raise Exception(f"Creation failed: {error_msg}")
            else:
                print(f"[VM {current_vm_id}] Successfully created")
                results.append({
                    "vm_id": current_vm_id,
                    "type": vm_type,
                    "status": "created"
                })

        except Exception as e:
            error_msg = f"[VM {current_vm_id}] Creation error: {str(e)}"
            print(error_msg)
            errors.append(error_msg)
            results.append({
                "vm_id": current_vm_id,
                "type": vm_type,
                "status": "failed",
                "error": str(e)
            })

    # 2ème BOUCLE: Démarrage des machines et attente
    print("\n=== PHASE 2: Démarrage des VMs ===")
    for vm in results:
        if vm['status'] not in ['created', 'created_with_warning']:
            continue
            
        current_vm_id = vm['vm_id']
        try:
            print(f"[VM {current_vm_id}] Starting...")
            start_response = start_vmprox_direct({
                "proxmox_ip": data['proxmox_ip'],
                "username": "root",
                "password": data['password'],
                "vm_id": current_vm_id
            })
            
            if start_response[1] != 200:
                raise Exception(f"Start failed: {start_response[0].get_json()}")
            
            print(f"[VM {current_vm_id}] Waiting 90 seconds...")
            time.sleep(90)  # Attente fixe pour toutes les VMs
            vm['status'] = "started"

        except Exception as e:
            error_msg = f"[VM {current_vm_id}] Start error: {str(e)}"
            print(error_msg)
            errors.append(error_msg)
            vm['status'] = "start_failed"
            vm['error'] = str(e)

    # 3ème BOUCLE: Récupération des IPs
    ansible_ip = None
    namenode_ip = None
    standby_ip = None
    datanode_ips = []
    retry_attempts = 10  # Nombre de tentatives
    retry_delay = 30    # Délai d'attente entre les tentatives en secondes

    for vm in results:
        if vm['status'] != 'started':
            continue
            
        current_vm_id = vm['vm_id']
        vm_type = vm['type']
        
        for attempt in range(retry_attempts):
            try:
                print(f"[VM {current_vm_id}] Tentative {attempt + 1}/{retry_attempts} pour obtenir l'IP... (Type: {vm_type})")
                ip_data, status_code = get_vmip_direct({
                    "proxmoxIp": data['proxmox_ip'],
                    "password": data['password'],
                    "vm_id": current_vm_id
                })
                
                if status_code != 200:
                    raise Exception(f"Erreur: {ip_data.get('error', 'Inconnue')}")
                
                vm_ip = ip_data['ip'] if isinstance(ip_data, dict) else ip_data
                vm_ip = vm_ip.strip().replace("inet ", "")
                vm['ip'] = vm_ip
                
                # Log spécifique pour le nœud Ansible
                if vm_type == "ansible":
                    ansible_ip = vm_ip
                    print(f"!!! NŒUD ANSIBLE TROUVÉ !!! IP: {ansible_ip} (VM ID: {current_vm_id})")
                elif vm_type == "namenode":
                    namenode_ip = vm_ip
                elif vm_type == "standby":
                    standby_ip = vm_ip
                elif vm_type == "datanode":
                    datanode_ips.append(vm_ip)

                if vm_type not in ip_map:
                    ip_map[vm_type] = []
                ip_map[vm_type].append(vm_ip)
                
                print(f"[VM {current_vm_id}] IP attribuée: {vm_ip}")
                break  # Sortir de la boucle si l'IP a été récupérée avec succès

            except Exception as e:
                error_msg = f"[VM {current_vm_id}] Erreur IP: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                vm['status'] = "ip_failed"
                vm['error'] = str(e)

                if attempt < retry_attempts - 1:
                    print(f"Aucune IP obtenue, attente de {retry_delay} secondes avant de réessayer...")
                    time.sleep(retry_delay)  # Attendre avant de réessayer

    # Vérification finale des IPs
    if not ansible_ip:
        raise Exception("ERREUR CRITIQUE: Aucune IP trouvée pour le nœud Ansible")

    print(f"""
    === VÉRIFICATION IP ===
    IP Ansible: {ansible_ip}
    IP NameNode: {namenode_ip}
    IP Standby: {standby_ip}
    IP DataNodes: {', '.join(datanode_ips)}
    """)

    # Vérification des IPs récupérées
    if not ansible_ip or not namenode_ip or not standby_ip or len(datanode_ips) < 2:
        raise Exception("ERREUR CRITIQUE: Aucune IP trouvée pour le nœud Ansible ou NameNode/Datanodes manquants.")

    # 4ème PHASE: Configuration Ansible et installation Hadoop
    try:
        # Créer une connexion SSH vers le contrôleur Ansible
        ssh = create_ssh_client(ansible_ip)
        if not ssh:
            print("Échec de la connexion SSH.")
            return False

        # Télécharger Hadoop et configurer
        commands = [
            'sudo apt update && sudo apt install -y wget openjdk-11-jdk net-tools sshpass pdsh',
            'sudo apt install -y python3 python3-pip',
            'sudo apt install -y ansible',

            #########################################jareb
            'mkdir -p ~/.ssh',
            '[ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa',
            f'ssh-keyscan -H {ansible_ip} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {namenode_ip} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {standby_ip} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {datanode_ips } >> ~/.ssh/known_hosts',
        ]
        # Ajout des commandes pour copier la clé SSH sur chaque datanode
        for ip in datanode_ips:
            commands.append(f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{ip}')

        # Ajout des commandes pour copier la clé SSH sur d'autres hôtes
        commands.extend([
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{ansible_ip}',
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{namenode_ip}',
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{standby_ip}',

            'chmod 600 ~/.ssh/id_rsa',
            'chmod 644 ~/.ssh/id_rsa.pub',
            'chmod 700 ~/.ssh',
################################################################################################################################
#ZOOKEEPER
#################################################################################################################################
           'wget https://archive.apache.org/dist/zookeeper/zookeeper-3.6.3/apache-zookeeper-3.6.3-bin.tar.gz',
           'sudo mv apache-zookeeper-3.6.3-bin.tar.gz /tmp',

           # Copier vers Namenode et Standby
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{namenode_ip}:/tmp/',
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{standby_ip}:/tmp/',
            # Copier vers seulement le premier datanode (pour avoir 3 nœuds ZooKeeper)
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{datanode_ips[0]}:/tmp/',

            # Créer /etc/zookeeper et déplacer le fichier
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',

            # Extraire Zookeeper
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',

            # Renommer zoo_sample.cfg en zoo.cfg
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',

            # Créer d'abord le dossier puis écrire l'ID
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /var/lib/zookeeper && echo 1 | sudo tee /var/lib/zookeeper/myid"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /var/lib/zookeeper && echo 2 | sudo tee /var/lib/zookeeper/myid"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /var/lib/zookeeper && echo 3 | sudo tee /var/lib/zookeeper/myid"',

            # 📂 Ajouter la création des dossiers logs avec bonne permission
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /etc/zookeeper/logs /var/lib/zookeeper /var/log/zookeeper && sudo chown -R molka:molka /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && sudo chmod -R 755 /etc/zookeeper"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /etc/zookeeper/logs /var/lib/zookeeper /var/log/zookeeper && sudo chown -R molka:molka /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && sudo chmod -R 755 /etc/zookeeper"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /etc/zookeeper/logs /var/lib/zookeeper /var/log/zookeeper && sudo chown -R molka:molka /etc/zookeeper /var/lib/zookeeper /var/log/zookeeper && sudo chmod -R 755 /etc/zookeeper"',
 
################################################################################################################################
            'wget https://archive.apache.org/dist/spark/spark-3.3.1/spark-3.3.1-bin-hadoop3.tgz && sudo mv spark-3.3.1-bin-hadoop3.tgz /tmp',

            'sudo chown -R molka:molka /opt',
            # Copier vers Namenode et Standby
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/spark-3.3.1-bin-hadoop3.tgz molka@{namenode_ip}:/tmp/',
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/spark-3.3.1-bin-hadoop3.tgz molka@{standby_ip}:/tmp/',
            # Copier vers seulement le premier datanode (pour avoir 3 nœuds ZooKeeper)
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /tmp/spark-3.3.1-bin-hadoop3.tgz molka@{datanode_ips[0]}:/tmp/',

            # Créer /opt/spark et déplacer le fichier
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /opt/spark && sudo mv /tmp/spark-3.3.1-bin-hadoop3.tgz /opt/spark/"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /opt/spark && sudo mv /tmp/spark-3.3.1-bin-hadoop3.tgz /opt/spark/"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /opt/spark && sudo mv /tmp/spark-3.3.1-bin-hadoop3.tgz /opt/spark/"',

            # Extraire spark
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "cd /opt/spark && sudo tar xzf spark-3.3.1-bin-hadoop3.tgz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "cd /opt/spark && sudo tar xzf spark-3.3.1-bin-hadoop3.tgz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "cd /opt/spark && sudo tar xzf spark-3.3.1-bin-hadoop3.tgz --strip-components=1"',

            # 📂 Créer le dossier logs de Spark avec les bonnes permissions sur chaque nœud
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /opt/spark/logs && sudo chown -R molka:molka /opt/spark/logs && sudo chown -R molka:molka /opt/spark && sudo chmod -R 755 /opt/spark"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /opt/spark/logs && sudo chown -R molka:molka /opt/spark/logs && sudo chown -R molka:molka /opt/spark && sudo chmod -R 755 /opt/spark"',
            f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "sudo mkdir -p /opt/spark/logs && sudo chown -R molka:molka /opt/spark/logs && sudo chown -R molka:molka /opt/spark && sudo chmod -R 755 /opt/spark"',

################################################################################################################################
#HADOOP
#################################################################################################################################
            'wget https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz',
            'sudo mv hadoop-3.3.1.tar.gz /tmp',
            'sudo chown -R molka:molka /opt',
            # Copier vers Namenode et Standby
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/hadoop-3.3.1.tar.gz molka@{namenode_ip}:/tmp/',
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/hadoop-3.3.1.tar.gz molka@{standby_ip}:/tmp/',
            f'for datanode in {" ".join(datanode_ips)}; do sshpass -p "molka" scp -o StrictHostKeyChecking=no /tmp/hadoop-3.3.1.tar.gz molka@${{datanode}}:/tmp/; done',

            # Créer /opt/hadoop et déplacer le fichier
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "sudo mkdir -p /opt/hadoop && sudo mv /tmp/hadoop-3.3.1.tar.gz /opt/hadoop/"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "sudo mkdir -p /opt/hadoop && sudo mv /tmp/hadoop-3.3.1.tar.gz /opt/hadoop/"',
            f'for datanode in {" ".join(datanode_ips)}; do ssh -o StrictHostKeyChecking=no molka@${{datanode}} "sudo mkdir -p /opt/hadoop && sudo mv /tmp/hadoop-3.3.1.tar.gz /opt/hadoop/"; done',

            # Extraire hadoop
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "cd /opt/hadoop && sudo tar xzf hadoop-3.3.1.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "cd /opt/hadoop && sudo tar xzf hadoop-3.3.1.tar.gz --strip-components=1"',
            f'for datanode in {" ".join(datanode_ips)}; do ssh -o StrictHostKeyChecking=no molka@${{datanode}} "cd /opt/hadoop && sudo tar xzf hadoop-3.3.1.tar.gz --strip-components=1"; done',
################################################################################################################################
            
#BASHRC
#################################################################################################################################
            # modification ."bashrc
          ############################################
            'echo "export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64" >> /home/molka/.bashrc',
            'echo "export HADOOP_HOME=/opt/hadoop" >> /home/molka/.bashrc',
            'echo "export ZOOKEEPER_HOME=/etc/zookeeper" >> /home/molka/.bashrc',
            'echo "export ZOO_LOG_DIR=/var/log/zookeeper" >> /home/molka/.bashrc',
            'echo "export SPARK_HOME=/opt/spark" >> /home/molka/.bashrc',
            'echo "export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$SPARK_HOME/bin:$SPARK_HOME/sbin:$ZOOKEEPER_HOME/bin" >> /home/molka/.bashrc',
            
            # Copie du .bashrc sur les différents nœuds
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{ansible_ip}:/home/molka/.bashrc',
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{namenode_ip}:/home/molka/.bashrc',
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{standby_ip}:/home/molka/.bashrc',
            f'for datanode in {" ".join(datanode_ips)}; do sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@${{datanode}}:/home/molka/.bashrc; done',
             
              # Recharger le .bashrc pour que les changements prennent effet immédiatement (source)
            f'ssh -o StrictHostKeyChecking=no molka@{ansible_ip} "source /home/molka/.bashrc"',
            f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "source /home/molka/.bashrc"',
            f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "source /home/molka/.bashrc"',
            f'for datanode in {" ".join(datanode_ips)}; do ssh -o StrictHostKeyChecking=no molka@${{datanode}} "source /home/molka/.bashrc"; done',
          
################################################################################################################################
#################################################################################################################################

            # 📂 Créer le dossier "templates" pour Ansible
            'mkdir -p ~/templates',
            # 📝 Ajouter les fichiers de configuration Hadoop
            # core-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>fs.defaultFS</name>\n        <value>hdfs://ha-cluster</value>\n    </property>\n    <property>\n        <name>dfs.client.failover.proxy.provider.ha-cluster</name>\n        <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>\n    </property>\n    <property>\n        <name>ha.zookeeper.quorum</name>\n        <value>{% for zk in groups[\'zookeeper\'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>\n    </property>\n    <property>\n        <name>dfs.permissions.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>ipc.client.connect.max.retries</name>\n        <value>3</value>\n    </property>\n</configuration>" > ~/templates/core-site.xml.j2',
            
            # hdfs-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>dfs.replication</name>\n        <value>2</value>\n    </property>\n    <property>\n        <name>dfs.nameservices</name>\n        <value>ha-cluster</value>\n    </property>\n    <property>\n        <name>dfs.ha.namenodes.ha-cluster</name>\n        <value>{{ groups[\'namenode\'][0] }},{{ groups[\'standby\'][0] }}</value>\n    </property>\n    <property>\n        <name>dfs.namenode.rpc-address.ha-cluster.{{ groups[\'namenode\'][0] }}</name>\n        <value>{{ hostvars[groups[\'namenode\'][0]].ansible_host }}:8020</value>\n    </property>\n    <property>\n        <name>dfs.namenode.rpc-address.ha-cluster.{{ groups[\'standby\'][0] }}</name>\n        <value>{{ hostvars[groups[\'standby\'][0]].ansible_host }}:8020</value>\n    </property>\n    <property>\n        <name>dfs.namenode.http-address.ha-cluster.{{ groups[\'namenode\'][0] }}</name>\n        <value>{{ hostvars[groups[\'namenode\'][0]].ansible_host }}:50070</value>\n    </property>\n    <property>\n        <name>dfs.namenode.http-address.ha-cluster.{{ groups[\'standby\'][0] }}</name>\n        <value>{{ hostvars[groups[\'standby\'][0]].ansible_host }}:50070</value>\n    </property>\n    <property>\n        <name>dfs.namenode.shared.edits.dir</name>\n        <value>qjournal://{% for jn in groups[\'journalnode\'] %}{{ hostvars[jn].ansible_host }}:8485{% if not loop.last %};{% endif %}{% endfor %}/ha-cluster</value>\n    </property>\n    <property>\n        <name>dfs.ha.automatic-failover.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>dfs.client.failover.proxy.provider.ha-cluster</name>\n        <value>org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider</value>\n    </property>\n    <property>\n        <name>ha.zookeeper.quorum</name>\n        <value>{% for zk in groups[\'zookeeper\'] %}{{ hostvars[zk].ansible_host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>\n    </property>\n    <property>\n        <name>dfs.namenode.name.dir</name>\n        <value>file:{{ hadoop_home }}/data/hdfs/namenode</value>\n    </property>\n    <property>\n        <name>dfs.datanode.data.dir</name>\n        <value>file:{{ hadoop_home }}/data/hdfs/datanode</value>\n    </property>\n    <property>\n        <name>dfs.namenode.checkpoint.dir</name>\n        <value>file:{{ hadoop_home }}/data/hdfs/namesecondary</value>\n    </property>\n    <property>\n        <name>dfs.ha.fencing.methods</name>\n        <value>shell(/bin/true)</value>\n    </property>\n    <property>\n        <name>dfs.ha.failover-controller.active-standby-elector.zk.op.retries</name>\n        <value>3</value>\n    </property>\n</configuration>" > ~/templates/hdfs-site.xml.j2',
            
            # yarn-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>yarn.resourcemanager.ha.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.cluster-id</name>\n        <value>yarn-cluster</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.ha.rm-ids</name>\n        <value>rm1,rm2</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.zk-address</name>\n        <value>{% for host in groups[\'zookeeper\'] %}{{ host }}:2181{% if not loop.last %},{% endif %}{% endfor %}</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.hostname.rm1</name>\n        <value>{{ groups[\'resourcemanager\'][0] }}</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.hostname.rm2</name>\n        <value>{{ groups[\'resourcemanager_standby\'][0] }}</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.recovery.enabled</name>\n        <value>true</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.store.class</name>\n        <value>org.apache.hadoop.yarn.server.resourcemanager.recovery.ZKRMStateStore</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.webapp.address.rm1</name>\n        <value>{{ groups[\'resourcemanager\'][0] }}:8088</value>\n    </property>\n    <property>\n        <name>yarn.resourcemanager.webapp.address.rm2</name>\n        <value>{{ groups[\'resourcemanager_standby\'][0] }}:8088</value>\n    </property>\n    <property>\n        <name>yarn.nodemanager.resource.memory-mb</name>\n        <value>4096</value>\n    </property>\n    <property>\n        <name>yarn.nodemanager.resource.cpu-vcores</name>\n        <value>4</value>\n    </property>\n</configuration>" > ~/templates/yarn-site.xml.j2',
            
            # mapred-site.xml.j2
            'echo "<configuration>\n    <property>\n        <name>mapreduce.framework.name</name>\n        <value>yarn</value>\n    </property>\n</configuration>" > ~/templates/mapred-site.xml.j2',

            # masters.j2
            'echo "{{ groups[\'namenode\'][0] }}" > ~/templates/masters.j2',

            # workers.j2
            'echo "{% for worker in groups[\'datanodes\'] %}{{ worker }}\n{% endfor %}" > ~/templates/workers.j2',

            # zoo.cfg.j2
            'echo "tickTime=2000\ninitLimit=10\nsyncLimit=5\ndataDir=/var/lib/zookeeper\ndataLogDir=/var/log/zookeeper\nclientPort=2181\n{% for zk in groups[\'zookeeper\'] %}server.{{ loop.index }}={{ hostvars[zk].ansible_host }}:2888:3888\n{% endfor %}" > ~/templates/zoo.cfg.j2',

            # spark-env.sh.j2
            'echo "export HADOOP_CONF_DIR={{ hadoop_home }}/etc/hadoop\nexport SPARK_HOME=/opt/spark\nexport SPARK_DIST_CLASSPATH=$({{ hadoop_home }}/bin/hadoop classpath)\nexport JAVA_HOME={{ java_home }}" > ~/templates/spark-env.sh.j2',

            # spark-defaults.conf.j2
            'echo "spark.master                     yarn\nspark.eventLog.enabled           true\nspark.eventLog.dir               hdfs://ha-cluster/spark-logs\nspark.history.fs.logDirectory    hdfs://ha-cluster/spark-logs\nspark.serializer                 org.apache.spark.serializer.KryoSerializer\nspark.hadoop.yarn.resourcemanager.ha.enabled   true\nspark.hadoop.yarn.resourcemanager.ha.rm-ids    rm1,rm2\nspark.hadoop.yarn.resourcemanager.hostname.rm1 {{ groups[\'resourcemanager\'][0] }}\nspark.hadoop.yarn.resourcemanager.hostname.rm2 {{ groups[\'resourcemanager_standby\'][0] }}\nspark.driver.memory              1g\nspark.executor.memory            2g\nspark.hadoop.yarn.resourcemanager.address {{ groups[\'resourcemanager\'][0] }}:8032\nspark.hadoop.yarn.resourcemanager.scheduler.address {{ groups[\'resourcemanager\'][0] }}:8030" > ~/templates/spark-defaults.conf.j2',
            # hosts.j2
            'echo "# ANSIBLE GENERATED HOSTS FILE\n{% for host in groups[\'all\'] %}{{ hostvars[host].ansible_host }} {{ host }}\n{% endfor %}" > ~/templates/hosts.j2',
            
            # Créer le fichier inventory.ini
            f'echo """[namenode]\n{namenode_ip} ansible_host={namenode_ip}\n{standby_ip} ansible_host={standby_ip}\n\n[spark]\n{namenode_ip} ansible_host={namenode_ip}\n\n[standby]\n{standby_ip} ansible_host={standby_ip}\n\n[datanodes]\n{"\n".join([f"{ip} ansible_host={ip}" for ip in datanode_ips])}\n\n[resourcemanager]\n{namenode_ip} ansible_host={namenode_ip}\n\n[resourcemanager_standby]\n{standby_ip} ansible_host={standby_ip}\n\n[zookeeper]\n{namenode_ip} ansible_host={namenode_ip}\n{standby_ip} ansible_host={standby_ip}\n{datanode_ips[0]} ansible_host={datanode_ips[0]}\n\n[journalnode]\n{namenode_ip} ansible_host={namenode_ip}\n{standby_ip} ansible_host={standby_ip}\n{datanode_ips[0]} ansible_host={datanode_ips[0]}\n\n[all:vars]\nansible_user=molka\nansible_ssh_private_key_file=~/.ssh/id_rsa\nansible_ssh_common_args=-o StrictHostKeyChecking=no\nansible_python_interpreter=/usr/bin/python3""" > ~/inventory.ini'        
            ])
        
        for idx, command in enumerate(commands, start=1):
            print(f"\n[Commande {idx}/{len(commands)}] Exécution : {command}")
            exit_status, output, error = execute_ssh_command(ssh, command)

            if exit_status == 0:
                print(f"✅ Commande réussie : {command}")
            else:
                print(f"❌ Erreur lors de l'exécution de la commande : {command}")
                print(f"Code de sortie : {exit_status}")
                print(f"Message d'erreur :\n{error.strip()}")
                ssh.close()
                return False  # Stop dès qu'une commande échoue        
        # Définir les playbooks avec une syntaxe YAML correcte
        playbooks = {
            'deploy_hadoop.yml': """---
- name: Déploiement Hadoop via extraction
  hosts: all
  become: yes
  gather_facts: no

  tasks:
    # 1. Créer /opt si nécessaire
    - name: Créer répertoire /opt
      file:
        path: /opt
        state: directory
        owner: root
        group: root
        mode: '0755'

    # 2. Installer les dépendances
    - name: Installer paquets requis
      apt:
        name:
          - openjdk-11-jdk
          - sshpass
          - net-tools
          - pdsh
          - rsync
          - tar
        state: present
        update_cache: yes

""",
          'hadoop_config.yml': """---
- name: Configurer les fichiers de configuration Hadoop et /etc/hosts
  hosts: all
  become: yes
  vars:
    namenode_hostname: "{{ groups['namenode'][0] }}"
    standby_hostname: "{{ groups['standby'][0] | default('default_standby_hostname') }}"
    hadoop_home: /opt/hadoop  # Ajout de la variable hadoop_home

  tasks:
    - name: Déployer core-site.xml
      template:
        src: /home/molka/templates/core-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/core-site.xml"

    - name: Déployer hdfs-site.xml
      template:
        src: /home/molka/templates/hdfs-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/hdfs-site.xml"

    - name: Déployer yarn-site.xml
      template:
        src: /home/molka/templates/yarn-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/yarn-site.xml"

    - name: Déployer mapred-site.xml
      template:
        src: /home/molka/templates/mapred-site.xml.j2
        dest: "{{ hadoop_home }}/etc/hadoop/mapred-site.xml"

    - name: Déployer masters
      template:
        src: /home/molka/templates/masters.j2
        dest: "{{ hadoop_home }}/etc/hadoop/masters"

    - name: Déployer workers
      template:
        src: /home/molka/templates/workers.j2
        dest: "{{ hadoop_home }}/etc/hadoop/workers"

    - name: Déployer zoo.cfg pour ZooKeeper
      template:
        src: /home/molka/templates/zoo.cfg.j2
        dest: "/etc/zookeeper/conf/zoo.cfg"

    - name: Mettre à jour /etc/hosts avec les hôtes du cluster
      template:
        src: /home/molka/templates/hosts.j2
        dest: /etc/hosts

- name: Configurer les nœuds Spark  # <-- Début d'une NOUVELLE play
  hosts: spark                      # Aligné avec '- name'
  become: yes                       # Aligné avec 'hosts'
  tasks:
    - name: Créer le répertoire de configuration Spark
      file:                         # Aligné sous 'tasks'
        path: /opt/spark/conf
        state: directory
        owner: molka
        group: molka
        mode: 0755

    - name: Déployer spark-defaults.conf
      template:                     # Aligné sous 'tasks'
        src: /home/molka/templates/spark-defaults.conf.j2
        dest: "/opt/spark/conf/spark-defaults.conf"

    - name: Déployer spark-env.sh
      template:                    # Aligné sous 'tasks'
        src: /home/molka/templates/spark-env.sh.j2
        dest: "/opt/spark/conf/spark-env.sh"
        
""",
            'hadoop_start.yml': """---
- name: Vérifier et démarrer ZooKeeper sur les nœuds ZooKeeper
  hosts: zookeeper
  become: yes
  vars:
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
    hadoop_home: "/opt/hadoop"
    zookeeper_home: "/etc/zookeeper"
  tasks:
    - name: Vérifier la configuration de ZooKeeper
      stat:
        path: "{{ zookeeper_home }}/conf/zoo.cfg"
      register: zoo_cfg_exists

    - name: Afficher le contenu de zoo.cfg
      shell: "cat {{ zookeeper_home }}/conf/zoo.cfg"
      register: zoo_cfg_content
      when: zoo_cfg_exists.stat.exists
      
    - name: Afficher le contenu de zoo.cfg
      debug:
        var: zoo_cfg_content.stdout_lines
      when: zoo_cfg_exists.stat.exists
    
    - name: Créer le répertoire /var/lib/zookeeper s'il n'existe pas
      file:
        path: /var/lib/zookeeper
        state: directory
        owner: molka
        group: molka
        mode: '0755'

    - name: Déplacer le fichier myid vers /var/lib/zookeeper
      command: mv /etc/zookeeper/myid /var/lib/zookeeper/myid
      args:
        removes: /etc/zookeeper/myid
      become_user: molka
      ignore_errors: yes

    - name: Stopper ZooKeeper si déjà en cours d'exécution
      shell: "{{ zookeeper_home }}/bin/zkServer.sh stop"
      become_user: molka
      environment:
        ZOO_LOG_DIR: "/var/log/zookeeper"
        ZOO_CONF_DIR: "{{ zookeeper_home }}/conf"
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes
      
    - name: Attendre que ZooKeeper s'arrête
      pause:
        seconds: 5
    
    - name: Démarrer ZooKeeper
      shell: "{{ zookeeper_home }}/bin/zkServer.sh start"
      become_user: molka
      environment:
        ZOO_LOG_DIR: "/var/log/zookeeper"
        ZOO_CONF_DIR: "{{ zookeeper_home }}/conf"
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      register: zk_status
      
    - name: Attendre le démarrage de ZooKeeper
      pause:
        seconds: 10
        
    - name: Vérifier le démarrage de ZooKeeper
      shell: "{{ zookeeper_home }}/bin/zkServer.sh status"
      become_user: molka
      environment:
        ZOO_LOG_DIR: "/var/log/zookeeper"
        ZOO_CONF_DIR: "{{ zookeeper_home }}/conf"
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      register: zk_status_check
      ignore_errors: yes
      
    - name: Afficher le statut de ZooKeeper
      debug:
        var: zk_status_check.stdout
        
    - name: Afficher les journaux ZooKeeper
      shell: "tail -n 30 /var/log/zookeeper/zookeeper.log"
      become_user: molka
      register: zk_logs
      ignore_errors: yes
      
    - name: Afficher les journaux de ZooKeeper
      debug:
        var: zk_logs.stdout_lines
    
    - name: Créer les répertoires de logs
      file:
        path: /opt/hadoop/logs
        state: directory
        owner: molka
        group: molka
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
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Créer le répertoire JournalNode
      file:
        path: /opt/hadoop/data/hdfs/journalnode
        state: directory
        owner: molka
        group: molka
        mode: '0755'

    - name: Démarrer JournalNode en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/hdfs --daemon start journalnode > /tmp/journalnode.log 2>&1 &"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
        HADOOP_LOG_DIR: "/opt/hadoop/logs"
      args:
        executable: /bin/bash

    - name: Attendre le démarrage du JournalNode
      pause:
        seconds: 10

    - name: Vérifier que le JournalNode est actif
      wait_for:
        port: 8485
        timeout: 60
        
    - name: Vérifier les journaux du JournalNode
      shell: "tail -n 30 {{ hadoop_home }}/logs/hadoop-molka-journalnode-*.log"
      become_user: molka
      register: jn_logs
      ignore_errors: yes
      
    - name: Afficher les journaux du JournalNode
      debug:
        var: jn_logs.stdout_lines

- name: Nettoyer et démarrer les services sur le NameNode actif
  hosts: namenode
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Nettoyer les processus existants
      shell: "ps -ef | grep -i hadoop | grep -v grep | awk '{print $2}' | xargs -r kill"
      become_user: molka
      ignore_errors: yes
      
    - name: Attendre que tous les processus s'arrêtent
      pause:
        seconds: 5

    - name: Initialiser HA dans ZooKeeper
      shell: "{{ hadoop_home }}/bin/hdfs zkfc -formatZK -force -nonInteractive"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['namenode'][0]
      register: zkfc_result
      failed_when: false
      
    - name: Afficher le résultat de formatZK
      debug:
        var: zkfc_result
      when: inventory_hostname == groups['namenode'][0]
                                                          
    - name: Créer le répertoire namenode
      file:
        path: "{{ hadoop_home }}/data/hdfs/namenode"
        state: directory
        owner: molka
        group: molka
        mode: '0755'
                                                                                                                               
    - name: Formater le NameNode (si nécessaire)
      shell: "{{ hadoop_home }}/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"
      args:
        creates: "{{ hadoop_home }}/data/hdfs/namenode/current/VERSION"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      when: inventory_hostname == groups['namenode'][0]
      
    - name: Démarrer le NameNode explicitement
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start namenode"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
        
    - name: Démarrer ZKFC explicitement
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start zkfc"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
        
    - name: Attendre que le NameNode commence à écouter
      wait_for:
        host: "{{ inventory_hostname }}"
        port: 8020
        timeout: 60
                                            
    - name: Démarrer les autres services HDFS
      shell: "{{ hadoop_home }}/sbin/start-dfs.sh"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes

- name: Vérifier la connectivité entre nœuds
  hosts: standby
  become: yes
  tasks:
    - name: Vérifier la connectivité avec le NameNode actif
      shell: "ping -c 4 {{ groups['namenode'][0] }}"
      register: ping_result
      ignore_errors: yes
      
    - name: Afficher le résultat du ping
      debug:
        var: ping_result.stdout_lines
        
    - name: Vérifier le port 8020 sur le NameNode actif
      shell: "nc -zv {{ groups['namenode'][0] }} 8020"
      register: nc_result
      ignore_errors: yes
      
    - name: Afficher le résultat de la vérification de port
      debug:
        var: nc_result

- name: Configurer le NameNode standby
  hosts: standby
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Créer le répertoire standby namenode
      file:
        path: "{{ hadoop_home }}/data/hdfs/namenode"
        state: directory
        owner: molka
        group: molka
        mode: '0755'
        
    - name: Bootstrap du standby avec timeout augmenté
      shell: "{{ hadoop_home }}/bin/hdfs namenode -bootstrapStandby -force"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
        HADOOP_CLIENT_OPTS: "-Dfs.defaultFS=hdfs://{{ groups['namenode'][0] }}:8020 -Ddfs.namenode.rpc-address.nn1={{ groups['namenode'][0] }}:8020"
      register: bootstrap_result
      failed_when: false
      
    - name: Afficher le résultat du bootstrap
      debug:
        var: bootstrap_result
        
    - name: Démarrer le standby NameNode
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start namenode"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes
      
    - name: Démarrer ZKFC sur le standby
      shell: "{{ hadoop_home }}/bin/hdfs --daemon start zkfc"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes

- name: Démarrer YARN sur les ResourceManagers
  hosts: resourcemanager
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Démarrer Ressource Manager Active
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh start resourcemanager"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['resourcemanager'][0]
      ignore_errors: yes

    - name: Attendre le démarrage du ResourceManager actif
      pause:
        seconds: 10
      when: inventory_hostname == groups['resourcemanager'][0]                                                                                        
                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes                                      
                                                  
    - name: Démarrer explicitement le ResourceManager en arrière-plan
      shell: "nohup {{ hadoop_home }}/bin/yarn --daemon start resourcemanager > /tmp/resourcemanager.log 2>&1 &"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes                                      

    - name: Pause pour démarrage du ResourceManager
      pause:
        seconds: 20 

- name: Restart ResourceManagers Standby
  hosts: resourcemanager_standby
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:
    - name: Stopper Ressource Manager standby
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh stop resourcemanager"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['resourcemanager_standby'][0]
      ignore_errors: yes

    - name: Attendre l'arrêt du ResourceManager standby
      pause:
        seconds: 10
      when: inventory_hostname == groups['resourcemanager_standby'][0]
      
    - name: Démarrer Ressource Manager Standby
      shell: "{{ hadoop_home }}/sbin/yarn-daemon.sh start resourcemanager"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      when: inventory_hostname == groups['resourcemanager_standby'][0]
      ignore_errors: yes

- name: Re-Démarrer YARN sur tous les nœuds
  hosts: resourcemanager
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
    java_home: "/usr/lib/jvm/java-11-openjdk-amd64"
  tasks:                                            
    - name: Démarrer YARN
      shell: "{{ hadoop_home }}/sbin/start-yarn.sh"
      become_user: molka
      environment:
        JAVA_HOME: "{{ java_home }}"
      args:
        executable: /bin/bash
      ignore_errors: yes  
                                                                                        
- name: Vérifier les services Hadoop (jps)
  hosts: all
  become: yes
  vars:
    hadoop_home: "/opt/hadoop"
  tasks:
    - name: Vérifier les processus avec jps
      shell: "jps"
      register: jps_output
      become_user: molka
      args:
        executable: /bin/bash

    - name: Afficher la sortie de jps
      debug:
        var: jps_output.stdout
"""
        }  
        # Écriture des playbooks dans des fichiers dans le répertoire home
        for filename, content in playbooks.items():
            remote_path = f"~/{filename}"  # Chemin vers le home de l'utilisateur
            command = f'echo "{content.replace("\"", "\\\"")}" > {remote_path}'  # Échapper les guillemets

            print(f"Exécution de la commande pour écrire le playbook : {filename}")
            exit_status, output, error = execute_ssh_command(ssh, command)

            if exit_status == 0:
                print(f"✅ Playbook écrit avec succès : {filename}")
            else:
                print(f"❌ Erreur lors de l'écriture du playbook : {filename}")
                print(f"Code de sortie : {exit_status}")
                print(f"Message d'erreur :\n{error.strip()}")
                ssh.close()
                return False  # Stop dès qu'une commande échoue

        # Exécution des playbooks un par un
        for filename in playbooks.keys():
            print(f"Exécution du playbook : {filename}")
            command = f'ansible-playbook ~/{filename} -i ~/inventory.ini -vvv'  # Assurez-vous que l'inventaire est correctement défini

            exit_status, output, error = execute_ssh_command(ssh, command)

            if exit_status == 0:
                print(f"✅ Exécution réussie du playbook : {filename}")
            else:
                print(f"❌ Erreur lors de l'exécution du playbook : {filename}")
                print(f"Code de sortie : {exit_status}")
                print(f"Message d'erreur :\n{error.strip()}")
         # 2. Commandes post-installation structurées
        post_playbooks_commands = [
            # Cluster HDFS
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"', "Formatage Namenode"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/hdfs namenode -format -force -clusterId ha-cluster -nonInteractive"', "Formatage Standby"),

            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/hdfs --daemon start namenode"', "Démarrage Namenode principal"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/hdfs --daemon start namenode"', "Démarrage Namenode secondaire"),
            
            # DataNodes
            *[(f'ssh -o StrictHostKeyChecking=no molka@{ip} "/opt/hadoop/bin/hdfs --daemon start datanode"', f"Démarrage Datanode {ip}") for ip in datanode_ips],
            *[(f'ssh -o StrictHostKeyChecking=no molka@{ip} "/opt/hadoop/bin/hdfs --daemon start journalnode"', f"Démarrage Journalnode {ip}") for ip in datanode_ips],
            
            # ZooKeeper Cluster
            # Démarrage explicite de ZooKeeper sur Namenode, Standby et Datanode1
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/etc/zookeeper/bin/zkServer.sh start"', f"Démarrage ZooKeeper {namenode_ip}"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/etc/zookeeper/bin/zkServer.sh start"', f"Démarrage ZooKeeper {standby_ip}"),
            (f'ssh -o StrictHostKeyChecking=no molka@{datanode_ips[0]} "/etc/zookeeper/bin/zkServer.sh start"', f"Démarrage ZooKeeper {datanode_ips[0]}"),
                          
            # Mécanismes HA
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/hdfs --daemon start zkfc"', "Démarrage ZKFC principal"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/hdfs --daemon start zkfc"', "Démarrage ZKFC secondaire"),
            
            # Services YARN
            (f'ssh -o StrictHostKeyChecking=no molka@{namenode_ip} "/opt/hadoop/bin/yarn --daemon start resourcemanager"', "Démarrage ResourceManager principal"),
            (f'ssh -o StrictHostKeyChecking=no molka@{standby_ip} "/opt/hadoop/bin/yarn --daemon start resourcemanager"', "Démarrage ResourceManager secondaire"),
            *[(f'ssh -o StrictHostKeyChecking=no molka@{ip} "/opt/hadoop/bin/yarn --daemon start nodemanager"', f"Démarrage NodeManager {ip}") for ip in datanode_ips],
        ]
        # 3. Exécution séquentielle avec vérification
        print("\n🚀 Phase de démarrage des services...")
        for cmd, service_name in post_playbooks_commands:
            exit_code, output, error = execute_ssh_command(ssh, cmd)
            
            if exit_code != 0:
                print(f"⛔ Échec sur {service_name}")
                ssh.close()
                return jsonify({
                    "status": "error",
                    "error": f"{service_name} : {error.strip()}", 
                    "commande": cmd
                }), 500
            print(f"✅ {service_name} opérationnel")
        # Fermez la connexion SSH après l'exécution
        ssh.close()
        # Toujours succès à la fin
        return jsonify({
            "status": "success",
            "vms": results,
            "ip_map": ip_map,
            "errors": {}
        })

    except Exception as e:
        log_step(f"ERREUR FATALE: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "cluster_name": data.get('cluster_name', 'unknown')
        }), 500

# Fonctions utilitaires (à adapter selon votre implémentation)
def create_vmprox_direct(data):
    with app.test_request_context('/create_vmprox', method='POST', json=data):
        return create_vmprox()

def start_vmprox_direct(data):
    with app.test_request_context('/start_vmprox', method='POST', json=data):
        return start_vmprox()

def get_vmip_direct(data):
    """Nouvelle version simplifiée"""
    with app.test_request_context('/get_vmip', method='POST', json=data):
        response = get_vmip()
        return response.get_json(), response.status_code
##############################################################################################
#AYOUB
#################################################################################################################################
#################################################################################################################################
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
