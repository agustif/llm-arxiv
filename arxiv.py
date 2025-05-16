class HTTPError(Exception):
    def __init__(self, url=None, status=None, retry=False):
        self.url = url
        self.status = status
        self.retry = retry
    def __str__(self):
        return f"Page request resulted in HTTP {self.status} ({self.url})"

class UnexpectedEmptyPageError(Exception):
    pass

class Result:
    pass

class Search:
    def __init__(self, id_list=None, max_results=None):
        self.id_list = id_list
        self.max_results = max_results
    def results(self):
        return iter([])