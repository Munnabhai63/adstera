# autopublish_engine.py - Autonomous AI Content Publisher with Anti-AI Detection Quality Gate
import os
import sys
import json
import re
import html
import urllib.request
import urllib.error
import subprocess
import time
import math
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 1. ANTI-AI DETECTION / HUMANIZER QUALITY GATE
BANNED_AI_WORDS = [
    "delve", "testament", "beacon", "tapestry", "in conclusion", 
    "it's important to remember", "it is important to note", "dive deep", 
    "foster", "underscore", "crucial", "vital", "moreover", "furthermore", 
    "holistic", "multifaceted", "navigating the landscape", "game-changer", 
    "revolutionize", "seamless", "plethora", "myriad", "paramount", 
    "robust", "embark", "shed light", "harnessing", "unleash", "elevate", 
    "unlocking the potential", "in today's fast-paced world", "ever-evolving", 
    "demystify", "unravel", "pivotal", "cornerstone", "nexus", "linchpin"
]

class AntiAIDetectionGate:
    @staticmethod
    def audit(text):
        """
        Runs comprehensive anti-AI detection audit:
        1. AI buzzword blacklist check
        2. Sentence length variance (burstiness)
        3. Real-world empirical data density
        """
        text_lower = text.lower()
        findings = []
        
        # 1. Blacklist check
        found_buzzwords = [w for w in BANNED_AI_WORDS if w in text_lower]
        if found_buzzwords:
            findings.append(f"Contains AI buzzwords: {', '.join(found_buzzwords[:5])}")
            
        # 2. Burstiness / Sentence length variance
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip().split()) >= 3]
        if len(sentences) >= 5:
            lengths = [len(s.split()) for s in sentences]
            mean_len = sum(lengths) / len(lengths)
            variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
            std_dev = math.sqrt(variance)
            if std_dev < 4.5:
                findings.append(f"Low burstiness (std_dev: {std_dev:.2f} < 4.5). Needs more varied sentence rhythm.")
        else:
            std_dev = 5.0
            
        # 3. Empirical data density (numbers, currencies, percentages)
        data_markers = len(re.findall(r'(\d+|₹|\$|%|SBI|HDFC|ICICI|RBI|TRAI|NPCI)', text))
        if data_markers < 6:
            findings.append("Low factual data density. Lacks concrete figures or regulatory citations.")
            
        is_passed = len(found_buzzwords) == 0 and (std_dev >= 4.0) and (data_markers >= 5)
        return is_passed, findings

    @staticmethod
    def humanize(text):
        """
        Cleans banned phrases and replaces robotic transitions with organic language.
        """
        replacements = {
            r"\bdelve into\b": "examine",
            r"\bdelving into\b": "looking at",
            r"\bdelve\b": "explore",
            r"\ba testament to\b": "clear evidence of",
            r"\btestament\b": "evidence",
            r"\btapestry of\b": "complex mix of",
            r"\btapestry\b": "landscape",
            r"\bbeacon of\b": "leading example of",
            r"\bbeacon\b": "guide",
            r"\bin conclusion\b": "The bottom line:",
            r"\bit's important to remember\b": "Keep in mind",
            r"\bit is important to note\b": "Notice that",
            r"\bdive deep into\b": "break down",
            r"\bdive deep\b": "look closely",
            r"\bfoster\b": "encourage",
            r"\bunderscore\b": "highlight",
            r"\bcrucial\b": "critical",
            r"\bvital\b": "essential",
            r"\bmoreover\b": "also",
            r"\bfurthermore\b": "in addition",
            r"\bholistic\b": "complete",
            r"\bmultifaceted\b": "varied",
            r"\bnavigating the landscape\b": "evaluating options",
            r"\bgame-changer\b": "major shift",
            r"\brevolutionize\b": "transform",
            r"\bplethora of\b": "wide range of",
            r"\bplethora\b": "range",
            r"\bmyriad of\b": "many",
            r"\bmyriad\b": "many",
            r"\bparamount\b": "top priority",
            r"\brobust\b": "durable",
            r"\bdemystify\b": "explain clearly",
            r"\bpivotal\b": "key",
            r"\bcornerstone\b": "foundation",
            r"\bnexus\b": "hub",
            r"\bharnessing\b": "using",
            r"\belevate\b": "improve"
        }
        clean = text
        for pat, repl in replacements.items():
            clean = re.sub(pat, repl, clean, flags=re.IGNORECASE)
        return clean

# 2. FREELLMAPI CLIENT
FREELLMAPI_URL = "http://localhost:3001/v1/chat/completions"
AUTH_TOKEN = "Bearer freellmapi-ceb04983702628b4439a5a1d9e9bf34484f948c29dbe8b4f"

def query_freellmapi(prompt, system_prompt, model="claude-sonnet-4-5"):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2500
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        FREELLMAPI_URL,
        data=data,
        headers={
            "Authorization": AUTH_TOKEN,
            "Content-Type": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"[FreeLLMAPI Error] {e}")
        return None

# 3. SEARCH ENGINE NOTIFICATION
def ping_search_engines(domain):
    sitemap_url = f"{domain}/sitemap.xml"
    ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
    try:
        req = urllib.request.Request(ping_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[Google Ping] Notified Google Search Console for {sitemap_url} (HTTP {resp.status})")
    except Exception as e:
        print(f"[Google Ping Note] Ping endpoint status: {e}")

print("Autonomous Publishing Engine & Anti-AI Quality Gate initialized successfully.")
