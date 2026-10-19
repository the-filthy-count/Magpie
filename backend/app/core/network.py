"""Small cached lookup of the container's outbound public network identity."""
import ipaddress
import threading
import time
from datetime import datetime, timezone
import requests


def fetch_network():
    # Workers ignore proxy environment variables too. Do not report the browser
    # IP or a proxy used only by this diagnostic request. No user-supplied URLs.
    with requests.Session() as session:
        session.trust_env = False
        with session.get('https://ipwho.is/', timeout=(3, 5), allow_redirects=False, stream=True) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('Unexpected IP provider response')
            body = bytearray()
            for chunk in response.iter_content(4096):
                body.extend(chunk)
                if len(body) > 32768:
                    raise ValueError('IP provider response too large')
    import json
    data = json.loads(body)
    address = ipaddress.ip_address(data['ip'])
    if data.get('success') is not True or not address.is_global:
        raise ValueError('Invalid public IP response')
    def text(value):
        return value[:120] if isinstance(value, str) else None
    connection = data.get('connection')
    if not isinstance(connection, dict):
        connection = {}
    return dict(ip=str(address), country=text(data.get('country')), city=text(data.get('city')),
                isp=text(connection.get('isp') or connection.get('org')),
                checked_at=datetime.now(timezone.utc).isoformat())


class NetworkInfo:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = None
        self.attempted = None
        self.failed = False

    def get(self):
        with self.lock:
            now = time.monotonic()
            ttl = 30 if self.failed else 300
            if self.attempted is None or now - self.attempted >= ttl:
                try:
                    self.value = fetch_network()
                    self.failed = False
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    self.failed = True
                self.attempted = time.monotonic()
            return {**(self.value or dict(ip=None, country=None, city=None, isp=None, checked_at=None)),
                    'stale': self.failed, 'error': 'Network information is temporarily unavailable' if self.failed else None}
