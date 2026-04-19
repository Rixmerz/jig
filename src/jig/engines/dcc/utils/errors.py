"""Custom exceptions for BigContext MCP."""


class BigContextError(Exception):
    """Base exception for BigContext MCP."""

    pass


class DocumentNotFoundError(BigContextError):
    """Document not found in database."""

    def __init__(self, document_id: int | None = None, path: str | None = None):
        if document_id:
            message = f"Document with ID {document_id} not found"
        elif path:
            message = f"Document at path '{path}' not found"
        else:
            message = "Document not found"
        super().__init__(message)


class SegmentNotFoundError(BigContextError):
    """Segment not found in database."""

    def __init__(self, segment_id: int):
        super().__init__(f"Segment with ID {segment_id} not found")


class ParseError(BigContextError):
    """Error parsing document."""

    def __init__(self, path: str, reason: str):
        super().__init__(f"Failed to parse '{path}': {reason}")


class UnsupportedFormatError(BigContextError):
    """Unsupported document format."""

    def __init__(self, format: str):
        super().__init__(f"Unsupported document format: {format}")


class DatabaseError(BigContextError):
    """Database operation error."""

    pass


class ValidationError(BigContextError):
    """Validation error in extraction validators."""

    pass
