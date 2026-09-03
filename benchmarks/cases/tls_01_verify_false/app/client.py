import requests


def call(url):
    return requests.get(url, timeout=5, verify=False)
