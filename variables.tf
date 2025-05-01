variable "proxmox_ip" {
  description = "Adresse IP du serveur Proxmox"
  type        = string
}
variable "target_node" {
  description = "Nom du nœud Proxmox où la VM sera créée"
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

variable "vm_id" {
  description = "ID de la machine virtuelle"
  type        = number
}
variable "create_cluster" {
  description = "Définir à true pour créer un cluster, false pour une seule machine virtuelle"
  type        = bool
  default     = false
}

variable "template" {
  description = "Template to use for the VM"
  type        = string
  default     = "ubuntu-template"
}
variable "network_type" {
  description = "Type of network (nat, bridged, etc.)"
  type        = string
  default     = "nat"
}

variable "network_bridge" {
  description = "Bridge to use for the network (if bridged)"
  type        = string
  default     = "vmbr0"
}




