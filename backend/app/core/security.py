"""Fail-closed URL, network and Linux filesystem boundaries."""
import base64
import ctypes
import hashlib
import ipaddress
import os
import re
import secrets
import socket
from pathlib import Path
from urllib.parse import urlsplit


def public_ip(value):
    ip = ipaddress.ip_address(value.split('%')[0])
    if not ip.is_global or (getattr(ip, 'ipv4_mapped', None) and not ip.ipv4_mapped.is_global):
        raise ValueError('Private, reserved and local network addresses are blocked')
    return ip


def validate_url(url, resolve=True):
    try:
        p = urlsplit(url)
        if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
            raise ValueError('Use a public HTTP or HTTPS URL without credentials')
        if p.port not in (None, 80, 443) or len(url) > 8192 or any(ord(c) < 33 for c in url):
            raise ValueError('URL port or characters are not allowed')
        host = p.hostname.encode('idna').decode()
        if host.lower() in ('localhost', 'metadata.google.internal') or host.endswith(('.local', '.localhost', '.internal')):
            raise ValueError('Local hosts are blocked')
        try:
            public_ip(host)
        except ValueError:
            # A literal address must never fall through into hostname resolution.
            try:
                ipaddress.ip_address(host)
            except ValueError:
                if resolve:
                    records = socket.getaddrinfo(host, p.port or 443, type=socket.SOCK_STREAM)
                    if not records:
                        raise ValueError('Host did not resolve')
                    for record in records:
                        public_ip(record[4][0])
            else:
                raise
        return url
    except (UnicodeError, OSError) as exc:
        raise ValueError('URL host could not be validated') from exc


def guard_network():
    """Check the actual address immediately before connect; pin hostname resolution.

    This also applies to redirect destinations, media hosts and extractor API calls.
    No HTTP proxies or external downloaders are enabled in worker configuration.
    """
    original = socket.socket.connect
    def connect(sock, address):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            raise OSError('Unsupported socket family')
        host, port = address[:2]
        if port not in (80, 443):
            raise OSError('Outbound port blocked')
        records = socket.getaddrinfo(host, port, sock.family, socket.SOCK_STREAM)
        for record in records:
            public_ip(record[4][0])
        return original(sock, records[0][4])
    def connect_ex(sock, address):
        try:
            connect(sock, address)
            return 0
        except (OSError, ValueError):
            return 13
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex


def landlock(writable):
    """Kernel-enforced write confinement, including symlinks and rename targets.

    Linux 5.13+ Landlock is mandatory; unsupported kernels fail the job closed.
    Syscall numbers are identical on the supported x86_64 and aarch64 platforms.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 1:
        raise RuntimeError('Linux Landlock is unavailable; downloads require Linux 5.13+ with Landlock enabled')
    # All write operations, including REFER (v2) and TRUNCATE (v3).
    access = sum(1 << bit for bit in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12))
    if abi >= 2:
        access |= 1 << 13
    if abi >= 3:
        access |= 1 << 14
    class Ruleset(ctypes.Structure):
        _fields_ = [('handled_access_fs', ctypes.c_uint64)]
    class Rule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int32)]
    attr = Ruleset(access)
    fd = libc.syscall(444, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'Cannot create filesystem sandbox')
    try:
        for path in writable:
            target = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = Rule(access, target)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0):
                    raise OSError(ctypes.get_errno(), 'Cannot add filesystem boundary')
            finally:
                os.close(target)
        if libc.prctl(38, 1, 0, 0, 0) or libc.syscall(446, fd, 0):
            raise OSError(ctypes.get_errno(), 'Cannot enforce filesystem boundary')
    finally:
        os.close(fd)


def destination_path(value, roots):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Destination must be an absolute path without traversal')
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or not any(resolved.is_relative_to(root) for root in roots):
        raise ValueError('Destination must be inside an explicitly permitted download root')
    return str(resolved)


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()


def verify_password(password, encoded):
    try:
        data = base64.b64decode(encoded)
        digest = hashlib.scrypt(password.encode(), salt=data[:16], n=16384, r=8, p=1)
        return secrets.compare_digest(digest, data[16:])
    except (ValueError, TypeError):
        return False


def safe_template(value):
    # Deliberately expose only plain metadata fields, never Python expressions,
    # field traversal, conversions or gallery-dl extended expression syntax.
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError('Templates must contain 1–256 characters')
    stripped = re.sub(r'\{[a-zA-Z_][a-zA-Z_0-9]*\}', '', value)
    if any(c in stripped for c in '{}/\\:') or '..' in value or value.startswith('.'):
        raise ValueError('Use plain metadata fields such as {filename}.{extension}; no paths or expressions')
    return value
