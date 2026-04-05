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

from py_clob_client.client import ClobClient

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=private_key,
    signature_type=0,  # EOA wallet (MetaMask-style)
)

creds = client.create_api_key()
print("\nPaste these into your .env:\n")
print(f"POLYMARKET_API_KEY={creds.api_key}")
print(f"POLYMARKET_API_SECRET={creds.api_secret}")
print(f"POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")
print("\nDone.")
