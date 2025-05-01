terraform {
  required_providers {
    proxmox = {
      source  = "Telmate/proxmox"
      version = "2.9.11"
    }
  }
}

provider "proxmox" {
  pm_api_url      = "https://${var.proxmox_ip}:8006/api2/json"
  pm_user         = "root@pam"
  pm_password     = var.password
  pm_tls_insecure = true
}

# Créer une seule machine virtuelle si create_cluster est false
resource "proxmox_vm_qemu" "test_vm" {
  count        = var.create_cluster ? 0 : 1  # Ne pas créer cette ressource si create_cluster est true
  name         = var.hostname
  target_node  = var.target_node
  vmid         = var.vm_id
  clone        = var.template
  full_clone   = true
  agent        = 1

 
  sockets      = 1

  disk {
    size    = "20G"
    type    = "ide"
    storage = "local-lvm"
  }

  os_type = "l26"

  network {
    model  = "virtio"
    bridge = var.network_type == "bridged" ? var.network_bridge : "nat"  # Choix du réseau
  }

  lifecycle {
    ignore_changes = [network]
  }

  onboot = true
}

# Créer un cluster si create_cluster est true
resource "proxmox_vm_qemu" "ansible_controller" {
  count        = var.create_cluster ? 1 : 0  # Créer cette ressource uniquement si create_cluster est true
  name         = "ansible-controller"
  target_node  = var.target_node
  vmid         = var.vm_id + 1
  clone        = var.template
  full_clone   = true
  agent        = 1


  sockets      = 1

  disk {
    size    = "20G"
    type    = "ide"
    storage = "local-lvm"
  }

  os_type = "l26"

  network {
    model  = "virtio"
    bridge = var.network_type == "bridged" ? var.network_bridge : "nat"  # Choix du réseau
  }

  lifecycle {
    ignore_changes = [network]
  }

  onboot = true
}

resource "proxmox_vm_qemu" "cluster_node" {
  count       = var.create_cluster ? 3 : 0  # Créer 3 nœuds uniquement si create_cluster est true
  name        = "cluster-node-${count.index + 1}"
  target_node = var.target_node
  vmid        = var.vm_id + 2 + count.index
  clone       = var.template
  full_clone  = true
  agent       = 1


  sockets     = 1

  disk {
    size    = "20G"
    type    = "ide"
    storage = "local-lvm"
  }

  os_type = "l26"

  network {
    model  = "virtio"
    bridge = var.network_type == "bridged" ? var.network_bridge : "nat"  # Choix du réseau
  }

  lifecycle {
    ignore_changes = [network]
  }

  onboot = true
}

# Provisionnement Ansible (uniquement si un cluster est créé)
resource "null_resource" "ansible_provisioning" {
  count = var.create_cluster ? 1 : 0  # Exécuter uniquement si create_cluster est true

  depends_on = [proxmox_vm_qemu.cluster_node]

  provisioner "local-exec" {
    command = <<EOT
      ansible-playbook -i ${join(",", proxmox_vm_qemu.cluster_node[*].network.0.ip)} playbook.yml
    EOT
  }
}