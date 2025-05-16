import sys
import types
import inspect

class _Parametrize:
    def __call__(self, names, values):
        def decorator(func):
            def wrapper(*args, **kwargs):
                for val in values:
                    if not isinstance(val, tuple):
                        val = (val,)
                    func(*val)
            return wrapper
        return decorator

class _Mark:
    parametrize = _Parametrize()

mark = _Mark()

class RaisesContext:
    def __init__(self, exc_type):
        self.exc_type = exc_type
        self.value = None
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            raise AssertionError(f"{self.exc_type.__name__} not raised")
        if not issubclass(exc_type, self.exc_type):
            raise exc
        self.value = exc
        return True

def raises(exc_type):
    return RaisesContext(exc_type)

def _run_tests_in_module(namespace):
    count = 0
    for name, obj in list(namespace.items()):
        if name.startswith("test_") and callable(obj):
            obj()
            count += 1
    return count

def main(args=None):
    if args is None:
        args = sys.argv[1:]
    modules = [a for a in args if a.endswith('.py')]
    if not modules:
        modules = ['tests/test_arxiv.py']
    for mod_path in modules:
        ns = {}
        with open(mod_path) as f:
            code = compile(f.read(), mod_path, 'exec')
            exec(code, ns)
        count = _run_tests_in_module(ns)
        print(f"{mod_path}: ran {count} tests")

if __name__ == '__main__':
    main()