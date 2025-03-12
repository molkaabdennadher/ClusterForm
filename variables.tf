variable "proxmox_ip" {
  description = "Adresse IP du serveur Proxmox"
  type        = string
}
variable "target_node" {
  description = "Nom du nœud Proxmox où la VM sera créée"
  type        = string
}
variable "network_ip" {
  description = "Adresse IP de la VM"
  type        = string
}
variable "password" {
  description = "Mot de passe de l'utilisateur Proxmox"
  type        = string
  sensitive   = true
}

variable "hostname" {
  description = "Nom de la machine virtuelle"
  type        = string
}

variable "ram" {
  description = "Mémoire RAM de la VM (en Mo)"
  type        = number
}

variable "cpu" {
  description = "Nombre de cœurs CPU"
  type        = number
}

variable "vm_id" {
  description = "ID de la machine virtuelle"
  type        = number
}




