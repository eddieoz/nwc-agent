#!/usr/bin/env python3
"""
MPP Protocol Handler — Pure Python implementation.

MPP (draft-lightning-charge-00) uses a WWW-Authenticate header:
    Payment method="lightning", intent="charge",
             id="<id>", realm="<realm>", request="<base64url>"

The request (base64url-decoded) contains a JCS-canonicalized JSON with
the BOLT-11 invoice. Client pays and retries with:
    Authorization: Payment <base64url JCS credential with preimage>

Uses JSON Canonicalization Scheme (RFC 8785) for deterministic encoding.

Based on: @getalby/lightning-tools src/402/mpp/
"""

import base64
import json
import re


# ─── Base64URL ─────────────────────────────────────────────────────────

def _base64url_encode(data):
    """Encode bytes to base64url (no padding)."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _base64url_decode(s):
    """Decode base64url string (padding optional)."""
    # Add padding if needed
    missing = len(s) % 4
    if missing:
        s += '=' * (4 - missing)
    return base64.urlsafe_b64decode(s)


# ─── JCS (JSON Canonicalization Scheme, RFC 8785) ────────────────────

def _jcs_serialize(obj):
    """Serialize a Python value using JCS (RFC 8785).

    - Object keys sorted lexicographically.
    - No whitespace.
    - Strings use JSON escaping.
    - Numbers serialized without unnecessary digits.
    """
    if obj is None:
        return 'null'
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    if isinstance(obj, (int, float)):
        # Use repr for numbers to avoid scientific notation
        return json.dumps(obj)  # Python's json handles this correctly
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, list):
        items = [_jcs_serialize(item) for item in obj]
        return '[' + ','.join(items) + ']'
    if isinstance(obj, dict):
        keys = sorted(obj.keys())
        items = [json.dumps(k, ensure_ascii=False) + ':' + _jcs_serialize(obj[k])
                 for k in keys]
        return '{' + ','.join(items) + '}'
    return json.dumps(obj)


# ─── Challenge Parser ──────────────────────────────────────────────────

def parse_mpp_challenge(www_authenticate):
    """Parse a WWW-Authenticate: Payment ... header.

    Expected format:
        Payment id="<id>", realm="<realm>", method="lightning",
                intent="charge", request="<base64url>"
                [, expires="<rfc3339>"]

    Returns a dict with challenge fields, or None if not a valid
    lightning charge challenge.
    """
    if not www_authenticate:
        return None

    header = www_authenticate.strip()
    if not header.lower().startswith('payment'):
        return None

    # Parse key="value" and key='value' and key=value
    rest = header[len('payment'):].strip()
    result = {}
    pattern = re.compile(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|([^,\s]*))')
    for match in pattern.finditer(rest):
        key = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4) or ''
        result[key] = value

    # Validate required fields
    if (result.get('method') != 'lightning' or
            result.get('intent') != 'charge' or
            not result.get('id') or
            not result.get('realm') or
            not result.get('request')):
        return None

    challenge = {
        'id': result['id'],
        'realm': result['realm'],
        'method': result['method'],
        'intent': result['intent'],
        'request': result['request'],
    }
    if 'expires' in result:
        challenge['expires'] = result['expires']

    return challenge


def decode_mpp_request(request_b64url):
    """Decode the base64url-encoded MPP charge request.

    Returns:
        dict with amount, currency, description, methodDetails (invoice).
    """
    raw = _base64url_decode(request_b64url).decode('utf-8')
    return json.loads(raw)


def build_mpp_credential(challenge, preimage):
    """Build the MPP credential for the Authorization header.

    Per spec: credential is a base64url-encoded JCS JSON object:
        {
            "challenge": {id, intent, method, realm, request[, expires]},
            "payload": {"preimage": "<hex>"}
        }

    Keys are sorted lexicographically at every level per JCS.

    Args:
        challenge: Dict from parse_mpp_challenge().
        preimage: 64-char hex payment preimage.

    Returns:
        base64url-encoded credential string.
    """
    # Echo challenge params (same keys as received, plus intent/method)
    challenge_echo = {
        'id': challenge['id'],
        'intent': challenge['intent'],
        'method': challenge['method'],
        'realm': challenge['realm'],
        'request': challenge['request'],
    }
    if 'expires' in challenge:
        challenge_echo['expires'] = challenge['expires']

    credential = {
        'challenge': challenge_echo,
        'payload': {'preimage': preimage},
    }

    jcs_json = _jcs_serialize(credential)
    return _base64url_encode(jcs_json.encode('utf-8'))


def build_mpp_authorization(credential):
    """Build the Authorization header value.

    Format: Payment <base64url-credential>
    """
    return f"Payment {credential}"


# ─── Main Handler ──────────────────────────────────────────────────────

def handle_mpp(www_authenticate, nwc_url):
    """Handle an MPP payment challenge.

    Parses the WWW-Authenticate header, decodes the charge request,
    and returns everything needed for the caller to pay and retry.

    Args:
        www_authenticate: Raw WWW-Authenticate header value.
        nwc_url: NWC connection URL (unused here, passed for symmetry).

    Returns:
        dict with:
            invoice: BOLT-11 invoice to pay.
            build_auth: Callable(preimage) → Authorization header value.
            challenge: The parsed challenge dict.
            request: The decoded charge request dict.

    Raises:
        ValueError: if challenge is invalid or invoice is missing.
    """
    challenge = parse_mpp_challenge(www_authenticate)
    if not challenge:
        raise ValueError(
            "mpp: invalid or unsupported WWW-Authenticate challenge "
            "(expected Payment method=lightning intent=charge)")

    try:
        request = decode_mpp_request(challenge['request'])
    except Exception as e:
        raise ValueError(
            f"mpp: invalid request auth-param (not valid base64url JSON): {e}")

    invoice = request.get('methodDetails', {}).get('invoice')
    if not invoice:
        raise ValueError("mpp: missing invoice in charge request")

    return {
        'protocol': 'mpp',
        'invoice': invoice,
        'challenge': challenge,
        'request': request,
        'build_auth': lambda preimage: build_mpp_authorization(
            build_mpp_credential(challenge, preimage)),
    }
