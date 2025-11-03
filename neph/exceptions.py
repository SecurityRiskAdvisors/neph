from .log import logger


class LoggedException(Exception):
    """Base exception class that also writes to the project's log file"""

    ERROR_TYPE = "error"

    def __init__(self, message):
        self.message = message
        getattr(logger, LoggedException.ERROR_TYPE)(self.message)
        super().__init__(self.message)


class SimulationRequestError(LoggedException):
    """Raised when a request to the Simulator returns a non-200 HTTP response code"""

    pass


class NodeNotFound(LoggedException):
    """Raised when node could not be found in graph"""

    pass


class NodeTableNotFound(LoggedException):
    """Raised when node table could not be found in nodes"""

    pass


class NodePropertyError(LoggedException):
    """Raised for issues reading node properties"""

    pass


class EdgeTableNotFound(LoggedException):
    """Raised when edge table could not be found in edges"""

    pass


class Unsupported(LoggedException):
    """Internal version of NotImplementedError"""

    pass
