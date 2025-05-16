_.py
New
+22
-0

class Fragment:
    def __init__(self, content, source=None):
        self.content = content
        self.source = source
    def __str__(self):
        return self.content

class Attachment:
    def __init__(self, content, source=None):
        self.content = content
        self.source = source

# Simple hookimpl decorator
def hookimpl(func=None):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    if func is None:
        return wrapper
    return func

# plugins submodule will provide pm
from . import plugins