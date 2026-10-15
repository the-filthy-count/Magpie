"""Trusted media launcher: inherit Landlock and deny networking before exec."""
import ctypes
import errno
import os
import platform
import sys
import signal
from pathlib import Path


def deny_network():
    """Install a fail-closed seccomp filter on AMD64/ARM64, inherited by FFmpeg.

    Python downloads remote media through Magpie's guarded sockets. Media
    helpers process local files or stdin; none may create/use network sockets.
    """
    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64'):
        arch, calls = 0xc000003e, (41, 42, 44, 46, 53)
    elif machine in ('aarch64', 'arm64'):
        arch, calls = 0xc00000b7, (198, 199, 203, 206, 211)
    else:
        raise RuntimeError('Unsupported FFmpeg sandbox architecture')
    class Instruction(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte),
                    ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint32)]
    class Program(ctypes.Structure):
        _fields_ = [('len', ctypes.c_ushort), ('filter', ctypes.POINTER(Instruction))]
    # Validate syscall architecture and reject x32 ABI before matching numbers.
    instructions = [(0x20, 0, 0, 4), (0x15, 1, 0, arch), (0x06, 0, 0, 0x80000000),
                    (0x20, 0, 0, 0), (0x45, 0, 1, 0x40000000), (0x06, 0, 0, 0x80000000)]
    for call in calls:
        instructions.extend([(0x15, 0, 1, call), (0x06, 0, 0, 0x50000 | errno.EPERM)])
    instructions.append((0x06, 0, 0, 0x7fff0000))
    filters = (Instruction * len(instructions))(*(Instruction(*i) for i in instructions))
    program = Program(len(filters), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(program)):
        raise OSError(ctypes.get_errno(), 'Cannot install local-only media tool sandbox')


def restrict_files(root):
    """FFmpeg may read media and system libraries, and write only media."""
    from app.core.security import landlock
    root = Path(root).resolve(strict=True)
    landlock([root])
    libc = ctypes.CDLL(None, use_errno=True)
    class Ruleset(ctypes.Structure):
        _fields_ = [('access', ctypes.c_uint64)]
    class Rule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('access', ctypes.c_uint64), ('fd', ctypes.c_int32)]
    read_file, read_dir = 1 << 2, 1 << 3
    attr = Ruleset(read_file | read_dir)
    fd = libc.syscall(444, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'Cannot create media read sandbox')
    try:
        for path in (root, Path('/usr'), Path('/lib'), Path('/lib64'), Path('/etc/ld.so.cache'), Path('/etc/ssl/openssl.cnf'), Path('/dev/null'), Path('/dev/urandom')):
            if not path.exists():
                continue
            target = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = Rule(read_file | (read_dir if path.is_dir() else 0), target)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0):
                    raise OSError(ctypes.get_errno(), 'Cannot add media read boundary')
            finally:
                os.close(target)
        if libc.syscall(446, fd, 0):
            raise OSError(ctypes.get_errno(), 'Cannot enforce media read boundary')
    finally:
        os.close(fd)


def main():
    tool = Path(sys.argv[0]).name
    if tool not in ('ffmpeg', 'ffprobe', 'node'):
        raise SystemExit('Only bundled media helpers are permitted')
    parent = os.getppid()
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != parent:
        raise SystemExit('Media worker parent exited')
    restrict_files(os.environ['MAGPIE_MEDIA_ROOT'])
    deny_network()
    # Absolute package-managed binaries; never a path from a URL or job setting.
    if tool == 'node':
        # Node's permission mode also denies child processes, worker threads,
        # native addons and filesystem APIs in challenge code.
        os.execv('/usr/local/libexec/magpie-node-real', ['node', '--permission', *sys.argv[1:]])
    os.execv('/usr/bin/' + tool, [tool, *sys.argv[1:]])
