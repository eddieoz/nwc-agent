#!/usr/bin/env python3
"""
402 Index Discovery — Pure Python, urllib-only.

Searches 402index.io for paid API services that accept Bitcoin/Lightning
payments (L402, X402, MPP). No API key required.

API: https://402index.io/api/v1/services

Usage:
    from nwc_discover import discover
    results = discover(q="image generation", protocol="l402")
"""

import json
import sys
import urllib.request
import urllib.parse

DISCOVER_URL = 'https://402index.io/api/v1/services'


def discover(q='', protocol=None, health='healthy', sort='reliability',
             limit=10):
    """Search 402index.io for paid API services.

    Args:
        q: Search query (default: '', returns all).
        protocol: Filter by protocol ('l402', 'x402', or None for all).
        health: Filter by health ('healthy', 'degraded', 'down', 'unknown').
        sort: Sort field ('reliability', 'name', 'price', 'latency', 'uptime').
        limit: Max results (default 10, max 200).

    Returns:
        dict with 'results' list of service objects.
    """
    params = {
        'limit': min(limit, 200),
        'sort': sort,
        'verified': 'true',
    }
    if q:
        params['q'] = q
    if protocol:
        params['protocol'] = protocol.lower()
    if health:
        params['health'] = health

    qs = urllib.parse.urlencode(params)
    url = f"{DISCOVER_URL}?{qs}"

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            services = data if isinstance(data, list) else data.get('services', [])
            return {'results': services}
    except Exception as e:
        raise RuntimeError(f"Failed to query 402index.io: {e}")
