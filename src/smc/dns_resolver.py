"""DNS via 1.1.1.1 (Cloudflare) untuk host bursa — hindari DNS-block/poisoning ISP.

Banyak ISP (mis. Indonesia) memblokir Binance/Bybit di level DNS: resolver bawaan mengembalikan IP
mati/terpoison -> ConnectTimeout meski internet sehat. Modul ini me-resolve host bursa lewat query
DNS langsung ke 1.1.1.1 (UDP:53, stdlib murni — tanpa dependensi), lalu mem-pin `socket.getaddrinfo`
agar koneksi memakai IP yang benar. SNI/sertifikat TETALp memakai hostname asli (getaddrinfo hanya
menukar IP tujuan), jadi TLS tetap valid. Berlaku untuk urllib (adapter langsung) DAN ccxt
(requests->urllib3->socket) karena patch di level socket global.

Terbukti: fapi.binance.com via DNS sistem = timeout; via 1.1.1.1 -> IP benar -> PING 200 (~0.14s).

Nonaktif via env `DOH_DISABLE=1`. Host di luar daftar bursa lewat resolver normal (tak disentuh).
"""
from __future__ import annotations

import os
import socket
import struct
import threading
import time

DNS_SERVERS = ("1.1.1.1", "1.0.0.1")     # Cloudflare primer + sekunder
# suffix host bursa yang di-resolve lewat 1.1.1.1 (data + ccxt Bybit/OKX + testnet)
EXCHANGE_HOSTS = (
    "binance.com", "binance.vision", "binancefuture.com",
    "bybit.com", "bybit-tech.com", "bytick.com",
    "okx.com", "okex.com",
)

_cache: dict = {}                         # host -> (ip, expiry_monotonic)
_lock = threading.Lock()
_orig_getaddrinfo = socket.getaddrinfo
_installed = False


def _query_a(host: str, server: str, timeout: float = 4.0):
    """Query A-record lewat UDP DNS ke `server`. Return (ip, ttl) atau None. Stdlib murni."""
    q = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)   # id, RD, qd=1
    for part in host.split("."):
        q += bytes([len(part)]) + part.encode()
    q += b"\x00" + struct.pack(">HH", 1, 1)                  # QTYPE=A, QCLASS=IN
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(q, (server, 53))
        data, _ = s.recvfrom(1024)
    finally:
        s.close()
    ancount = struct.unpack(">H", data[6:8])[0]
    if not ancount:
        return None
    idx = 12
    while data[idx] != 0:                                    # lewati QNAME
        idx += data[idx] + 1
    idx += 5                                                 # null + QTYPE + QCLASS
    for _ in range(ancount):
        if data[idx] & 0xC0 == 0xC0:                         # nama terkompresi (pointer)
            idx += 2
        else:
            while data[idx] != 0:
                idx += data[idx] + 1
            idx += 1
        rtype, _rclass, ttl, rdlen = struct.unpack(">HHIH", data[idx:idx + 10])
        idx += 10
        if rtype == 1 and rdlen == 4:                        # A record IPv4
            return ".".join(str(b) for b in data[idx:idx + 4]), ttl
        idx += rdlen
    return None


def resolve(host: str, timeout: float = 4.0):
    """IP untuk `host` via 1.1.1.1 (cache TTL, thread-safe). None bila gagal semua server."""
    now = _time_monotonic()
    with _lock:
        c = _cache.get(host)
        if c and c[1] > now:
            return c[0]
    for server in DNS_SERVERS:
        try:
            r = _query_a(host, server, timeout=timeout)
        except Exception:  # noqa: BLE001
            r = None
        if r:
            ip, ttl = r
            with _lock:
                _cache[host] = (ip, now + max(60.0, min(float(ttl), 3600.0)))
            return ip
    return None


def _time_monotonic() -> float:
    return time.monotonic()


def _is_exchange(host: str) -> bool:
    return isinstance(host, str) and any(
        host == h or host.endswith("." + h) for h in EXCHANGE_HOSTS)


def _patched_getaddrinfo(host, *args, **kwargs):
    if _is_exchange(host):
        ip = resolve(host)
        if ip:
            return _orig_getaddrinfo(ip, *args, **kwargs)   # konek ke IP; SNI tetap hostname asli
    return _orig_getaddrinfo(host, *args, **kwargs)


def install() -> bool:
    """Pasang patch getaddrinfo (idempoten). Return True bila aktif. No-op bila DOH_DISABLE=1."""
    global _installed
    if _installed or os.environ.get("DOH_DISABLE") == "1":
        return _installed
    socket.getaddrinfo = _patched_getaddrinfo
    _installed = True
    return True
