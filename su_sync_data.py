import pty
import os
import time

def run_as_root(password, command):
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp('su', ['su', '-c', command, 'root'])
    else:
        time.sleep(1)
        os.write(fd, (password + "\n").encode())
        output = b""
        while True:
            try:
                data = os.read(fd, 1024)
                if not data: break
                output += data
            except:
                break
        return output.decode(errors='ignore')

# Copiar data completa a la ruta del Host de Easypanel
target_dir = "/etc/easypanel/projects/desarrollo/sophosv2/code/data"
cmd = f"mkdir -p {target_dir} && cp -rf /home/rleon/sophos_update/data/* {target_dir}/ && chown -R root:root {target_dir} && echo 'DATA_SYNC_OK'"
password = "12345."
print(run_as_root(password, cmd))
