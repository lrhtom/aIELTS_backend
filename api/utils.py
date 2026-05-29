

import functools
from asgiref.sync import async_to_sync

def adrf_sync(f):
    sync_f = async_to_sync(f)
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return sync_f(*args, **kwargs)
    return wrapper


import functools
from asgiref.sync import async_to_sync

def adrf_sync(f):
    sync_f = async_to_sync(f)
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return sync_f(*args, **kwargs)
    return wrapper
