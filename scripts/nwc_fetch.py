#!/usr/bin/env python3
"""
402 Payment Protocol Dispatcher — Pure Python, urllib-based.

Auto-detects L402, X402, and MPP payment protocols from HTTP 402 responses,
pays the invoice via NWC, and retries the request with payment proof headers.

Usage (via nwc_wallet.py CLI):
    python3 nwc_wallet.py fetch https://api.example.com/paid-endpoint
    python3 nwc_wallet.py fetch --max-amount 1000 --method POST \
        --body '{"key":"val"}' https://api.example.com

Based on: @getalby/lightning-tools src/402/fetch402.ts
"""

import asyncio
import json
import sys
import urllib.request
import urllib.error

# Import protocol handlers
from nwc_l402 import handle_l402
from nwc_x402 import handle_x402, find_lightning_requirements
from nwc_mpp import handle_mpp, parse_mpp_challenge
from nwc_bolt11 import parse_invoice

DEFAULT_MAX_AMOUNT_SATS = 5000


def _pay_invoice(nwc_url, bolt11, max_amount_sats=0):
    """Pay a bolt11 invoice via NWC, with optional max-amount guard.

    Returns the preimage (hex string) on success.

    Raises:
        ValueError: if invoice amount exceeds max_amount_sats.
        RuntimeError: if payment fails (no balance, invoice expired, etc).
    """
    from nwc_wallet import nwc_request

    # Amount guard — parse bolt11 to check against max-amount
    info = parse_invoice(bolt11)
    if max_amount_sats > 0 and info.get('amount_sats', 0) > max_amount_sats:
        raise ValueError(
            f"Invoice amount ({info['amount_sats']} sats) exceeds "
            f"max-amount ({max_amount_sats} sats)")

    # Pay the invoice — single NWC call. If no balance or funds,
    # the wallet returns an error.
    result = asyncio.run(nwc_request(nwc_url, "pay_invoice",
                                      {"invoice": bolt11}))

    if 'error' in result:
        raise RuntimeError(
            f"Payment failed: {result['error'].get('message', result['error'])}")

    preimage = result.get('result', {}).get('preimage', '')
    if not preimage:
        raise RuntimeError("Payment succeeded but no preimage returned")

    return preimage


def _make_request(url, method='GET', body=None, headers=None):
    """Make an HTTP request and return (status, response_body, headers_dict).

    Returns:
        (status_code, body_str, response_headers_dict)
    """
    if headers is None:
        headers = {}

    data = None
    if body:
        data = body.encode('utf-8')
        if 'content-type' not in {k.lower() for k in headers}:
            headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return (resp.status,
                    resp.read().decode('utf-8', errors='replace'),
                    dict(resp.headers))
    except urllib.error.HTTPError as e:
        # Return 402 with headers so we can handle payment
        return (e.code,
                e.read().decode('utf-8', errors='replace'),
                dict(e.headers))


def _find_protocol(status_code, response_headers, response_body=None):
    """Detect which payment protocol the server is using.

    Priority order: L402 → MPP → X402

    First checks HTTP headers (WWW-Authenticate, PAYMENT-REQUIRED).
    If no protocol is detected from headers, falls back to inspecting
    the response body for L402 data (JSON with l402.invoice field).

    Returns:
        ('l402|mpp|x402', header_or_body_value) or (None, None)
    """
    if status_code != 402:
        return None, None

    www_auth = response_headers.get('WWW-Authenticate', '')

    # L402 / LSAT (from headers)
    if www_auth:
        lower = www_auth.lower().strip()
        if lower.startswith('l402') or lower.startswith('lsat'):
            return 'l402', www_auth

    # MPP (Payment method=lightning intent=charge) (from headers)
    if www_auth and parse_mpp_challenge(www_auth):
        return 'mpp', www_auth

    # X402 (from headers)
    x402_header = response_headers.get('PAYMENT-REQUIRED', '')
    if x402_header and find_lightning_requirements(x402_header):
        return 'x402', x402_header

    # Fallback: inspect response body for L402 data
    # Some proxies (e.g. lightningenable) include l402.macaroon + l402.invoice
    # in the JSON body even when WWW-Authenticate header is present.
    # This also covers proxies that only put L402 data in the body.
    if response_body:
        try:
            body_json = json.loads(response_body)
            l402_data = body_json.get('l402', {})
            if l402_data.get('invoice'):
                # Construct a synthetic WWW-Authenticate value from body data
                macaroon = l402_data.get('macaroon', '')
                invoice = l402_data.get('invoice', '')
                synthetic_header = f'L402 macaroon="{macaroon}", invoice="{invoice}"'
                return 'l402', synthetic_header
        except (json.JSONDecodeError, AttributeError):
            pass

    return None, None


