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
  count        = var.create_cluster ? 0 : 1  # Ne pas créer si cluster
  name         = var.hostname
  target_node  = var.target_node
  vmid         = var.vm_id
  clone        = var.template
  full_clone   = false
  agent        = 1

  sockets = 1

  disk {
    size    = "20G"
    type    = "ide"
    storage = "local-lvm"
  }

  os_type = "l26"

  network {
    model  = "virtio"
    bridge = var.network_type == "bridged" ? var.network_bridge : "nat"
  }

  lifecycle {
    ignore_changes = [network]
  }

  onboot = true
}

# Créer ansible-controller (toujours 1 si cluster)
resource "proxmox_vm_qemu" "ansible_controller" {
  count        = var.create_cluster ? 1 : 0
  name         = "ansible-controller"
  target_node  = var.target_node
  vmid         = var.vm_id + 1
  clone        = var.template
  full_clone   = false
  agent        = 1

  sockets = 1

  disk {
    size    = "20G"
    type    = "ide"
    storage = "local-lvm"
  }

  os_type = "l26"

  network {
    model  = "virtio"
    bridge = var.network_type == "bridged" ? var.network_bridge : "nat"
  }

  lifecycle {
    ignore_changes = [network]
  }

  onboot = true
}

# Créer les nodes de cluster (nombre = var.node_count)
resource "proxmox_vm_qemu" "cluster_node" {
  count       = var.create_cluster ? var.node_count : 0
  name        = "Datanode-${count.index + 1}"
  target_node = var.target_node
  vmid        = var.vm_id + 2 + count.index # +2 car vm_id et ansible-controller prennent les 2 premiers
  clone        = var.template
  full_clone  = false
  agent       = 1

  sockets = 1

  disk {
    size    = "20G"
    type    = "ide"
    storage = "local-lvm"
  }

  os_type = "l26"

  network {
    model  = "virtio"
    bridge = var.network_type == "bridged" ? var.network_bridge : "nat"
  }

  lifecycle {
    ignore_changes = [network]
  }

  onboot = true
}

# Provisionnement Ansible
resource "null_resource" "ansible_provisioning" {
  count = var.create_cluster ? 1 : 0

  depends_on = [
    proxmox_vm_qemu.ansible_controller,
    proxmox_vm_qemu.cluster_node
  ]

  provisioner "local-exec" {
    command = <<EOT
      ansible-playbook \
        -i '${join(",", [for vm in proxmox_vm_qemu.ansible_controller : vm.network.0.ip])}' \
        -i '${join(",", [for vm in proxmox_vm_qemu.cluster_node : vm.network.0.ip])}' \
        playbook.yml
    EOT
  }
}