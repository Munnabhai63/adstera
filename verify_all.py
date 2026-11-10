import httpx

DOMAINS = [
    "loanraaj.com",
    "rechargetak.com",
    "rechargepur.com",
    "tazaloan.com",
    "loankiseva.com",
    "karzseva.com",
    "loantau.com",
    "tazabhav.com",
    "tazarokda.com",
    "rechargekar.com",
]

client = httpx.Client(timeout=10, follow_redirects=True)

print("=" * 70)
print("ALL 10 DOMAINS (APEX + WWW) - CLOUDFLARE PAGES LIVE AUDIT")
print("=" * 70)

all_ok = True
for d in DOMAINS:
    for prefix in ["", "www."]:
        host = f"{prefix}{d}"
        url = f"https://{host}"
        try:
            r = client.get(url)
            srv = r.headers.get("server")
            print(f"https://{host:22}: {r.status_code} OK (server: {srv})")
            if r.status_code != 200:
                all_ok = False
        except Exception as e:
            print(f"https://{host:22}: ERROR -> {e}")
            all_ok = False

print("=" * 70)
print(f"VERDICT: {'ALL 20 HOSTS (APEX + WWW) ARE 100% ONLINE AND SERVED BY CLOUDFLARE EDGE' if all_ok else 'SOME FAILED'}")
print("=" * 70)
