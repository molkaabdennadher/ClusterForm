import paramiko
import os
from pathlib import Path

# Configuration des nœuds
ANSIBLE_CONTROLLER = "192.168.1.24"
NAMENODE = "192.168.1.20"
DATANODE1 = "192.168.1.23"
DATANODE2 = "192.168.1.19"

# Configuration des hôtes
NODES = {
    "namenode": NAMENODE,
    "datanodes": [DATANODE1, DATANODE2],
    "resource_manager": NAMENODE
}

# Credentials
USER = "molka"
PASSWORD = "molka"  # À changer en production

# Chemins et versions
HADOOP_VERSION = "3.3.1"
JAVA_VERSION = "11"

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
            username=USER, 
            password=PASSWORD,
            look_for_keys=False,
            allow_agent=False,
            timeout=30
        )
        return ssh
    except Exception as e:
        print(f"Échec de connexion SSH à {host}: {str(e)}")
        return None

def install_hadoop_on_controller():
    """Installe Hadoop sur le nœud contrôleur."""
    try:
        # Créer une connexion SSH vers le contrôleur Ansible
        ssh = create_ssh_client(ANSIBLE_CONTROLLER)
        if not ssh:
            print("Échec de la connexion SSH.")
            return False
        # Télécharger Hadoop
        commands = [
						'sudo apt update && sudo apt install -y wget openjdk-11-jdk net-tools sshpass pdsh',
            'sudo apt install -y python3 python3-pip',
            'sudo apt install -y ansible',

            #########################################jareb
            'mkdir -p ~/.ssh',
            '[ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa',
            f'ssh-keyscan -H {ANSIBLE_CONTROLLER} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {NAMENODE} >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {DATANODE1 } >> ~/.ssh/known_hosts',
            f'ssh-keyscan -H {DATANODE2} >> ~/.ssh/known_hosts',
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{ANSIBLE_CONTROLLER}',
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{NAMENODE}',
            f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{DATANODE1 }',
             f'sshpass -p "molka" ssh-copy-id -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa.pub molka@{DATANODE2}',

            'chmod 600 ~/.ssh/id_rsa',
            'chmod 644 ~/.ssh/id_rsa.pub',
            'chmod 700 ~/.ssh',
            ############################################
            'wget https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz',
            'sudo mv hadoop-3.3.1.tar.gz /opt',
            'sudo chown -R molka:molka /opt',
            'java -version',
            'ansible --version',
            # 📂 Créer le dossier "templates" pour Ansible
            'mkdir -p ~/templates',
            
            # 📝 Ajouter les fichiers de configuration Hadoop
            'echo "<configuration>\n  <property>\n    <name>fs.defaultFS</name>\n    <value>hdfs://{{ namenode_hostname }}:9000</value>\n  </property>\n</configuration>" > ~/templates/core-site.xml.j2',
            
            'echo "<configuration>\n  <property>\n    <name>dfs.replication</name>\n    <value>2</value>\n  </property>\n</configuration>" > ~/templates/hdfs-site.xml.j2',
            
            'echo "<configuration>\n  <property>\n    <name>yarn.resourcemanager.hostname</name>\n    <value>{{ namenode_hostname }}</value>\n  </property>\n</configuration>" > ~/templates/yarn-site.xml.j2',
            
            'echo "<configuration>\n  <property>\n    <name>mapreduce.framework.name</name>\n    <value>yarn</value>\n  </property>\n</configuration>" > ~/templates/mapred-site.xml.j2',

            # 📝 Fichier masters.j2
            'echo "{{ groups[\'namenode\'][0] }}" > ~//templates/masters.j2',

            # 📝 Fichier workers.j2
            'echo "{% for worker in groups[\'datanodes\'] %}\n{{ worker }}\n{% endfor %}" > ~/templates/workers.j2',

            # 📝 Fichier hosts.j2
            'echo "# ANSIBLE GENERATED CLUSTER HOSTS\n{% for host in groups[\'all\'] %}\n{{ hostvars[host][\'ansible_host\'] }} {{ host }}\n{% endfor %}" > ~/templates/hosts.j2',

            # 📝 Créer le fichier inventory.ini
            f'echo "[namenode]\n{NAMENODE} ansible_host={NAMENODE}\n\n[datanodes]\n{DATANODE1} ansible_host={DATANODE1}\n{DATANODE2} ansible_host={DATANODE2}\n\n[all:vars]\nansible_user=molka\nansible_ssh_private_key_file=~/.ssh/id_rsa\nansible_ssh_common_args=\'-o StrictHostKeyChecking=no\'\nansible_python_interpreter=/usr/bin/python3" > ~/inventory.ini',

            # Créer le fichier inventory.ini
						f'echo """[namenode]\n{NAMENODE} ansible_host={NAMENODE}\n\n[datanodes]\n{DATANODE1} ansible_host={DATANODE1}\n{DATANODE2} ansible_host={DATANODE2}\n\n[resource_manager]\n{NODES["resource_manager"]} ansible_host={NODES["resource_manager"]}\n\n[all:vars]\nansible_user=molka\nansible_ssh_private_key_file=~/.ssh/id_rsa\nansible_ssh_common_args=\'-o StrictHostKeyChecking=no\'\nansible_python_interpreter=/usr/bin/python3""" > ~/inventory.ini'
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

    - name: Extraire Hadoop sur chaque nœud
      become: yes
      shell: |
        mkdir -p /opt/hadoop
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
          export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/biny
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
            cmd = f'cat > ~/{filename} <<EOF\n{content}\nEOF'
            exit_status, output, error = execute_ssh_command(ssh, cmd)
            if exit_status != 0:
                print(f"Erreur création {filename}: {error}")
                return False

        # Exécuter les playbooks Ansible
        for filename in playbooks.keys():
            cmd = f'ansible-playbook -i ~/inventory.ini /{filename}'
            exit_status, output, error = execute_ssh_command(ssh, cmd)
            if exit_status != 0:
                print(f"Erreur exécution {filename}: {error}")
                return False

        print("Installation et déploiement Hadoop réussis!")
        return True

    except Exception as e:
        print(f"Erreur lors de l'installation d'Hadoop: {e}")
        return False
    

def main():
    
    try:
        # Installer Hadoop et vérifier le succès
        if install_hadoop_on_controller():
            print("Hadoop installé avec succès sur le contrôleur.")
            print("Fichier inventory.ini créé avec succès.")
      
        else:
            print("Échec de l'installation de Hadoop sur le contrôleur.")
    finally:
        ssh.close()

def test_hadoop_deployment():
    """Test complet du déploiement Hadoop"""
    # 1. Installer Hadoop sur le contrôleur
    assert install_hadoop_on_controller(), "Échec de l'installation sur le contrôleur"

if __name__ == "__main__":
    print("=== Démarrage du déploiement Hadoop ===")
    test_hadoop_deployment()
    print("=== Déploiement terminé ===")
    print("=== Démarrage de la configuration du cluster Hadoop ===")
    main()
    print("=== Configuration terminée ===")

    #############################################################################################