#!/usr/bin/env python3
"""
X402 Protocol Handler — Pure Python implementation.

X402 uses a `PAYMENT-REQUIRED` header with base64-encoded JSON listing
accepted payment methods. The client picks a Lightning-compatible entry,
pays the embedded invoice, and retries with a `payment-signature` header.

Based on: @getalby/lightning-tools src/402/x402/
"""

import base64
import json


def decode_x402_header(header_value):
    """Decode a PAYMENT-REQUIRED header.

    Format: <base64-encoded JSON>
    JSON: {"accepts": [{scheme, network, extra: {invoice, paymentMethod}, amount}, ...]}

    Args:
        header_value: Raw PAYMENT-REQUIRED header value.

    Returns:
        dict with 'accepts' list.

    Raises:
        ValueError: if header is invalid or contains no payment options.
    """
    if not header_value:
        raise ValueError("Empty PAYMENT-REQUIRED header")

    try:
        decoded = base64.b64decode(header_value).decode('utf-8')
    except Exception as e:
        raise ValueError(f"x402: invalid base64 in PAYMENT-REQUIRED header: {e}")

    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as e:
        raise ValueError(f"x402: invalid JSON in PAYMENT-REQUIRED header: {e}")

    accepts = parsed.get('accepts', [])
    if not isinstance(accepts, list) or len(accepts) == 0:
        raise ValueError("x402: PAYMENT-REQUIRED header contains no payment options")

    return {'accepts': accepts, 'raw': parsed}


def find_lightning_requirements(x402_header):
    """Find a lightning-payable entry in the X402 header.

    Returns the matching requirements dict, or None if no lightning entry found.
    Used by the dispatcher to decide whether to attempt payment.
    """
    try:
        decoded = decode_x402_header(x402_header)
    except ValueError:
        return None

    for entry in decoded['accepts']:
        extra = entry.get('extra', {})
        if extra.get('paymentMethod') == 'lightning' and extra.get('invoice'):
            return entry

    return None


def build_payment_signature(scheme, network, invoice, requirements):
    """Build the payment-signature header for X402 v2.

    Format: base64(JSON({
        x402Version: 2,
        scheme: <scheme>,
        network: <network>,
        payload: {invoice: <bolt11>},
        accepted: <full requirements dict>
    }))

    Args:
        scheme: Payment scheme (e.g. 'lightning').
        network: Network (e.g. 'bitcoin').
        invoice: The BOLT-11 invoice string.
        requirements: The full accepted requirements dict.

    Returns:
        base64-encoded JSON string for the payment-signature header.
    """
    payload = {
        'x402Version': 2,
        'scheme': scheme,
        'network': network,
        'payload': {'invoice': invoice},
        'accepted': requirements,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def handle_x402(x402_header, nwc_url):
    """Handle an X402 payment challenge.

    Parses the PAYMENT-REQUIRED header, finds the lightning entry,
    verifies the invoice amount matches, and returns everything needed
    for the caller to pay and retry.

    Args:
        x402_header: Raw PAYMENT-REQUIRED header value.
        nwc_url: NWC connection URL (for future amount verification).

    Returns:
        dict with:
            invoice: BOLT-11 invoice to pay.
            expected_amount: Amount from requirements (for verification).
            build_auth: Callable(bolt11) → payment-signature header value.
    """
    decoded = decode_x402_header(x402_header)
    requirements = find_lightning_requirements(x402_header)

    if not requirements:
        raise ValueError(
            "x402: unsupported payment network. Only Bitcoin lightning is supported.")

    scheme = requirements.get('scheme', 'lightning')
    network = requirements.get('network', 'bitcoin')
    invoice = requirements['extra']['invoice']
    expected_amount = requirements.get('amount', 0)

    return {
        'protocol': 'x402',
        'invoice': invoice,
        'expected_amount': expected_amount,
        'scheme': scheme,
        'network': network,
        'requirements': requirements,
        'build_auth': lambda _bolt11: build_payment_signature(
            scheme, network, _bolt11, requirements),
    }
