"""
Debug CLOB authentication. Run to check connectivity and account registration.

Usage:
    python scripts/debug_clob_auth.py
"""
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

pk = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
proxy = os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip()
sig_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "1"))

if not pk or pk == "REPLACE_ME":
    print("ERROR: Set POLYMARKET_PRIVATE_KEY in .env first")
    raise SystemExit(1)

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=pk,
    signature_type=sig_type,
    funder=proxy or None,
)

print(f"Signature type : {sig_type}")
print(f"EOA address    : {client.get_address()}")
print(f"Proxy address  : {proxy or '(none)'}")
print()

print("1. Testing basic connectivity (get_ok)...")
try:
    print("  ", client.get_ok())
except Exception as e:
    print("   FAILED:", e)

print("2. Testing balance/allowance (requires registered account)...")
try:
    result = client.get_balance_allowance({"asset_type": "USDC"})
    print("   ", result)
except Exception as e:
    print("   FAILED:", e)

print("3. Attempting create_api_key...")
try:
    creds = client.create_api_key()
    print()
    print("SUCCESS — paste these into .env:")
    print(f"  POLYMARKET_API_KEY={creds.api_key}")
    print(f"  POLYMARKET_API_SECRET={creds.api_secret}")
    print(f"  POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")
except Exception as e:
    print("   FAILED:", e)

print("4. Attempting create_or_derive_api_creds (EOA-only, no proxy)...")
try:
    from py_clob_client.constants import POLYGON
    client2 = ClobClient(
        host="https://clob.polymarket.com",
        key=pk,
        chain_id=POLYGON,
    )
    creds = client2.create_or_derive_api_creds()
    print()
    print("SUCCESS — paste these into .env:")
    print(f"  POLYMARKET_API_KEY={creds.api_key}")
    print(f"  POLYMARKET_API_SECRET={creds.api_secret}")
    print(f"  POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")
except Exception as e:
    print("   FAILED:", e)
