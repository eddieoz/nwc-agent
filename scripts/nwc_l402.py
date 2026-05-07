#!/usr/bin/env python3
"""
L402 Protocol Handler — Python implementation of the L402/LSAT payment flow.

L402 (Lightning Service Authentication Token) is a protocol where a server
returns HTTP 402 with a WWW-Authenticate header containing a macaroon/token
and a Lightning invoice. The client pays the invoice and retries with:
    Authorization: L402 <token>:<preimage>

Based on: @getalby/lightning-tools src/402/l402/
"""

import re


def parse_l402_header(www_authenticate):
    """Parse a WWW-Authenticate: L402/LSAT header.

    Format:
        L402 token="<macaroon>", invoice="<bolt11>"
        LSAT macaroon="<macaroon>", invoice="<bolt11>"

    Args:
        www_authenticate: Raw header value (e.g. 'L402 token=abc, invoice=lnbc...')

    Returns:
        dict with 'token' and 'invoice' keys.

    Raises:
        ValueError: if required fields are missing.
    """
    if not www_authenticate:
        raise ValueError("Empty WWW-Authenticate header")

    header = www_authenticate.strip()

    # Strip L402/LSAT scheme prefix
    scheme = None
    lower = header.lower()
    if lower.startswith('l402'):
        scheme = 'L402'
        header = header[4:].strip()
    elif lower.startswith('lsat'):
        scheme = 'LSAT'
        header = header[4:].strip()
    else:
        raise ValueError(f"Unknown auth scheme (expected L402 or LSAT): {header[:30]}")

    # Parse key=value pairs. Supports:
    #   key=value
    #   key="value"
    #   key='value'
    pairs = {}
    # Regex: key= followed by quoted or unquoted value
    pattern = re.compile(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|([^,]*))')
    for match in pattern.finditer(header):
        key = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4) or ''
        pairs[key] = value.strip()

    # Normalize: support 'macaroon' key as fallback for 'token'
    if 'token' not in pairs and 'macaroon' in pairs:
        pairs['token'] = pairs.pop('macaroon')

    if 'token' not in pairs:
        raise ValueError("L402: missing token in WWW-Authenticate header")
    if 'invoice' not in pairs:
        raise ValueError("L402: missing invoice in WWW-Authenticate header")

    return {
        'scheme': scheme,
        'token': pairs['token'],
        'invoice': pairs['invoice'],
        'raw_pairs': pairs,
    }


def build_l402_authorization(token, preimage):
    """Build the Authorization header value after paying the invoice.

    Format: L402 <token>:<preimage>

    Args:
        token: The macaroon/token from the WWW-Authenticate challenge.
        preimage: 64-char hex preimage from paying the bolt11 invoice.

    Returns:
        String for the Authorization header.
    """
    return f"L402 {token}:{preimage}"


def handle_l402(www_authenticate, nwc_url):
    """Handle an L402 payment challenge.

    Parses the WWW-Authenticate header, extracts the invoice, and returns
    everything needed for the caller to pay and retry.

    Args:
        www_authenticate: Raw WWW-Authenticate header value.
        nwc_url: NWC connection URL (unused by handler, passed for symmetry).

    Returns:
        dict with:
            token: The L402 token/macaroon.
            invoice: BOLT-11 invoice to pay.
            build_auth: Callable(preimage) → Authorization header value.
    """
    details = parse_l402_header(www_authenticate)

    return {
        'protocol': 'l402',
        'token': details['token'],
        'invoice': details['invoice'],
        'build_auth': lambda preimage: build_l402_authorization(
            details['token'], preimage),
    }
