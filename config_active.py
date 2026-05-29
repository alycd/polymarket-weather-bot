"""
Active config selector. Import from this module everywhere instead of config.
Picks live_config or paper_config based on sys.argv at import time.
"""
import sys

if '--live' in sys.argv:
    from live_config import *   # noqa: F401, F403
else:
    from paper_config import *  # noqa: F401, F403
