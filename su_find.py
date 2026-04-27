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

# Search for the correct path
cmd = "find /etc/easypanel -name app.py | grep sophosv2"
password = "12345."
print(run_as_root(password, cmd))
