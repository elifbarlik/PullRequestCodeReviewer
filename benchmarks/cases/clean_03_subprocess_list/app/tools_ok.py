import subprocess
import shlex


def ping(host):
    subprocess.run(["ping", "-c", "1", host], check=True, timeout=5)
