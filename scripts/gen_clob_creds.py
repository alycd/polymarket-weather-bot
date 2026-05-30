"""
Generate Polymarket CLOB API credentials from your private key.
Run once, then paste the output into .env.

Usage:
    source venv/bin/activate
    python scripts/gen_clob_creds.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
if not private_key or private_key == "REPLACE_ME":
    print("ERROR: Set POLYMARKET_PRIVATE_KEY in .env first")
    raise SystemExit(1)

proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip()
sig_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))

if sig_type == 1 and not proxy_address:
    print("ERROR: POLYMARKET_SIGNATURE_TYPE=1 requires POLYMARKET_PROXY_ADDRESS to be set")
    raise SystemExit(1)

from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=POLYGON,
    key=private_key,
    signature_type=sig_type,
    funder=proxy_address if sig_type == 1 else None,
)

creds = client.create_or_derive_api_creds()
print("\nPaste these into your .env:\n")
print(f"POLYMARKET_API_KEY={creds.api_key}")
print(f"POLYMARKET_API_SECRET={creds.api_secret}")
print(f"POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")
print("\nDone.")