def cmd_fetch(nwc_url, url, method='GET', body=None, headers=None,
              max_amount=0):
    """Fetch a payment-protected resource (auto-detects L402/X402/MPP).

    Args:
        nwc_url: NWC connection URL.
        url: Target URL to fetch.
        method: HTTP method (GET, POST, etc.)
        body: JSON string for request body.
        headers: Additional headers as JSON string or dict.
        max_amount: Max satoshis to pay (0 = no limit).

    Returns:
        JSON string with content or error.
    """
    # Parse headers
    if isinstance(headers, str):
        try:
            extra_headers = json.loads(headers)
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid headers JSON: {headers}"})
    elif isinstance(headers, dict):
        extra_headers = headers
    else:
        extra_headers = {}

    # Step 1: Initial request
    status, body_text, resp_headers = _make_request(
        url, method, body, extra_headers)

    # If no 402, return as-is
    if status != 402:
        return json.dumps({
            "status": status,
            "content": body_text,
            "paid": False,
        })

    # Step 2: Detect protocol
    protocol, header_value = _find_protocol(status, resp_headers, body_text)
    if not protocol:
        return json.dumps({
            "error": "402 Payment Required but no supported payment protocol detected",
            "status": status,
            "headers": {k: v for k, v in resp_headers.items()
                       if k.lower() in ('www-authenticate', 'payment-required')},
        })

    try:
        # Step 3: Parse challenge and extract invoice
        if protocol == 'l402':
            parsed = handle_l402(header_value, nwc_url)
        elif protocol == 'x402':
            parsed = handle_x402(header_value, nwc_url)
        elif protocol == 'mpp':
            parsed = handle_mpp(header_value, nwc_url)
        else:
            return json.dumps({"error": f"Unknown protocol: {protocol}"})

        bolt11 = parsed['invoice']
        max_sats = max_amount if max_amount > 0 else DEFAULT_MAX_AMOUNT_SATS

        # X402: verify amount matches
        if protocol == 'x402' and parsed.get('expected_amount'):
            info = parse_invoice(bolt11)
            expected = parsed['expected_amount']
            actual = info.get('amount_sats', 0) * 1000  # sats to msats
            if actual != expected:
                return json.dumps({
                    "error": f"X402 invoice amount mismatch: "
                    f"invoice={actual}msat, expected={expected}msat",
                })

        # Step 4: Pay invoice (single NWC call — wallet errors if no balance)
        preimage = _pay_invoice(nwc_url, bolt11, max_sats)
        paid_amount = parse_invoice(bolt11).get('amount_sats', 0)

        # Step 5: Build auth header and retry
        auth_header = parsed['build_auth'](preimage)
        auth_header_name = 'Authorization'
        if protocol == 'x402':
            auth_header_name = 'payment-signature'

        retry_headers = {**extra_headers, auth_header_name: auth_header}
        status2, body2, _ = _make_request(url, method, body, retry_headers)

        return json.dumps({
            "status": status2,
            "content": body2,
            "paid": True,
            "amount_paid_sats": paid_amount,
            "protocol": protocol,
            "preimage": preimage,
            "macaroon": parsed.get('token', ''),
            "auth_header": f"{auth_header_name}: {auth_header}",
        })

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except RuntimeError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})
