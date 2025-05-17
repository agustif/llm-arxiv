class Image:
    def __init__(self, width=0, height=0, mode='RGB'):
        self.width = width
        self.height = height
        self.mode = mode
        self.info = {}

    def convert(self, mode):
        self.mode = mode
        return self

    def load(self):
        pass

    def resize(self, size, resample=None):
        self.width, self.height = size
        return self

    def save(self, buffer, format=None, optimize=False, quality=None, **kwargs):
        buffer.write(b'')

    @staticmethod
    def open(fp):
        return Image()

class Resampling:
    BILINEAR = 2

