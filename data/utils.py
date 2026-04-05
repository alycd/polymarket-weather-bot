import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def retry(exceptions, tries=3, delay=2, backoff=2):
    """
    Retry decorator with exponential backoff.
    """
    def decorator(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    msg = f"{e}, Retrying in {mdelay} seconds..."
                    logger.warning(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry
    return decorator
