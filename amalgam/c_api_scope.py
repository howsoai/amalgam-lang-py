import gc


class CAPIScope:
    """
    A variable scope which aggressively garbage collects on exit.

    Use as a context manager, any attributes assigned are deleted on close,
    Then the garbage collector is called. Note that the GC will collect
    across all of Python, not just the deleted vars within this scope.

    NOTE: This is not something that should be used in normal circumstances. It
    is created to aggressively manage buffer handles into C-API objects to
    ensure that the C-side releases memory for said buffers.
    """

    def _hard_delete_attrs(self):
        for attr in list(self.__dict__.keys()):
            del self.__dict__[attr]
        gc.collect()

    def __enter__(self):
        """Enter the context manager."""
        return self

    def __exit__(self, type, value, traceback):
        """Exit the context manager."""
        self._hard_delete_attrs()
