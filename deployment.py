# scripts/deployment.py
import paramiko
import os
from config import azure_config

# def deploy_website(ip_address, folder_path):
#     ssh = paramiko.SSHClient()
#     ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#     ssh.connect(ip_address, username=azure_config.vm_username, password=azure_config.vm_password)

#     # Install Nginx and set permissions
#     commands = [
#         "sudo apt update",
#         "sudo apt install -y nginx",
#         "sudo chown -R $(whoami):$(whoami) /var/www/html"
#     ]
#     for command in commands:
#         ssh.exec_command(command)

#     # Transfer all files in the specified folder
#     sftp = ssh.open_sftp()
#     for filename in os.listdir(folder_path):
#         local_path = os.path.join(folder_path, filename)
#         remote_path = f"/var/www/html/{filename}"
#         sftp.put(local_path, remote_path)

#     sftp.close()
#     ssh.close()



def deploy_website(ip_address, folder_path, vm_username, vm_password):

    print(f"getting the admin username:{vm_username}")
    print(f"getting the admin password:{vm_password}")

    # Setup SSH connection
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip_address, username=vm_username, password=vm_password)

    # Install Nginx (check if installed first)
    commands = [
        "sudo apt update",
        "dpkg -l | grep nginx || sudo apt install -y nginx",  # Only install if not installed
        "sudo chown -R www-data:www-data /var/www/html",  # Assuming Nginx runs as 'www-data'
        "sudo systemctl restart nginx"  # Restart Nginx to apply changes
    ]
    for command in commands:
        stdin, stdout, stderr = ssh.exec_command(command)
        # Optionally, log the output for debugging
        print(stdout.read().decode())

    # Transfer all files in the specified folder
    sftp = ssh.open_sftp()
    for filename in os.listdir(folder_path):
        local_path = os.path.join(folder_path, filename)
        remote_path = f"/var/www/html/{filename}"
        if os.path.isdir(local_path):
            # If the local path is a directory, make sure to create the corresponding directory on the remote machine
            ssh.exec_command(f"mkdir -p {remote_path}")
            continue
        try:
            sftp.put(local_path, remote_path)
            print(f"Successfully uploaded: {filename}")
        except Exception as e:
            print(f"Error uploading {filename}: {e}")
    sftp.close()

    # Close SSH connection
    ssh.close()
