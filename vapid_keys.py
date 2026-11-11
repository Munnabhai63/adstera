"""
vapid_keys.py — Layer 6: Zero-Dependency NIST P-256 VAPID Keypair & RFC 8292 ES256 JWT Engine

Provides pure-Python cryptographic primitives for Web Push (RFC 8291 / RFC 8292):
- Generate cryptographically random NIST P-256 (secp256r1) keypairs using `secrets`
- Encode/decode 65-byte uncompressed `applicationServerKey` (URL-safe base64, no padding)
- Export standard PKCS#8 DER/PEM private keys & RFC 7517 JWK metadata
- Sign & verify RFC 8292 `ES256` VAPID JWT assertions (`Authorization: vapid t=..., k=...`)
- Persist local keypair safely in gitignored `state/vapid_keys.json` (or `.env` overrides)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_VAPID_STATE_PATH = PROJECT_ROOT / "state" / "vapid_keys.json"
DEFAULT_VAPID_SUBJECT = "mailto:admin@loanraaj.com"

# NIST P-256 (secp256r1 / prime256v1) domain parameters
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5

# ASN.1 DER prefixes
_OID_EC_PUBLIC_KEY = bytes.fromhex("06072a8648ce3d0201")
_OID_PRIME256V1 = bytes.fromhex("06082a8648ce3d030107")


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    cleaned = (text or "").strip()
    pad = (-len(cleaned)) % 4
    return base64.urlsafe_b64decode(cleaned + ("=" * pad))


def _der_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _der_tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(body)) + body


def _point_add(
    p1: Optional[tuple[int, int]],
    p2: Optional[tuple[int, int]],
) -> Optional[tuple[int, int]]:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % _P == 0:
            return None
        lam = ((3 * x1 * x1 + _A) * pow((2 * y1) % _P, -1, _P)) % _P
    else:
        lam = ((y2 - y1) * pow((x2 - x1) % _P, -1, _P)) % _P
    x3 = (lam * lam - x1 - x2) % _P
    y3 = (lam * (x1 - x3) - y1) % _P
    return (x3, y3)


def _scalar_mult(k: int, point: tuple[int, int] = (_GX, _GY)) -> Optional[tuple[int, int]]:
    k_mod = k % _N
    if k_mod == 0:
        return None
    res: Optional[tuple[int, int]] = None
    addend: Optional[tuple[int, int]] = point
    while k_mod > 0:
        if k_mod & 1:
            res = _point_add(res, addend)
        addend = _point_add(addend, addend)
        k_mod >>= 1
    return res


def is_on_p256_curve(x: int, y: int) -> bool:
    if not (0 <= x < _P and 0 <= y < _P):
        return False
    return (y * y - (x * x * x + _A * x + _B)) % _P == 0


def derive_public_point(private_d: int) -> tuple[int, int]:
    if not (1 <= private_d < _N):
        raise ValueError("Invalid P-256 private scalar")
    pt = _scalar_mult(private_d)
    if pt is None or not is_on_p256_curve(pt[0], pt[1]):
        raise ValueError("Derived point not on P-256 curve")
    return pt


def encode_pkcs8_pem(private_d: int, pub_x: int, pub_y: int) -> str:
    """Encode P-256 keypair into standard SEC1-wrapped PKCS#8 PEM."""
    priv_bytes = private_d.to_bytes(32, "big")
    pub_uncompressed = b"\x04" + pub_x.to_bytes(32, "big") + pub_y.to_bytes(32, "big")

    ec_priv = _der_tlv(
        0x30,
        _der_tlv(0x02, b"\x01")
        + _der_tlv(0x04, priv_bytes)
        + _der_tlv(0xA1, _der_tlv(0x03, b"\x00" + pub_uncompressed)),
    )
    alg_id = _der_tlv(0x30, _OID_EC_PUBLIC_KEY + _OID_PRIME256V1)
    pkcs8_der = _der_tlv(0x30, _der_tlv(0x02, b"\x00") + alg_id + _der_tlv(0x04, ec_priv))

    b64 = base64.encodebytes(pkcs8_der).decode("ascii").replace("\n", "")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


