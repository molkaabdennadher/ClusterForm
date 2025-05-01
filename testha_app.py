import paramiko
import os
from pathlib import Path

# Configuration des nœuds
ANSIBLE_CONTROLLER = "192.168.100.151"
NAMENODE = "192.168.100.148"
DATANODE1 = "192.168.100.149"
DATANODE2 = "192.168.100.150"
STANDBY = "192.168.100.152"

# Configuration des hôtes
NODES = {
    "namenode": [NAMENODE, STANDBY],
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
            
           'wget https://archive.apache.org/dist/zookeeper/zookeeper-3.6.3/apache-zookeeper-3.6.3-bin.tar.gz',
           'sudo mv apache-zookeeper-3.6.3-bin.tar.gz /tmp',

           # Copier vers Namenode et Standby
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{NAMENODE}:/tmp/',
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{STANDBY}:/tmp/',
            f'scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /tmp/apache-zookeeper-3.6.3-bin.tar.gz molka@{DATANODE1}:/tmp/',

            # Créer /etc/zookeeper et déplacer le fichier
            f'ssh -o StrictHostKeyChecking=no molka@{NAMENODE} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',
            f'ssh -o StrictHostKeyChecking=no molka@{STANDBY} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',
            f'ssh -o StrictHostKeyChecking=no molka@{DATANODE1} "sudo mkdir -p /etc/zookeeper && sudo mv /tmp/apache-zookeeper-3.6.3-bin.tar.gz /etc/zookeeper/"',

            # Extraire Zookeeper
            f'ssh -o StrictHostKeyChecking=no molka@{NAMENODE} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{STANDBY} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',
            f'ssh -o StrictHostKeyChecking=no molka@{DATANODE1} "cd /etc/zookeeper && sudo tar xzf apache-zookeeper-3.6.3-bin.tar.gz --strip-components=1"',

            # Renommer zoo_sample.cfg en zoo.cfg
            f'ssh -o StrictHostKeyChecking=no molka@{NAMENODE} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',
            f'ssh -o StrictHostKeyChecking=no molka@{STANDBY} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',
            f'ssh -o StrictHostKeyChecking=no molka@{DATANODE1} "sudo mv /etc/zookeeper/conf/zoo_sample.cfg /etc/zookeeper/conf/zoo.cfg"',

            # Créer d'abord le dossier puis écrire l'ID
            f'ssh -o StrictHostKeyChecking=no molka@{NAMENODE} "sudo mkdir -p /var/lib/zookeeper && echo 1 | sudo tee /var/lib/zookeeper/myid"',
            f'ssh -o StrictHostKeyChecking=no molka@{STANDBY} "sudo mkdir -p /var/lib/zookeeper && echo 2 | sudo tee /var/lib/zookeeper/myid"',
            f'ssh -o StrictHostKeyChecking=no molka@{DATANODE1} "sudo mkdir -p /var/lib/zookeeper && echo 2 | sudo tee /var/lib/zookeeper/myid"',

            ############################################
          ############################################
            'wget https://archive.apache.org/dist/hadoop/common/hadoop-3.3.1/hadoop-3.3.1.tar.gz',
            'sudo mv hadoop-3.3.1.tar.gz /opt',
            'sudo chown -R molka:molka /opt',

            'echo "export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64" >> /home/molka/.bashrc',
            'echo "export HADOOP_HOME=/opt/hadoop" >> /home/molka/.bashrc',
            'echo "export PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin" >> /home/molka/.bashrc',

            # Copie du .bashrc sur les différents nœuds
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{ANSIBLE_CONTROLLER}:/home/molka/.bashrc',
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{NAMENODE}:/home/molka/.bashrc',
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{STANDBY}:/home/molka/.bashrc',
            f'sshpass -p "molka" scp -o StrictHostKeyChecking=no /home/molka/.bashrc molka@{DATANODE1}:/home/molka/.bashrc',
             ############################################

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
            'echo "tickTime=2000\ninitLimit=10\nsyncLimit=5\ndataDir=/var/lib/zookeeper\nclientPort=2181\n{% for zk in groups[\'zookeeper\'] %}server.{{ loop.index }}={{ hostvars[zk].ansible_host }}:2888:3888\n{% endfor %}" > ~/templates/zoo.cfg.j2',

            # hosts.j2
            'echo "# ANSIBLE GENERATED HOSTS FILE\n{% for host in groups[\'all\'] %}{{ hostvars[host].ansible_host }} {{ host }}\n{% endfor %}" > ~/templates/hosts.j2',
            
            # Créer le fichier inventory.ini
            f'echo """[namenode]\n{NAMENODE} ansible_host={NAMENODE}\n{STANDBY} ansible_host={STANDBY}\n\n[standby]\n{STANDBY} ansible_host={STANDBY}\n\n[datanodes]\n{DATANODE1} ansible_host={DATANODE1}\n{DATANODE2} ansible_host={DATANODE2}\n\n[resourcemanager]\n{NAMENODE} ansible_host={NAMENODE}\n\n[resourcemanager_standby]\n{STANDBY} ansible_host={STANDBY}\n\n[zookeeper]\n{NAMENODE} ansible_host={NAMENODE}\n{STANDBY} ansible_host={STANDBY}\n{DATANODE1} ansible_host={DATANODE1}\n\n[journalnode]\n{NAMENODE} ansible_host={NAMENODE}\n{STANDBY} ansible_host={STANDBY}\n{DATANODE1} ansible_host={DATANODE1}\n\n[all:vars]\nansible_user=molka\nansible_ssh_private_key_file=~/.ssh/id_rsa\nansible_ssh_common_args=\'-o StrictHostKeyChecking=no\'\nansible_python_interpreter=/usr/bin/python3""" > ~/inventory.ini'
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

    # 3. Transférer Hadoop via SCP
    - name: Transférer Hadoop via SCP
      command: >
        scp -r -i /home/molka/.ssh/id_rsa
        -o StrictHostKeyChecking=no
        -o UserKnownHostsFile=/dev/null
        /opt/hadoop-3.3.1.tar.gz 
        molka@{{ inventory_hostname }}:/tmp/
      delegate_to: localhost

    # 4. Déplacer l'archive
    - name: Déplacer l'archive
      become: yes
      shell: |
        mv /tmp/hadoop-3.3.1.tar.gz /opt/
        chown molka:molka /opt/hadoop-3.3.1.tar.gz

    # 5. Extraire Hadoop sur chaque nœud
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
    ssh = None
    try:
        # Installer Hadoop et vérifier le succès
        if install_hadoop_on_controller():
            print("Hadoop installé avec succès sur le contrôleur.")
            print("Fichier inventory.ini créé avec succès.")
        else:
            print("Échec de l'installation de Hadoop sur le contrôleur.")
    finally:
        if ssh:
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