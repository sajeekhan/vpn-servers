import base64
import json
import urllib.request

API = "https://www.vpngate.net/api/iphone/"


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
            servers.append(
                {
                    "hostName": parts[0],
                    "country": parts[5],
                    "countryCode": parts[6],
                    "score": int(parts[2]),
                    "speedMbps": round(int(parts[4]) / 1_000_000),
                    "config": clean_config(config),
                }
            )
        except Exception:
            continue

    # Sab se achhe score wale pehle, har mulk ke sirf top 3
    servers.sort(key=lambda s: s["score"], reverse=True)

    per_country = {}
    picked = []
    for s in servers:
        n = per_country.get(s["countryCode"], 0)
        if n >= 3:
            continue
        per_country[s["countryCode"]] = n + 1
        picked.append(s)

    picked = picked[:60]

    if not picked:
        raise SystemExit("No servers found, keeping the old file")

    with open("servers.json", "w", encoding="utf-8") as f:
        json.dump(picked, f, ensure_ascii=False)

    print(f"Saved {len(picked)} servers")


main()
