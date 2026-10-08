import base64
import json
import os
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://www.vpngate.net/api/iphone/"

# "udp", "tcp" ya "any"
WANTED_PROTO = "udp"

CANDIDATES = 200   # itne servers ko check karenge
PER_COUNTRY = 3    # har mulk ke kitne servers
MAX_SERVERS = 60   # kul servers


def clean_config(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        # khali lines, comments aur data-ciphers hata do (file chhoti rahe)
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if s.startswith("data-ciphers"):
            continue
        out.append(line.rstrip())
    return "\n".join(out) + "\n"


def get_proto(text):
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("proto "):
            return s.split()[1].lower()
    return "udp"


def get_remote(text):
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("remote "):
            p = s.split()
            if len(p) >= 3 and p[2].isdigit():
                return p[1], int(p[2])
    return None, None


def probe_udp(host, port, timeout=3.0):
    # OpenVPN ka pehla handshake packet bhej kar dekhte hain ke server jawab deta hai
    try:
        packet = bytes([0x38]) + os.urandom(8) + bytes([0]) + bytes(4)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(packet, (host, port))
            data, _ = s.recvfrom(1024)
            return len(data) > 0
    except Exception:
        return False


def probe_tcp(host, port, timeout=4.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def is_alive(server):
    host, port = server["_host"], server["_port"]
    if host is None:
        return False
    if server["proto"].startswith("tcp"):
        return probe_tcp(host, port)
    return probe_udp(host, port)


def main():
    with urllib.request.urlopen(API, timeout=120) as r:
        raw = r.read().decode("utf-8", errors="replace")

    lines = [
        l for l in raw.splitlines()
        if l and not l.startswith("*") and not l.startswith("#")
    ]

    servers = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 15:
            continue
        try:
            config = base64.b64decode(parts[-1].strip()).decode(
                "utf-8", errors="replace"
            )

            proto = get_proto(config)

            if WANTED_PROTO != "any" and not proto.startswith(WANTED_PROTO):
                continue

            host, port = get_remote(config)

            servers.append(
                {
                    "hostName": parts[0],
                    "country": parts[5],
                    "countryCode": parts[6],
                    "score": int(parts[2]),
                    "speedMbps": round(int(parts[4]) / 1_000_000),
                    "proto": proto,
                    "config": clean_config(config),
                    "_host": host,
                    "_port": port,
                }
            )
        except Exception:
            continue

    servers.sort(key=lambda s: s["score"], reverse=True)
    candidates = servers[:CANDIDATES]

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(is_alive, candidates))

    alive = [s for s, ok in zip(candidates, results) if ok]
    print(f"Checked {len(candidates)} servers, alive: {len(alive)}")

    if not alive:
        print("Warning: no server answered, using the unchecked list")
        alive = candidates

    per_country = {}
    picked = []
    for s in alive:
        n = per_country.get(s["countryCode"], 0)
        if n >= PER_COUNTRY:
            continue
        per_country[s["countryCode"]] = n + 1
        picked.append(s)

    picked = picked[:MAX_SERVERS]

    if not picked:
        raise SystemExit("No servers found, keeping the old file")

    out = [
        {k: v for k, v in s.items() if not k.startswith("_")} for s in picked
    ]

    with open("servers.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"Saved {len(out)} servers")


main()
