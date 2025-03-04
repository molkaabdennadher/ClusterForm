import paramiko

def execute_command():
    ip = "172.20.10.3"
    username = "molka"
    password = "1234"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(ip, username=username, password=password)
        
        command = "terraform init && terraform apply -auto-approve"
        stdin, stdout, stderr = client.exec_command(command)

        print(stdout.read().decode(errors='ignore'))
        print(stderr.read().decode(errors='ignore'))


    except Exception as e:
        print(f"Échec de la connexion : {e}")
    finally:
        client.close()

execute_command()
