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
  pm_password     = var.proxmox_password
  pm_tls_insecure = true                                    
}

#############################################################################
# Ressource pour copier l'ISO depuis la machine locale vers Proxmox
resource "null_resource" "copy_iso" {
  provisioner "file" {
    source      = "C:/Users/pc msi/Downloads/lubuntu.iso"  # Chemin sur votre machine locale
    destination = "/var/lib/vz/template/iso/lubuntu.iso"  # Chemin de destination sur le serveur Proxmox

    connection {
      type        = "ssh"
      host        = var.proxmox_ip
      user        = "root"
      password    = var.proxmox_password
      private_key = ""
      agent       = false
      timeout     = "2m"
    }
  }
}

# Créer la VM avec l'ISO
resource "proxmox_vm_qemu" "test_vm" {
  name        = var.hostname
  target_node = var.target_node
  vmid        = var.vm_id  # Ajout de l'ID de la VM


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

  # Spécifier l'ISO pour démarrer la VM
  iso = "/var/lib/vz/template/iso/lubuntu.iso"  # Chemin correct pour l'ISO téléchargée

  boot = "cd"  # Boot sur l'ISO

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

  depends_on = [null_resource.copy_iso]  # Cette ressource dépend de l'ISO copiée
}

