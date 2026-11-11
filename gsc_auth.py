"""
gsc_auth.py — Layer 5: Google Search Console & Indexing API OAuth2 / Service Account Auth

Supports all real Google credential paths without heavy external SDK lock-in:
1. Service Account JSON (RS256 JWT assertion -> https://oauth2.googleapis.com/token)
2. OAuth2 Refresh Token (client_id + client_secret + refresh_token -> access_token)
3. Direct Bearer Access Token fallback (env GSC_ACCESS_TOKEN / GSC_SERVICE_ACCOUNT_KEY)

Credential resolution priority:
- Explicit path/dict argument
- Environment / .env: GOOGLE_APPLICATION_CREDENTIALS, GSC_SERVICE_ACCOUNT_JSON,
  GSC_CLIENT_ID + GSC_CLIENT_SECRET + GSC_REFRESH_TOKEN, GSC_ACCESS_TOKEN
- config.yaml -> gsc.* paths
- state/gsc_service_account.json, state/gsc_oauth_token.json
- ~/.config/claude-seo/service_account.json, google-api.json, oauth-token.json
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
STATE_DIR = PROJECT_ROOT / "state"
DEFAULT_SA_PATH = STATE_DIR / "gsc_service_account.json"
DEFAULT_OAUTH_TOKEN_PATH = STATE_DIR / "gsc_oauth_token.json"
DEFAULT_OAUTH_CLIENT_PATH = STATE_DIR / "gsc_oauth_client.json"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"

SCOPE_WEBMASTERS = "https://www.googleapis.com/auth/webmasters"
SCOPE_WEBMASTERS_RO = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPE_INDEXING = "https://www.googleapis.com/auth/indexing"

DEFAULT_SCOPES = [SCOPE_WEBMASTERS, SCOPE_INDEXING]

# PKCS#1 v1.5 DigestInfo ASN.1 DER prefix for SHA-256 (RFC 8017 Section 9.2)
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_dotenv(env_path: Optional[Path] = None) -> dict[str, str]:
    target = Path(env_path) if env_path is not None else DEFAULT_ENV_PATH
    out: dict[str, str] = {}
    if not target.is_file():
        return out
    try:
        for line in target.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                out[k] = v
    except Exception:
        pass
    return out


def _get_setting(key: str, env_map: Optional[dict[str, str]] = None) -> str:
    val = os.environ.get(key, "")
    if val:
        return val.strip()
    if env_map is None:
        env_map = _read_dotenv()
    return env_map.get(key, "").strip()


# ---------------------------------------------------------------------------
# Pure-Python ASN.1 DER & RFC 8017 RS256 Signer
# ---------------------------------------------------------------------------

def _der_read_tlv(buf: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    """Read one ASN.1 DER Tag-Length-Value element starting at offset."""
    if offset >= len(buf):
        raise ValueError("Unexpected end of DER input")
    tag = buf[offset]
    offset += 1
    if offset >= len(buf):
        raise ValueError("Missing DER length byte")
    first_len = buf[offset]
    offset += 1
    if first_len & 0x80:
        num_octets = first_len & 0x7F
        if num_octets == 0 or offset + num_octets > len(buf):
            raise ValueError("Invalid DER length encoding")
        length = int.from_bytes(buf[offset : offset + num_octets], "big")
        offset += num_octets
    else:
        length = first_len
    if offset + length > len(buf):
        raise ValueError("DER element exceeds buffer length")
    value = buf[offset : offset + length]
    return tag, value, offset + length


def _der_parse_sequence_items(seq_bytes: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    pos = 0
    while pos < len(seq_bytes):
        tag, val, pos = _der_read_tlv(seq_bytes, pos)
        items.append((tag, val))
    return items


def _pem_to_der(pem_text: str) -> tuple[str, bytes]:
    normalized = pem_text.replace("\\n", "\n").strip()
    lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]
    label = ""
    b64_chunks: list[str] = []
    in_body = False
    for ln in lines:
        if ln.startswith("-----BEGIN ") and ln.endswith("-----"):
            label = ln[11:-5].strip().upper()
            in_body = True
        elif ln.startswith("-----END ") and ln.endswith("-----"):
            break
        elif in_body:
            b64_chunks.append(ln)
    if not b64_chunks:
        raise ValueError("No PEM key body found in private_key")
    return label, base64.b64decode("".join(b64_chunks))


def load_rsa_private_key_from_pem(pem_text: str) -> tuple[int, int]:
    """Extract RSA modulus (n) and private exponent (d) from PKCS#8 or PKCS#1 PEM."""
    label, der = _pem_to_der(pem_text)
    tag, seq_body, _ = _der_read_tlv(der, 0)
    if tag != 0x30:
        raise ValueError("Invalid RSA key DER: expected outer SEQUENCE")
    items = _der_parse_sequence_items(seq_body)

    # PKCS#8 PrivateKeyInfo has [INTEGER version, SEQUENCE algId, OCTET STRING privateKey]
    if "RSA PRIVATE KEY" not in label and len(items) >= 3 and items[2][0] == 0x04:
        inner_der = items[2][1]
        inner_tag, inner_body, _ = _der_read_tlv(inner_der, 0)
        if inner_tag != 0x30:
            raise ValueError("Invalid PKCS#8 inner RSA key SEQUENCE")
        items = _der_parse_sequence_items(inner_body)

    if len(items) < 4 or items[0][0] != 0x02 or items[1][0] != 0x02 or items[3][0] != 0x02:
        raise ValueError("Invalid RSAPrivateKey ASN.1 structure")

    n = int.from_bytes(items[1][1], "big")
    d = int.from_bytes(items[3][1], "big")
    if n <= 0 or d <= 0:
        raise ValueError("Invalid RSA modulus/exponent")
    return n, d


