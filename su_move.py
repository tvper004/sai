import pty
import os
import sys
import time

def run_as_root(password, command):
    # Spawn a shell as root using su
    pid, fd = pty.fork()
    
    if pid == 0:
        # Child process: execute su
        os.execvp('su', ['su', '-c', command, 'root'])
    else:
        # Parent process: handle password entry
        output = b""
        time.sleep(1) # Wait for password prompt
        
        # Read a bit to clear buffer
        try:
            output += os.read(fd, 1024)
        except:
            pass
            
        # Send password
        os.write(fd, (password + "\n").encode())
        
        # Read the rest
        while True:
            try:
                data = os.read(fd, 1024)
                if not data: break
                output += data
            except EOFError:
                break
            except OSError:
                break
        
        return output.decode(errors='ignore')

# The command to move files
cmd = "cp -rf /home/rleon/sophos_update/* /etc/easypanel/projects/desarrollo/sophosv2/volumes/code/ && chown -R root:root /etc/easypanel/projects/desarrollo/sophosv2/volumes/code/ && echo 'SUCCESS_MOVE'"
password = "12345."

print(run_as_root(password, cmd))
