class UnexpectedEmptyPageError(Exception):
    pass
class HTTPError(Exception):
    def __init__(self, url='', status=500, retry=False):
        self.url = url
        self.status = status
        self.retry = retry
    def __str__(self):
        return f"Page request resulted in HTTP {self.status} ({self.url})"

class Result:
    class Author:
        def __init__(self, name):
            self.name = name

    def __init__(self):
        self.entry_id = ''
        self.title = ''
        self.summary = ''
        self.published = None
        self.updated = None
        self.primary_category = None
        self.categories = []
        self.pdf_url = ''
        self.authors = []

    def download_pdf(self, dirpath=None):
        return ''

class SortCriterion:
    Relevance = 'relevance'
    LastUpdatedDate = 'lastUpdatedDate'
    SubmittedDate = 'submittedDate'

def Search(*args, **kwargs):
    class _Search:
        def __init__(self, *a, **kw):
            pass
        def results(self):
            return []
    return _Search()


