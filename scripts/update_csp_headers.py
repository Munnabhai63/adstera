"""
scripts/update_csp_headers.py — Add Content-Security-Policy to all 10 sites/_headers files.
"""
from pathlib import Path

CSP_DIRECTIVE = (
    "default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: blob:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' https: data: blob:; "
    "frame-src 'self' https: about:; "
    "connect-src 'self' https: wss:;"
)

def update_headers_file(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    if "Content-Security-Policy:" in content:
        return False

    lines = content.strip().splitlines()
    lines.append(f"  Content-Security-Policy: {CSP_DIRECTIVE}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True

def main():
    updated = 0
    headers_files = list(Path("sites").glob("*/_headers"))
    for hf in headers_files:
        if update_headers_file(hf):
            updated += 1
            print(f"Added CSP to {hf}")
        else:
            print(f"CSP already present in {hf}")
    print(f"Total _headers updated: {updated}/{len(headers_files)}")

if __name__ == "__main__":
    main()
