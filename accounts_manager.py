"""
accounts_manager.py — Ingestion, persona generation, and management for unlimited accounts.
Supports accounts.txt, Email API, and synthetic high-intent financial personas.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.resolve()
STATE_ACCOUNTS_DIR = PROJECT_ROOT / "state" / "accounts"
ACCOUNTS_TXT_PATH = PROJECT_ROOT / "accounts.txt"
REGISTRY_PATH = STATE_ACCOUNTS_DIR / "registry.json"


# Sample realistic first and last names for synthetic personas
_FIRST_NAMES = [
    "James", "Michael", "Robert", "John", "David", "William", "Richard", "Joseph",
    "Thomas", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Donald", "Steven",
    "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica",
    "Sarah", "Karen", "Lisa", "Nancy", "Ashley", "Emily", "Donna", "Michelle"
]

_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker"
]

_CITIES_US = [
    ("New York", "NY", "10001", "America/New_York"),
    ("Los Angeles", "CA", "90001", "America/Los_Angeles"),
    ("Chicago", "IL", "60601", "America/Chicago"),
    ("Houston", "TX", "77001", "America/Chicago"),
    ("Phoenix", "AZ", "85001", "America/Phoenix"),
    ("Philadelphia", "PA", "19101", "America/New_York"),
    ("Dallas", "TX", "75201", "America/Chicago"),
    ("Austin", "TX", "78701", "America/Chicago"),
    ("Atlanta", "GA", "30301", "America/New_York"),
    ("Seattle", "WA", "98101", "America/Los_Angeles"),
]

_FIRST_NAMES_IN = [
    "Rahul", "Amit", "Rohit", "Vikram", "Suresh", "Rajesh", "Ankit", "Gaurav",
    "Deepak", "Manish", "Sachin", "Pradeep", "Priya", "Neha", "Pooja", "Anjali",
    "Kavita", "Sneha", "Swati", "Ritu",
]

_LAST_NAMES_IN = [
    "Sharma", "Verma", "Patel", "Singh", "Kumar", "Gupta", "Yadav", "Joshi",
    "Mehta", "Chauhan", "Mishra", "Reddy", "Nair", "Kulkarni", "Tiwari", "Agarwal",
]

_CITIES_IN = [
    ("Mumbai", "MH", "400001", "Asia/Kolkata"),
    ("New Delhi", "DL", "110001", "Asia/Kolkata"),
    ("Bengaluru", "KA", "560001", "Asia/Kolkata"),
    ("Pune", "MH", "411001", "Asia/Kolkata"),
    ("Ahmedabad", "GJ", "380001", "Asia/Kolkata"),
    ("Hyderabad", "TG", "500001", "Asia/Kolkata"),
    ("Jaipur", "RJ", "302001", "Asia/Kolkata"),
    ("Lucknow", "UP", "226001", "Asia/Kolkata"),
]

_FINANCIAL_INTENTS = [
    "Personal Loans Refinancing",
    "Low Interest Mortgages 2026",
    "High Yield Savings Accounts",
    "Commercial Real Estate Lending",
    "Business Line of Credit",
    "Experian Credit Score Boost",
    "Auto Insurance Quotes",
    "Cybersecurity VPN Infrastructure"
]


class Account:
    """Represents a single profile account with authentication and persona metadata."""
    def __init__(
        self,
        account_id: str,
        email: str,
        password: str,
        name: str = "",
        proxy: Optional[str] = None,
        persona: Optional[Dict[str, Any]] = None,
        created_at: float = 0.0,
        warmed: bool = False,
        cookies_count: int = 0
    ):
        self.account_id = account_id
        self.email = email
        self.password = password
        self.name = name or email.split("@")[0]
        self.proxy = proxy
        self.persona = persona or {}
        self.created_at = created_at
        self.warmed = warmed
        self.cookies_count = cookies_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "email": self.email,
            "password": self.password,
            "name": self.name,
            "proxy": self.proxy,
            "persona": self.persona,
            "created_at": self.created_at,
            "warmed": self.warmed,
            "cookies_count": self.cookies_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Account":
        return cls(
            account_id=data.get("account_id") or str(uuid.uuid4()),
            email=data.get("email", ""),
            password=data.get("password", ""),
            name=data.get("name", ""),
            proxy=data.get("proxy"),
            persona=data.get("persona") or {},
            created_at=float(data.get("created_at", 0.0)),
            warmed=bool(data.get("warmed", False)),
            cookies_count=int(data.get("cookies_count", 0)),
        )


class AccountsManager:
    """Manages the full lifecycle of unlimited accounts, accounts.txt parsing, and personas."""

    def __init__(self):
        STATE_ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_accounts_txt()
        self._registry: Dict[str, Account] = {}
        self._load_registry()

    def _ensure_accounts_txt(self) -> None:
        """Create sample accounts.txt if missing."""
        if not ACCOUNTS_TXT_PATH.exists():
            sample_content = (
                "# accounts.txt — Multi-format account and persona pool\n"
                "# Formats supported:\n"
                "# 1. email:password\n"
                "# 2. email:password:proxy_host:proxy_port\n"
                "# 3. email:password:proxy_host:proxy_port:proxy_user:proxy_pass\n"
                "# 4. JSON: [{\"email\": \"...\", \"password\": \"...\"}]\n"
                "david.miller.invest88@gmail.com:PassSecure#2026\n"
                "sarah.connor.finance@yahoo.com:LoanRefi$992\n"
                "alex.turner.cloud@outlook.com:CloudVPS*774\n"
            )
            ACCOUNTS_TXT_PATH.write_text(sample_content, encoding="utf-8")

    def _load_registry(self) -> None:
        if REGISTRY_PATH.exists():
            try:
                data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
                for acc_id, acc_dict in data.items():
                    self._registry[acc_id] = Account.from_dict(acc_dict)
            except Exception as exc:
                logger.warning("Failed to load accounts registry: %s", exc)

    def _save_registry(self) -> None:
        try:
            data = {acc_id: acc.to_dict() for acc_id, acc in self._registry.items()}
            REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save accounts registry: %s", exc)

    def parse_accounts_file(self, filepath: Optional[Path] = None) -> List[Account]:
        """Parse accounts from accounts.txt supporting colon, pipe, and JSON formats."""
        target_path = filepath or ACCOUNTS_TXT_PATH
        if not target_path.exists():
            return []

        raw = target_path.read_text(encoding="utf-8").strip()
        if not raw:
            return []

        accounts: List[Account] = []

        # Check for JSON array
        if raw.startswith("[") and raw.endswith("]"):
            try:
                items = json.loads(raw)
                for it in items:
                    email = it.get("email") or it.get("username")
                    pw = it.get("password") or it.get("pass")
                    if email and pw:
                        acc_id = hashlib.sha256(email.lower().strip().encode()).hexdigest()[:16]
                        acc = Account(
                            account_id=acc_id,
                            email=email.strip(),
                            password=pw.strip(),
                            name=it.get("name", ""),
                            proxy=it.get("proxy"),
                            persona=self.generate_persona(email.strip()),
                        )
                        accounts.append(acc)
                return accounts
            except Exception:
                pass

        # Parse line-by-line
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            delimiter = ":" if ":" in line else "|" if "|" in line else None
            if not delimiter:
                continue

            parts = [p.strip() for p in line.split(delimiter)]
            if len(parts) >= 2:
                email = parts[0]
                password = parts[1]
                proxy_str = None

                if len(parts) == 4 and parts[3].isdigit():
                    # email:password:host:port
                    proxy_str = f"http://{parts[2]}:{parts[3]}"
                elif len(parts) >= 6:
                    # email:password:host:port:user:pass
                    proxy_str = f"http://{parts[4]}:{parts[5]}@{parts[2]}:{parts[3]}"

                acc_id = hashlib.sha256(email.lower().strip().encode()).hexdigest()[:16]
                acc = Account(
                    account_id=acc_id,
                    email=email,
                    password=password,
                    proxy=proxy_str,
                    persona=self.generate_persona(email),
                )
                accounts.append(acc)

        return accounts

    def generate_persona(self, email_seed: str, rng: Optional[random.Random] = None, country: str = "US") -> Dict[str, Any]:
        """Generates a consistent, geo-coherent high-intent financial persona (IN or US)."""
        seed_int = int(hashlib.sha256(f"{email_seed}:{country}".encode()).hexdigest()[:8], 16)
        r = random.Random(seed_int) if rng is None else rng

        is_in = str(country or "").upper() == "IN"
        if is_in:
            first = r.choice(_FIRST_NAMES_IN)
            last = r.choice(_LAST_NAMES_IN)
            city_info = r.choice(_CITIES_IN)
            phone = f"9{r.choice(['8', '9', '7'])}{r.randint(10000000, 99999999)}"
            income_str = f"₹{r.randint(6, 24) * 100000:,}"
        else:
            first = r.choice(_FIRST_NAMES)
            last = r.choice(_LAST_NAMES)
            city_info = r.choice(_CITIES_US)
            phone = f"({r.randint(201, 899)}) {r.randint(200, 999)}-{r.randint(1000, 9999)}"
            income_str = f"${r.randint(65, 140) * 1000:,}"

        intent = r.choice(_FINANCIAL_INTENTS)
        age = r.randint(28, 58)

        return {
            "country": "IN" if is_in else "US",
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}",
            "age": age,
            "city": city_info[0],
            "state": city_info[1],
            "zip": city_info[2],
            "phone": phone,
            "timezone": city_info[3],
            "annual_income": income_str,
            "credit_score": r.randint(680, 810),
            "commercial_intent": intent,
            "search_query": f"best {intent.lower()} rates {city_info[0]}",
        }

    def generate_synthetic_account(self, domain: str = "gmail.com", country: str = "US") -> Account:
        """Create a brand new synthetic account with realistic geo-coherent persona on-the-fly."""
        is_in = str(country or "").upper() == "IN"
        first = (random.choice(_FIRST_NAMES_IN) if is_in else random.choice(_FIRST_NAMES)).lower()
        last = (random.choice(_LAST_NAMES_IN) if is_in else random.choice(_LAST_NAMES)).lower()
        rand_num = random.randint(100, 9999)
        email = f"{first}.{last}{rand_num}@{domain}"
        password = f"Secure#{random.randint(10000, 99999)}"
        acc_id = hashlib.sha256(email.encode()).hexdigest()[:16]

        acc = Account(
            account_id=acc_id,
            email=email,
            password=password,
            name=f"{first.capitalize()} {last.capitalize()}",
            persona=self.generate_persona(email, country=country),
            created_at=random.uniform(1000000, 2000000)
        )
        self._registry[acc_id] = acc
        self._save_registry()
        return acc

    def get_or_create_account(self, email: str, password: str = "DefaultPass#2026") -> Account:
        """Fetch existing account from registry or create a new one."""
        acc_id = hashlib.sha256(email.lower().strip().encode()).hexdigest()[:16]
        if acc_id in self._registry:
            return self._registry[acc_id]

        acc = Account(
            account_id=acc_id,
            email=email.strip(),
            password=password,
            persona=self.generate_persona(email.strip()),
        )
        self._registry[acc_id] = acc
        self._save_registry()
        return acc

    def get_all_accounts(self) -> List[Account]:
        """Returns all accounts parsed from accounts.txt plus registry."""
        file_accounts = self.parse_accounts_file()
        for fa in file_accounts:
            if fa.account_id not in self._registry:
                self._registry[fa.account_id] = fa
        self._save_registry()
        return list(self._registry.values())

    def update_account_warming(self, account_id: str, cookies_count: int) -> None:
        """Mark account as warmed with cookie tally."""
        if account_id in self._registry:
            self._registry[account_id].warmed = True
            self._registry[account_id].cookies_count = cookies_count
            self._save_registry()
