from contextlib import contextmanager
import gc
import logging

_logger = logging.getLogger(__name__)


class _Vars:
    """Simple class whose instances can be assigned an attribute."""


class CAPIScopeManager:
    """
    A variable scope which aggressively garbage collects on exit.

    Use as a context manager, any attributes assigned are deleted on close,
    Then the garbage collector is called. Note that the GC will collect
    across all of Python, not just the deleted vars within this scope.

    NOTE: This is not something that should be used in normal circumstances. It
    is created to aggressively manage buffer handles into C-API objects to
    ensure that the C-side releases memory for said buffers.

    Parameters
    ----------
    gc_interval : int, default None
        The number of operations (scopes) before garbage collecting. None
        means no garbage collection will be forced to occur.
    """

    def __init__(self, gc_interval=None):
        if isinstance(gc_interval, int):
            self._gc_interval = max(0, gc_interval - 1)
        else:
            self.gc_interval = None
        self._op_count = 0

    def _gc(self):
        if self._gc_interval is not None:
            if self._op_count >= self._gc_interval:
                _logger.debug("Collecting Garbage")
                gc.collect()
                self._op_count = 0
            else:
                self._op_count += 1

    @contextmanager
    def capi_scope(self):
        """Implement a context for managing vars."""
        scope_vars = _Vars()
        try:
            yield scope_vars
        finally:
            del scope_vars
            self._gc()
