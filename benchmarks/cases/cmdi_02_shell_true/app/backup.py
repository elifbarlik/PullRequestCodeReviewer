import subprocess


def archive(name):
    subprocess.run("tar czf " + name + ".tgz data/", shell=True, check=True)
