#!/usr/bin/env python3
"""
Fiat/Satoshi Conversion — Pure Python, urllib-only.

Converts between fiat currencies (USD, EUR, etc.) and satoshis using
the CoinGecko free API. No API key required.

Usage:
    from nwc_fiat import fiat_to_sats, sats_to_fiat
    sats = fiat_to_sats(10, 'USD')   # "10 USD → sats"
    usd = sats_to_fiat(1000, 'EUR')  # "1000 sats → EUR"
"""

import json
import sys
import urllib.request

COINGECKO_URL = (
    'https://api.coingecko.com/api/v3/simple/price'
    '?ids=bitcoin&vs_currencies={currency}'
)


def _get_btc_price(currency):
    """Get BTC price in the given fiat currency from CoinGecko."""
    url = COINGECKO_URL.format(currency=currency.lower())
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get('bitcoin', {}).get(currency.lower())
    except Exception as e:
        raise RuntimeError(f"Failed to fetch BTC/{currency} price: {e}")


def fiat_to_sats(amount, currency='USD'):
    """Convert a fiat amount to satoshis.

    Args:
        amount: Fiat amount (e.g., 10.50).
        currency: Currency code (e.g., 'USD', 'EUR', 'BRL').

    Returns:
        dict with amount_in_fiat, currency, btc_price, amount_sats.
    """
    btc_price = _get_btc_price(currency)
    if not btc_price or btc_price <= 0:
        raise RuntimeError(f"Invalid BTC price for {currency}")

    btc_amount = amount / btc_price
    sats = int(btc_amount * 100_000_000)

    return {
        'amount': amount,
        'currency': currency.upper(),
        'btc_price': btc_price,
        'amount_sats': sats,
    }


def sats_to_fiat(sats, currency='USD'):
    """Convert satoshis to a fiat amount.

    Args:
        sats: Integer satoshis.
        currency: Currency code.

    Returns:
        dict with amount_sats, fiat_amount, currency, btc_price.
    """
    btc_price = _get_btc_price(currency)
    if not btc_price or btc_price <= 0:
        raise RuntimeError(f"Invalid BTC price for {currency}")

    btc_amount = sats / 100_000_000
    fiat = btc_amount * btc_price

    return {
        'amount_sats': sats,
        'fiat_amount': round(fiat, 2),
        'currency': currency.upper(),
        'btc_price': btc_price,
    }
