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

# Créer la VM avec l'ISO
resource "proxmox_vm_qemu" "test_vm" {
  name        = var.hostname
  target_node = var.target_node
  vmid        = var.vm_id # Ajout de l'ID de la VM
  clone       = "ubuntu-template"  # Nom du template source
  full_clone  = true
  agent       = 1

  # Configuration du hardware
  memory      = var.ram
  cores       = var.cpu
  vcpus       = var.cpu  
  sockets     = 1
  disk {
    size    = "20G"
    type    = "ide"
    storage = "local-lvm"
  }
  os_type = "l26"

  # Réseau
  network {
    model  = "virtio"
    bridge = "vmbr0"
  }

  lifecycle {
    ignore_changes = [network]
  }
  
  # Auto-start
  onboot = true

}

