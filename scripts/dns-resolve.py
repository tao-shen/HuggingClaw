#!/usr/bin/env python3
"""
DNS-over-HTTPS resolver for HF Spaces.

HF Spaces containers cannot resolve certain domains (e.g. web.whatsapp.com)
via the default DNS resolver. This script resolves key domains using
Cloudflare DoH (DNS-over-HTTPS) and writes results to a JSON file
for the Node.js DNS fix script to consume.

Usage: python3 dns-resolve.py [output-file]
"""

import json
import os
import ssl
import sys
import urllib.request

DOH_ENDPOINTS = [
    "https://1.1.1.1/dns-query",         # Cloudflare
    "https://8.8.8.8/resolve",            # Google
    "https://dns.google/resolve",         # Google (hostname)
]

# Domains that WhatsApp/Baileys needs to connect to
DOMAINS = [
    "web.whatsapp.com",
    "g.whatsapp.net",
    "mmg.whatsapp.net",
    "pps.whatsapp.net",
    "static.whatsapp.net",
    "media.fmed1-1.fna.whatsapp.net",
]


def resolve_via_doh(domain: str, endpoint: str, timeout: int = 10) -> list[str]:
    """Resolve a domain via DNS-over-HTTPS, return list of IPv4 addresses."""
    url = f"{endpoint}?name={domain}&type=A"
    req = urllib.request.Request(url, headers={"Accept": "application/dns-json"})

    ctx = ssl.create_default_context()
    resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    data = json.loads(resp.read().decode())

    ips = []
    for answer in data.get("Answer", []):
        if answer.get("type") == 1:  # A record
            ips.append(answer["data"])
        elif answer.get("type") == 5:  # CNAME — follow chain
            continue
    return ips


def resolve_domain(domain: str) -> list[str]:
    """Try multiple DoH endpoints until one succeeds."""
    for endpoint in DOH_ENDPOINTS:
        try:
            ips = resolve_via_doh(domain, endpoint)
            if ips:
                return ips
        except Exception:
            continue
    return []


def main() -> None:
    output_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dns-resolved.json"

    # First check if system DNS works at all
    try:
        import socket
        socket.getaddrinfo("web.whatsapp.com", 443, socket.AF_INET)
        print("[dns] System DNS works for web.whatsapp.com — DoH not needed")
        # Write empty file so dns-fix.cjs knows it's not needed
        with open(output_file, "w") as f:
            json.dump({}, f)
        return
    except (socket.gaierror, OSError):
        print("[dns] System DNS cannot resolve web.whatsapp.com — using DoH fallback")

    results = {}
    for domain in DOMAINS:
        ips = resolve_domain(domain)
        if ips:
            results[domain] = ips[0]
            print(f"[dns] {domain} -> {ips[0]}")
        else:
            print(f"[dns] WARNING: could not resolve {domain}")

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"[dns] Resolved {len(results)}/{len(DOMAINS)} domains -> {output_file}")


if __name__ == "__main__":
    main()