def _rfc6979_k(private_d: int, msg_hash: bytes) -> int:
    """RFC 6979 deterministic ECDSA nonce generation with HMAC-SHA256."""
    q_len = 32
    bx = private_d.to_bytes(q_len, "big")
    h1_int = int.from_bytes(msg_hash, "big") % _N
    bh = h1_int.to_bytes(q_len, "big")

    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + bx + bh, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + bx + bh, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()

    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < _N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def sign_es256_raw(private_key_b64: str, message: bytes) -> bytes:
    """Sign message with P-256 ECDSA SHA-256 returning 64-byte IEEE P1363 (r || s)."""
    priv_bytes = b64url_decode(private_key_b64)
    if len(priv_bytes) != 32:
        raise ValueError("Expected 32-byte raw P-256 private key")
    d = int.from_bytes(priv_bytes, "big")
    if not (1 <= d < _N):
        raise ValueError("Private scalar out of P-256 range")

    digest = hashlib.sha256(message).digest()
    z = int.from_bytes(digest, "big")
    k = _rfc6979_k(d, digest)

    pt = _scalar_mult(k)
    if pt is None:
        raise RuntimeError("Unexpected ECDSA point at infinity")
    r = pt[0] % _N
    if r == 0:
        raise RuntimeError("Unexpected ECDSA r == 0")
    s = (pow(k, -1, _N) * (z + r * d)) % _N
    if s == 0:
        raise RuntimeError("Unexpected ECDSA s == 0")
    if s > _N // 2:
        s = _N - s
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify_es256_raw(public_key_b64: str, message: bytes, sig_raw: bytes) -> bool:
    """Verify 64-byte IEEE P1363 ECDSA P-256 SHA-256 signature."""
    if len(sig_raw) != 64:
        return False
    try:
        pub = b64url_decode(public_key_b64)
    except Exception:
        return False
    if len(pub) != 65 or pub[0] != 0x04:
        return False
    qx = int.from_bytes(pub[1:33], "big")
    qy = int.from_bytes(pub[33:65], "big")
    if not is_on_p256_curve(qx, qy):
        return False

    r = int.from_bytes(sig_raw[:32], "big")
    s = int.from_bytes(sig_raw[32:], "big")
    if not (1 <= r < _N and 1 <= s < _N):
        return False

    z = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, _N)
    u1 = (z * w) % _N
    u2 = (r * w) % _N
    pt = _point_add(_scalar_mult(u1), _scalar_mult(u2, (qx, qy)))
    if pt is None:
        return False
    return (pt[0] % _N) == r