def sign_rs256_jwt(claims: dict[str, Any], private_key_pem: str, key_id: Optional[str] = None) -> str:
    """Create and sign a Google OAuth2 Service Account JWT assertion using RS256."""
    n, d = load_rsa_private_key_from_pem(private_key_pem)
    k = (n.bit_length() + 7) // 8

    header: dict[str, str] = {"alg": "RS256", "typ": "JWT"}
    if key_id:
        header["kid"] = str(key_id)

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    claims_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{claims_b64}".encode("ascii")

    digest = hashlib.sha256(signing_input).digest()
    t_block = _SHA256_DIGEST_INFO_PREFIX + digest
    ps_len = k - len(t_block) - 3
    if ps_len < 8:
        raise ValueError("RSA key modulus too small for SHA-256 PKCS#1 v1.5 signing")

    em = b"\x00\x01" + (b"\xff" * ps_len) + b"\x00" + t_block
    sig_int = pow(int.from_bytes(em, "big"), d, n)
    sig_b64 = _b64url_encode(sig_int.to_bytes(k, "big"))
    return f"{header_b64}.{claims_b64}.{sig_b64}"


# ---------------------------------------------------------------------------
# Credential Parsing & Unified Auth Manager
# ---------------------------------------------------------------------------

def _load_json_dict(source: Path | str | dict[str, Any] | None) -> Optional[dict[str, Any]]:
    if source is None:
        return None
    if isinstance(source, dict):
        return source
    text = str(source).strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    p = Path(os.path.expanduser(text))
    if p.is_file():
        try:
            parsed = json.loads(p.read_text(encoding="utf-8"))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def validate_service_account_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate Google Service Account JSON structure and RSA private key."""
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise ValueError("JSON must have \"type\": \"service_account\"")
    email = str(data.get("client_email") or "").strip()
    if not email or "@" not in email:
        raise ValueError("Service account JSON missing valid \"client_email\"")
    pkey = str(data.get("private_key") or "").strip()
    if not pkey:
        raise ValueError("Service account JSON missing \"private_key\"")
    load_rsa_private_key_from_pem(pkey)
    return data


def _extract_oauth_client_fields(data: dict[str, Any]) -> Optional[dict[str, str]]:
    if not isinstance(data, dict):
        return None
    section = data.get("installed") or data.get("web") or data
    if not isinstance(section, dict):
        return None
    cid = str(section.get("client_id") or "").strip()
    csec = str(section.get("client_secret") or "").strip()
    if not cid or not csec:
        return None
    return {
        "client_id": cid,
        "client_secret": csec,
        "token_uri": str(section.get("token_uri") or GOOGLE_TOKEN_URI),
        "auth_uri": str(section.get("auth_uri") or GOOGLE_AUTH_URI),
    }


def _load_gsc_config(cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if cfg and isinstance(cfg, dict):
        return cfg.get("gsc", {}) or {}
    if DEFAULT_CONFIG_PATH.is_file():
        try:
            loaded = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            return loaded.get("gsc", {}) or {}
        except Exception:
            pass
    return {}


class GSCAuthManager:
    """Manages Google OAuth2 access tokens from Service Accounts or OAuth refresh tokens."""

    def __init__(
        self,
        cfg: Optional[dict[str, Any]] = None,
        service_account_json: Optional[str | dict[str, Any] | Path] = None,
        oauth_token_path: Optional[Path] = None,
        oauth_client_path: Optional[Path] = None,
        env_path: Optional[Path] = None,
        direct_token: Optional[str] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        self.cfg = cfg or {}
        self.gsc_cfg = _load_gsc_config(cfg)
        self.explicit_sa = service_account_json or self.gsc_cfg.get("service_account_json")
        self.oauth_token_path = Path(oauth_token_path) if oauth_token_path else Path(
            self.gsc_cfg.get("oauth_token_json") or DEFAULT_OAUTH_TOKEN_PATH
        )
        self.oauth_client_path = Path(oauth_client_path) if oauth_client_path else Path(
            self.gsc_cfg.get("oauth_client_json") or DEFAULT_OAUTH_CLIENT_PATH
        )
        self.env_path = Path(env_path) if env_path else DEFAULT_ENV_PATH
        self.direct_token = (direct_token or "").strip()
        self.default_scopes = list(scopes or DEFAULT_SCOPES)
        self._token_cache: dict[tuple[str, ...], tuple[str, float]] = {}

    def _resolve_credential_source(self) -> dict[str, Any]:
        env_map = _read_dotenv(self.env_path)

        # 1. Explicit service_account_json dict or path
        if self.explicit_sa is not None:
            sa_dict = _load_json_dict(self.explicit_sa)
            if sa_dict and sa_dict.get("type") == "service_account":
                return {
                    "auth_type": "service_account",
                    "sa_data": sa_dict,
                    "source_path": str(self.explicit_sa) if not isinstance(self.explicit_sa, dict) else "inline",
                }
            # Direct path argument that does not exist yet should NOT silently override unless fallback exists

        # 2. Environment variables for Service Account JSON
        for env_key in ("GOOGLE_APPLICATION_CREDENTIALS", "GSC_SERVICE_ACCOUNT_JSON"):
            raw_val = _get_setting(env_key, env_map)
            if raw_val:
                sa_dict = _load_json_dict(raw_val)
                if sa_dict and sa_dict.get("type") == "service_account":
                    return {
                        "auth_type": "service_account",
                        "sa_data": sa_dict,
                        "source_path": "inline_env" if raw_val.startswith("{") else raw_val,
                    }

        # 3. Direct non-mock Bearer token argument (or legacy GSC_SERVICE_ACCOUNT_KEY if JSON/path)
        key_candidate = self.direct_token or _get_setting("GSC_ACCESS_TOKEN", env_map) or _get_setting("GSC_SERVICE_ACCOUNT_KEY", env_map)
        if key_candidate and not key_candidate.startswith("mock"):
            sa_from_key = _load_json_dict(key_candidate)
            if sa_from_key and sa_from_key.get("type") == "service_account":
                return {"auth_type": "service_account", "sa_data": sa_from_key, "source_path": key_candidate}
            if not key_candidate.endswith(".json"):
                return {"auth_type": "bearer_token", "access_token": key_candidate, "source_path": "token_env_or_arg"}

        # 4. Standard workspace Service Account file (state/gsc_service_account.json) & ~/.config/claude-seo
        sa_candidates: list[Path] = [DEFAULT_SA_PATH]
        claude_cfg_path = Path(os.path.expanduser("~/.config/claude-seo/google-api.json"))
        if claude_cfg_path.is_file():
            try:
                cdata = json.loads(claude_cfg_path.read_text(encoding="utf-8"))
                if cdata.get("service_account_path"):
                    sa_candidates.append(Path(os.path.expanduser(cdata["service_account_path"])))
            except Exception:
                pass
        sa_candidates.append(Path(os.path.expanduser("~/.config/claude-seo/service_account.json")))

        for cand in sa_candidates:
            sa_dict = _load_json_dict(cand)
            if sa_dict and sa_dict.get("type") == "service_account":
                return {"auth_type": "service_account", "sa_data": sa_dict, "source_path": str(cand)}

        # 5. OAuth2 Refresh Token (env vars or saved state/gsc_oauth_token.json or claude-seo oauth-token.json)
        cid = _get_setting("GSC_CLIENT_ID", env_map)
        csec = _get_setting("GSC_CLIENT_SECRET", env_map)
        rtok = _get_setting("GSC_REFRESH_TOKEN", env_map)
        if cid and csec and rtok:
            return {
                "auth_type": "oauth2_refresh_token",
                "client_id": cid,
                "client_secret": csec,
                "refresh_token": rtok,
                "token_uri": GOOGLE_TOKEN_URI,
                "source_path": "env",
            }

        for tok_path in (
            self.oauth_token_path,
            Path(os.path.expanduser("~/.config/claude-seo/oauth-token.json")),
        ):
            tok_data = _load_json_dict(tok_path)
            if tok_data and tok_data.get("refresh_token"):
                client_id = str(tok_data.get("client_id") or "")
                client_secret = str(tok_data.get("client_secret") or "")
                if (not client_id or not client_secret) and self.oauth_client_path.is_file():
                    client_fields = _extract_oauth_client_fields(_load_json_dict(self.oauth_client_path) or {})
                    if client_fields:
                        client_id = client_id or client_fields["client_id"]
                        client_secret = client_secret or client_fields["client_secret"]
                if client_id and client_secret:
                    return {
                        "auth_type": "oauth2_refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": str(tok_data["refresh_token"]),
                        "token_uri": str(tok_data.get("token_uri") or GOOGLE_TOKEN_URI),
                        "source_path": str(tok_path),
                    }

        return {"auth_type": "unconfigured"}

    def is_configured(self) -> bool:
        return self._resolve_credential_source()["auth_type"] != "unconfigured"

    def get_status(self) -> dict[str, Any]:
        """Return non-secret credential diagnostics for UI and CLI reports."""
        resolved = self._resolve_credential_source()
        auth_type = resolved["auth_type"]
        configured = auth_type != "unconfigured"
        client_email = ""
        project_id = ""
        if auth_type == "service_account":
            sa = resolved["sa_data"]
            client_email = str(sa.get("client_email") or "")
            project_id = str(sa.get("project_id") or "")

        oauth_client_ready = bool(
            self.oauth_client_path.is_file()
            and _extract_oauth_client_fields(_load_json_dict(self.oauth_client_path) or {})
        )
        return {
            "configured": configured,
            "auth_type": auth_type,
            "client_email": client_email,
            "project_id": project_id,
            "credential_source": resolved.get("source_path", ""),
            "expected_sa_path": str(DEFAULT_SA_PATH),
            "expected_oauth_token_path": str(self.oauth_token_path),
            "oauth_client_configured": oauth_client_ready,
            "token_cached": bool(self._token_cache),
            "scopes": list(self.default_scopes),
        }

    def _build_token_request(
        self, resolved: dict[str, Any], scopes: list[str]
    ) -> tuple[str, dict[str, str]]:
        if resolved["auth_type"] == "service_account":
            sa = resolved["sa_data"]
            now = int(time.time())
            token_uri = str(sa.get("token_uri") or GOOGLE_TOKEN_URI)
            claims = {
                "iss": sa["client_email"],
                "scope": " ".join(scopes),
                "aud": token_uri,
                "iat": now,
                "exp": now + 3600,
            }
            assertion = sign_rs256_jwt(
                claims,
                sa["private_key"],
                key_id=sa.get("private_key_id"),
            )
            return token_uri, {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            }

        if resolved["auth_type"] == "oauth2_refresh_token":
            token_uri = str(resolved.get("token_uri") or GOOGLE_TOKEN_URI)
            return token_uri, {
                "grant_type": "refresh_token",
                "client_id": resolved["client_id"],
                "client_secret": resolved["client_secret"],
                "refresh_token": resolved["refresh_token"],
            }

        raise ValueError("Cannot build token request for unconfigured credentials")

    def get_access_token(
        self,
        scopes: Optional[list[str]] = None,
        client: Optional[httpx.Client] = None,
    ) -> Optional[str]:
        """Synchronously obtain a valid Google OAuth2 Bearer access token (cached until near expiry)."""
        scope_list = sorted(set(scopes or self.default_scopes))
        scope_key = tuple(scope_list)
        now = time.time()

        cached = self._token_cache.get(scope_key)
        if cached and cached[1] - 60 > now:
            return cached[0]

        resolved = self._resolve_credential_source()
        if resolved["auth_type"] == "unconfigured":
            return None
        if resolved["auth_type"] == "bearer_token":
            return resolved["access_token"]

        token_uri, form_data = self._build_token_request(resolved, scope_list)
        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            resp = http.post(token_uri, data=form_data)
            if resp.status_code != 200:
                raise RuntimeError(f"Google OAuth2 token exchange failed ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()
            token = str(data.get("access_token") or "")
            if not token:
                raise RuntimeError("Google OAuth2 response missing access_token")
            expires_in = float(data.get("expires_in", 3600))
            self._token_cache[scope_key] = (token, time.time() + expires_in)
            return token
        finally:
            if own_client:
                http.close()

    async def aget_access_token(
        self,
        scopes: Optional[list[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[str]:
        """Asynchronously obtain a valid Google OAuth2 Bearer access token."""
        scope_list = sorted(set(scopes or self.default_scopes))
        scope_key = tuple(scope_list)
        now = time.time()

        cached = self._token_cache.get(scope_key)
        if cached and cached[1] - 60 > now:
            return cached[0]

        resolved = self._resolve_credential_source()
        if resolved["auth_type"] == "unconfigured":
            return None
        if resolved["auth_type"] == "bearer_token":
            return resolved["access_token"]

        token_uri, form_data = self._build_token_request(resolved, scope_list)
        own_client = client is None
        http = client or httpx.AsyncClient(timeout=15.0)
        try:
            resp = await http.post(token_uri, data=form_data)
            if resp.status_code != 200:
                raise RuntimeError(f"Google OAuth2 token exchange failed ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()
            token = str(data.get("access_token") or "")
            if not token:
                raise RuntimeError("Google OAuth2 response missing access_token")
            expires_in = float(data.get("expires_in", 3600))
            self._token_cache[scope_key] = (token, time.time() + expires_in)
            return token
        finally:
            if own_client:
                await http.aclose()

    def clear_cache(self) -> None:
        self._token_cache.clear()

    def save_credentials_payload(
        self,
        payload: dict[str, Any] | str,
        sa_target: Optional[Path] = None,
        oauth_target: Optional[Path] = None,
        client_target: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Validate and persist Service Account JSON or OAuth2 credentials without echoing secrets."""
        data = _load_json_dict(payload) if not isinstance(payload, dict) else payload
        if not isinstance(data, dict):
            raise ValueError("Invalid JSON credential payload")

        self.clear_cache()

        # Case A: Service Account JSON
        if data.get("type") == "service_account":
            validate_service_account_dict(data)
            out_path = Path(sa_target) if sa_target else DEFAULT_SA_PATH
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            _chmod_private(out_path)
            return {
                "saved": True,
                "auth_type": "service_account",
                "client_email": data["client_email"],
                "project_id": data.get("project_id", ""),
                "path": str(out_path),
            }

        # Case B: Direct OAuth2 refresh_token payload
        if data.get("refresh_token") and data.get("client_id") and data.get("client_secret"):
            clean = {
                "client_id": str(data["client_id"]).strip(),
                "client_secret": str(data["client_secret"]).strip(),
                "refresh_token": str(data["refresh_token"]).strip(),
                "token_uri": str(data.get("token_uri") or GOOGLE_TOKEN_URI),
                "scopes": data.get("scopes") or DEFAULT_SCOPES,
            }
            out_path = Path(oauth_target) if oauth_target else self.oauth_token_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
            _chmod_private(out_path)
            return {
                "saved": True,
                "auth_type": "oauth2_refresh_token",
                "path": str(out_path),
            }

        # Case C: Google Cloud OAuth client_secret JSON (web or installed)
        client_fields = _extract_oauth_client_fields(data)
        if client_fields:
            out_path = Path(client_target) if client_target else self.oauth_client_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            _chmod_private(out_path)
            return {
                "saved": True,
                "auth_type": "oauth2_client_secret",
                "path": str(out_path),
            }

        raise ValueError(
            "Unsupported credential JSON. Provide a Google Service Account JSON (type='service_account'), "
            "an OAuth2 refresh_token bundle, or an OAuth client_secret JSON."
        )

    def build_oauth_authorize_url(
        self,
        redirect_uri: str = "http://localhost:8085",
        scopes: Optional[list[str]] = None,
    ) -> dict[str, str]:
        """Generate an OAuth2 PKCE consent URL using saved oauth_client_json."""
        client_data = _load_json_dict(self.oauth_client_path)
        fields = _extract_oauth_client_fields(client_data or {})
        if not fields:
            raise ValueError(f"OAuth client_secret JSON not configured at {self.oauth_client_path}")

        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
        challenge = _b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())
        state = secrets.token_urlsafe(24)
        params = {
            "client_id": fields["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes or DEFAULT_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        return {
            "auth_url": f"{GOOGLE_AUTH_URI}?{urlencode(params)}",
            "state": state,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        }

    def exchange_oauth_code(
        self,
        code: str,
        redirect_uri: str = "http://localhost:8085",
        code_verifier: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> dict[str, Any]:
        """Exchange an OAuth2 authorization code for refresh/access tokens and persist them."""
        client_data = _load_json_dict(self.oauth_client_path)
        fields = _extract_oauth_client_fields(client_data or {})
        if not fields:
            raise ValueError(f"OAuth client_secret JSON not configured at {self.oauth_client_path}")

        form = {
            "code": code.strip(),
            "client_id": fields["client_id"],
            "client_secret": fields["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            form["code_verifier"] = code_verifier

        own_client = client is None
        http = client or httpx.Client(timeout=15.0)
        try:
            resp = http.post(fields["token_uri"], data=form)
            if resp.status_code != 200:
                raise RuntimeError(f"OAuth code exchange failed ({resp.status_code}): {resp.text[:300]}")
            tok = resp.json()
            if not tok.get("refresh_token") and not tok.get("access_token"):
                raise RuntimeError("OAuth response missing tokens")
            saved_bundle = {
                "client_id": fields["client_id"],
                "client_secret": fields["client_secret"],
                "refresh_token": tok.get("refresh_token", ""),
                "token_uri": fields["token_uri"],
                "scopes": DEFAULT_SCOPES,
                "saved_at": time.time(),
            }
            self.oauth_token_path.parent.mkdir(parents=True, exist_ok=True)
            self.oauth_token_path.write_text(json.dumps(saved_bundle, indent=2), encoding="utf-8")
            _chmod_private(self.oauth_token_path)
            self.clear_cache()
            if tok.get("access_token"):
                expires_in = float(tok.get("expires_in", 3600))
                self._token_cache[tuple(sorted(DEFAULT_SCOPES))] = (tok["access_token"], time.time() + expires_in)
            return {
                "saved": True,
                "has_refresh_token": bool(tok.get("refresh_token")),
                "path": str(self.oauth_token_path),
            }
        finally:
            if own_client:
                http.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Google Search Console OAuth2 / Service Account diagnostics")
    parser.add_argument("--status", action="store_true", help="Print credential status as JSON (redacted)")
    args = parser.parse_args()
    mgr = GSCAuthManager()
    print(json.dumps(mgr.get_status(), indent=2))
