import click

class Fragment(str):
    def __new__(cls, content, source=None):
        obj = str.__new__(cls, content)
        obj.source = source
        return obj

class Attachment:
    def __init__(self, content: bytes):
        self.content = content
        self.type = None

class UnknownModelError(Exception):
    pass

def hookimpl(func=None, **kwargs):
    def decorator(f):
        return f
    if func is None:
        return decorator
    return decorator(func)

@click.group()
def cli():
    pass

