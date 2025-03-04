Vagrant.configure("2") do |config|
    config.vm.provider :proxmox do |proxmox|
      proxmox.endpoint = 'https://192.168.1.150:8006/api2/json'
      proxmox.user_name = 'root@pam'
      proxmox.password = ENV['PROXMOX_PASSWORD'] || 'ton_mot_de_passe'
      proxmox.vm_type = :qemu
      proxmox.template = ENV['VM_TEMPLATE'] || 'ubuntu-24-template'
      proxmox.vm_id_range = 900..910
      proxmox.node_name = 'pve'
  
      # Configuration des ressources
      proxmox.vm_memory = ENV['VM_RAM'] || 2048
      proxmox.vm_cores = ENV['VM_CPU'] || 2
      proxmox.disk_size = ENV['VM_DISK'] || '20G'
    end
  end
  