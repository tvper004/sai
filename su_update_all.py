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

# Locations to copy to
paths = [
    "/etc/easypanel/projects/desarrollo/sophosv2/code",
    "/home/server-data/projects/desarrollo/sophosv2",
    "/home/server-data/projects/desarrollo/sophosv2/code"
]

password = "12345."

for p in paths:
    print(f"--- Actualizando: {p} ---")
    cmd = f"mkdir -p {p} && cp -rf /home/rleon/sophos_update/* {p}/ && chown -R root:root {p} && echo 'OK'"
    print(run_as_root(password, cmd))