def generate_vapid_keypair(subject: str = DEFAULT_VAPID_SUBJECT) -> dict[str, Any]:
    """Generate a fresh cryptographically valid RFC 8292 P-256 VAPID keypair."""
    d = secrets.randbelow(_N - 1) + 1
    x, y = derive_public_point(d)
    priv_raw = d.to_bytes(32, "big")
    pub_raw = b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")

    pub_b64 = b64url_encode(pub_raw)
    priv_b64 = b64url_encode(priv_raw)
    pem = encode_pkcs8_pem(d, x, y)
    fingerprint = hashlib.sha256(pub_raw).hexdigest()[:16]

    return {
        "algorithm": "ES256",
        "curve": "P-256",
        "subject": subject or DEFAULT_VAPID_SUBJECT,
        "public_key": pub_b64,
        "private_key": priv_b64,
        "private_key_pem": pem,
        "fingerprint": fingerprint,
        "jwk_public": {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url_encode(x.to_bytes(32, "big")),
            "y": b64url_encode(y.to_bytes(32, "big")),
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def validate_vapid_pair(public_key_b64: str, private_key_b64: str) -> bool:
    """Confirm that public_key and private_key form a genuine matching P-256 keypair."""
    try:
        pub = b64url_decode(public_key_b64)
        priv = b64url_decode(private_key_b64)
        if len(pub) != 65 or pub[0] != 0x04 or len(priv) != 32:
            return False
        d = int.from_bytes(priv, "big")
        x, y = derive_public_point(d)
        expected_pub = b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")
        return hmac.compare_digest(pub, expected_pub)
    except Exception:
        return False


def build_vapid_auth_header(
    endpoint_url: str,
    public_key_b64: str,
    private_key_b64: str,
    subject: str = DEFAULT_VAPID_SUBJECT,
    ttl_seconds: int = 43200,
) -> dict[str, str]:
    """Construct RFC 8292 `Authorization` and `Crypto-Key` headers for Web Push delivery."""
    parts = urlsplit(endpoint_url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid push endpoint URL: {endpoint_url!r}")
    aud = f"{parts.scheme}://{parts.netloc}"
    exp = int(time.time()) + max(60, min(86400, int(ttl_seconds)))

    header_b64 = b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode("utf-8"))
    claims_b64 = b64url_encode(
        json.dumps({"aud": aud, "exp": exp, "sub": subject or DEFAULT_VAPID_SUBJECT}, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")
    sig_raw = sign_es256_raw(private_key_b64, signing_input)
    jwt_token = f"{header_b64}.{claims_b64}.{b64url_encode(sig_raw)}"

    return {
        "Authorization": f"vapid t={jwt_token}, k={public_key_b64}",
        "Crypto-Key": f"p256ecdsa={public_key_b64}",
        "jwt": jwt_token,
        "aud": aud,
    }


def verify_vapid_jwt(jwt_token: str, public_key_b64: str) -> dict[str, Any]:
    """Decode and cryptographically verify an ES256 VAPID JWT assertion."""
    parts = (jwt_token or "").split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    sig_raw = b64url_decode(parts[2])
    if not verify_es256_raw(public_key_b64, signing_input, sig_raw):
        raise ValueError("Invalid ES256 VAPID JWT signature")
    header = json.loads(b64url_decode(parts[0]).decode("utf-8"))
    claims = json.loads(b64url_decode(parts[1]).decode("utf-8"))
    if header.get("alg") != "ES256":
        raise ValueError("Unexpected JWT alg")
    return {"header": header, "claims": claims}


def load_or_create_vapid_keys(
    state_path: Optional[Path | str] = None,
    subject: Optional[str] = None,
    force_rotate: bool = False,
) -> dict[str, Any]:
    """
    Load persistent VAPID keypair from `.env` or `state/vapid_keys.json`, or generate
    and save a fresh valid P-256 keypair on first run.
    """
    target_path = Path(state_path) if state_path is not None else DEFAULT_VAPID_STATE_PATH
    env_pub = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    env_priv = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    env_sub = (subject or os.getenv("VAPID_SUBJECT", "") or DEFAULT_VAPID_SUBJECT).strip()

    if not force_rotate and env_pub and env_priv and validate_vapid_pair(env_pub, env_priv):
        d = int.from_bytes(b64url_decode(env_priv), "big")
        x, y = derive_public_point(d)
        pub_raw = b64url_decode(env_pub)
        return {
            "algorithm": "ES256",
            "curve": "P-256",
            "subject": env_sub,
            "public_key": env_pub,
            "private_key": env_priv,
            "private_key_pem": encode_pkcs8_pem(d, x, y),
            "fingerprint": hashlib.sha256(pub_raw).hexdigest()[:16],
            "jwk_public": {
                "kty": "EC",
                "crv": "P-256",
                "x": b64url_encode(x.to_bytes(32, "big")),
                "y": b64url_encode(y.to_bytes(32, "big")),
            },
            "source": "env",
        }

    if not force_rotate and target_path.is_file():
        try:
            saved = json.loads(target_path.read_text(encoding="utf-8"))
            if (
                isinstance(saved, dict)
                and validate_vapid_pair(saved.get("public_key", ""), saved.get("private_key", ""))
            ):
                saved.setdefault("subject", env_sub)
                saved["source"] = "state_file"
                return saved
        except Exception as exc:
            logger.warning("Failed to load existing VAPID state %s: %s", target_path, exc)

    fresh = generate_vapid_keypair(subject=env_sub)
    fresh["source"] = "generated"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(fresh, indent=2), encoding="utf-8")
    logger.info("Generated new P-256 VAPID keypair (fingerprint=%s) at %s", fresh["fingerprint"], target_path)
    return fresh


def get_public_vapid_status(state_path: Optional[Path | str] = None) -> dict[str, Any]:
    """Return ONLY non-secret public VAPID metadata (never exposes private key)."""
    target_path = Path(state_path) if state_path is not None else DEFAULT_VAPID_STATE_PATH
    keys = load_or_create_vapid_keys(state_path=target_path)
    return {
        "configured": bool(keys.get("public_key")),
        "algorithm": keys.get("algorithm", "ES256"),
        "curve": keys.get("curve", "P-256"),
        "subject": keys.get("subject", DEFAULT_VAPID_SUBJECT),
        "public_key": keys["public_key"],
        "fingerprint": keys["fingerprint"],
        "source": keys.get("source", "state_file"),
        "state_path": str(target_path),
        "created_at": keys.get("created_at", ""),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Layer 6 VAPID P-256 Key Manager")
    parser.add_argument("--rotate", action="store_true", help="Generate & persist a new VAPID keypair")
    parser.add_argument("--status", action="store_true", help="Show public VAPID metadata (safe, no secrets)")
    args = parser.parse_args()

    if args.rotate:
        load_or_create_vapid_keys(force_rotate=True)
    print(json.dumps(get_public_vapid_status(), indent=2))
