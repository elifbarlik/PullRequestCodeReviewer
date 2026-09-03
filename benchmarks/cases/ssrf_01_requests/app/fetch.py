import requests


def proxy(url):
    return requests.get(url, timeout=5).text
