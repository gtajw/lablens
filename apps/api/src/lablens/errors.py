class Problem(Exception):
    def __init__(self, code: str, message: str, status: int = 422, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details or {}


def missing():
    raise Problem("RESOURCE_NOT_FOUND", "This item is unavailable in your workspace.", 404)
