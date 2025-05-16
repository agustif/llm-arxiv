class Fragment(str):
    def __new__(cls, text, source=None):
        obj = str.__new__(cls, text)
        obj.source = source
        return obj

def hookimpl(func=None, **kwargs):
    # Decorator that returns the function unchanged
    if func is None:
        def wrapper(f):
            return f
        return wrapper
    return func