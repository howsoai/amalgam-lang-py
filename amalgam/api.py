from __future__ import annotations

from base64 import b64encode
from datetime import datetime
import gc
import json as json_lib
import logging
from pathlib import Path
import platform
import re
import threading
import typing as t
import warnings

from amalgam._native import load_native_library
from amalgam._types import LoadStatusTuple

# Set to amalgam
_logger = logging.getLogger('amalgam')


class LoadEntityStatus:
    """
    Status returned by :func:`~api.Amalgam.load_entity` and related methods.

    Parameters
    ----------
    loaded : bool, default True
        Whether the entity loaded.
    message : str or None, default ""
        The engine's message, typically an error description.
    version : str or None, default ""
        The Amalgam version recorded in the loaded content.
    entity_path : list of str or None, optional
        The path of the contained entity the content was loaded into.
    """

    def __init__(
        self,
        *,
        loaded: bool = True,
        message: str | None = "",
        version: str | None = "",
        entity_path: list[str | None] | None = None,
    ) -> None:
        self.loaded = loaded
        self.message = message
        self.version = version
        self.entity_path = entity_path if entity_path is not None else []

    @classmethod
    def _from_native(cls, status: LoadStatusTuple) -> LoadEntityStatus:
        """Build a status from a native backend's ``(loaded, message, version, entity_path)`` tuple."""
        loaded, message, version, entity_path = status
        return cls(loaded=loaded, message=message, version=version, entity_path=entity_path)

    def __str__(self) -> str:
        """
        Return a human-readable string representation.

        Returns
        -------
        str
            The human-readable string representation.
        """
        ep = ""
        if self.entity_path:
            eps = (f'"{step}"' for step in self.entity_path)
            ep = f",[{','.join(eps)}]"
        return f"{self.loaded},\"{self.message}\",\"{self.version}\"{ep}"


class ResultWithLog:
    """
    Return value from :func:`~api.Amalgam.execute_entity_json_logged`.

    Parameters
    ----------
    json : bytes | None
        The JSON-format response from the Amalgam invocation.
    log : bytes | None
        The Amalgam-syntax transaction-log entry.
    """

    def __init__(self, *, json: bytes | None, log: bytes | None):
        self.json = json
        """The JSON-format response from the Amalgam invocation."""

        self.log = log
        """The Amalgam-syntax transaction-log entry."""


class Amalgam:
    """
    A general python direct interface to the Amalgam library.

    Native calls go through the ``amalgam._api`` C extension when it is available and through ctypes
    otherwise; set the ``AMALGAM_PY_BACKEND`` environment variable to ``c`` or ``ctypes`` to choose one.

    Parameters
    ----------
    library_path : Path or str, optional
        Path to either the amalgam DLL, DyLib or SO (Windows, MacOS
        or Linux, respectively). If not specified it will build a path to the
        appropriate library bundled with the package.

    append_trace_file : bool, default False
        If True, new content will be appended to a trace file if the file
        already exists rather than creating a new file.

    arch : str, optional
        The platform architecture of the embedded Amalgam library.
        If not provided, it will be automatically detected.
        (Note: arm64_8a architecture must be manually specified!)

    execution_trace_dir : str, optional
        A directory path for writing trace files. If ``None``, then
        the current working directory will be used.

    execution_trace_file : str, default "execution.trace"
        The full or relative path to the execution trace used in debugging.

    gc_interval : int, optional
        If set, garbage collection will be forced at the specified
        interval of amalgam operations. Note that this reduces memory
        consumption at the compromise of performance. Only use if models are
        exceeding your host's process memory limit or if paging to disk. As an
        example, if this operation is set to 0 (force garbage collection every
        operation), it results in a performance impact of 150x.
        Default value does not force garbage collection.

    library_postfix : str, optional
        For configuring use of different amalgam builds i.e. -st for
        single-threaded. If not provided, an attempt will be made to detect
        it within library_path. If neither are available, -mt (multi-threaded)
        will be used.

    max_num_threads : int, optional
        If a multithreaded Amalgam binary is used, sets the maximum
        number of threads to the value specified. If 0, will use the number of
        visible logical cores. Default None will not attempt to set this value.

    sbf_datastore_enabled : bool, optional
        If true, sbf tree structures are enabled.

    trace : bool, optional
        If true, enables execution trace file.

    Raises
    ------
    FileNotFoundError
        Amalgam library not found in default location, and not configured to
        retrieve automatically.
    RuntimeError
        The initializer was unable to determine a supported platform or
        architecture to use when no explicit `library_path` was supplied.
    """

    def __init__(  # noqa: C901
        self,
        library_path: t.Optional[Path | str] = None,
        *,
        arch: t.Optional[str] = None,
        append_trace_file: bool = False,
        execution_trace_dir: t.Optional[str] = None,
        execution_trace_file: str = "execution.trace",
        gc_interval: t.Optional[int] = None,
        library_postfix: t.Optional[str] = None,
        max_num_threads: t.Optional[int] = None,
        sbf_datastore_enabled: t.Optional[bool] = None,
        trace: t.Optional[bool] = None,
        **kwargs
    ):
        """Initialize Amalgam instance."""
        # Guards all trace-file state: self._trace, self.execution_trace_filepath
        # and self.load_command_log_entry. Re-entrant so a caller may bracket a
        # whole command/reply group while the _log_* helpers each acquire it
        # again. Created first: set_max_num_threads() below writes to the trace.
        #
        # self._trace may be swapped at any time -- by reset_trace(), or by a
        # caller assigning to the `trace` property to toggle tracing off and
        # back on again. So the _log_* helpers check it twice: once unlocked,
        # to skip the whole block cheaply when tracing is off, and again under
        # the lock, because it may have been set to None while they were
        # waiting to acquire.
        self._trace_lock = threading.RLock()

        if len(kwargs):
            warnings.warn(f'Unexpected keyword arguments '
                          f'[{", ".join(list(kwargs.keys()))}] '
                          f'passed to Amalgam constructor.')

        # Work out path and postfix of the library from the given parameters.
        self.library_path, self.library_postfix = self._get_library_path(
            library_path, library_postfix, arch)

        self.append_trace_file = append_trace_file
        if trace:
            # Determine where to put the trace files ...
            self.base_execution_trace_file = execution_trace_file
            # default to current directory, and expand relative paths ..
            if execution_trace_dir is None:
                self.execution_trace_dir = Path.cwd()
            else:
                self.execution_trace_dir = Path(
                    execution_trace_dir).expanduser().absolute()
            # Create the trace directory if needed
            if not self.execution_trace_dir.exists():
                self.execution_trace_dir.mkdir(parents=True, exist_ok=True)

            # increment a counter on the file name, if file already exists..
            self.execution_trace_filepath = Path(
                self.execution_trace_dir, execution_trace_file)
            if not self.append_trace_file:
                counter = 1
                while self.execution_trace_filepath.exists():
                    self.execution_trace_filepath = Path(
                        self.execution_trace_dir,
                        f'{self.base_execution_trace_file}.{counter}'
                    )
                    counter += 1

            # NOTE: Even though there are getters and setters for the public
            #       API, this class continues to directly access `_trace` for
            #       performance reasons.
            self._trace = self.execution_trace_filepath.open("wb+")
            _logger.debug("Opening Amalgam trace file: "
                          f"{self.execution_trace_filepath}")
        else:
            self._trace = None

        _logger.debug(f"Loading amalgam library: {self.library_path}")
        _logger.debug(f"SBF_DATASTORE enabled: {sbf_datastore_enabled}")
        self.amlg = load_native_library(self.library_path)
        _logger.debug(f"Amalgam backend: {type(self.amlg).__module__}")
        if sbf_datastore_enabled is not None:
            self.set_amlg_flags(sbf_datastore_enabled)
        if max_num_threads is not None:
            self.set_max_num_threads(max_num_threads)
        self.gc_interval = gc_interval
        self.op_count = 0
        self.load_command_log_entry: bytes | None = None

    @property
    def trace(self) -> t.BinaryIO | None:
        """
        The open execution trace file, or None when tracing is disabled.

        Assigning to this swaps the destination under the lock that guards
        trace writes, so it is safe to call while other threads are logging.
        Assign None to suspend tracing and a file object to resume it.

        Note that assigning does not close the outgoing file -- the caller owns
        it, so it can be handed back later to resume. Use
        :func:`~api.Amalgam.reset_trace` to roll over to a fresh file instead.
        """
        return self._trace

    @trace.setter
    def trace(self, value: t.BinaryIO | None) -> None:
        """Swap the execution trace file under the trace lock."""
        with self._trace_lock:
            self._trace = value

    @classmethod
    def _get_allowed_postfixes(cls, library_dir: Path) -> list[str]:
        """
        Return list of all library postfixes allowed given library directory.

        Parameters
        ----------
        library_dir : Path
            The path object to the library directory.

        Returns
        -------
        list of str
            The allowed library postfixes.
        """
        allowed_postfixes = set()
        for file in library_dir.glob("amalgam*"):
            postfix = cls._parse_postfix(file.name)
            if postfix is not None:
                allowed_postfixes.add(postfix)
        return list(allowed_postfixes)

    @classmethod
    def _parse_postfix(cls, filename: str) -> str | None:
        """
        Determine library postfix given a filename.

        Parameters
        ----------
        filename : str
            The filename to parse.

        Returns
        -------
        str or None
            The library postfix of the filename, or None if no postfix.
        """
        matches = re.findall(r'-([^.]+)(?:\.[^.]*)?$', filename)
        if len(matches) > 0:
            return f'-{matches[-1]}'
        else:
            return None

    @classmethod
    def _get_library_path(
        cls,
        library_path: t.Optional[Path | str] = None,
        library_postfix: t.Optional[str] = None,
        arch: t.Optional[str] = None
    ) -> tuple[Path, str]:
        """
        Return the full Amalgam library path and its library_postfix.

        Using the potentially empty parameters passed into the initializer,
        determine and return the prescribed or the correct default path and
        library postfix for the running environment.

        Parameters
        ----------
        library_path : Path or str, optional
            The path to the Amalgam shared library.
        library_postfix : str, optional
            The library type as specified by a postfix to the word
            "amalgam" in the library's filename. E.g., the "-mt" in
            `amalgam-mt.dll`. If left unspecified, "-mt" will be used where
            supported, otherwise "-st".
        arch : str, optional
            The platform architecture of the embedded Amalgam
            library. If not provided, it will be automatically detected.
            (Note: arm64_8a architecture must be manually specified!)

        Returns
        -------
        Path
            The path to the appropriate Amalgam shared lib (.dll, .so, .dylib).
        str
            The library postfix.
        """
        if library_postfix and not library_postfix.startswith("-"):
            # Library postfix must start with a dash
            raise ValueError(
                f'The provided `library_postfix` value of "{library_postfix}" '
                'must start with a "-".'
            )

        if library_path:
            # Find the library postfix, if one is present in the given
            # library_path.
            filename = Path(library_path).name
            _library_postfix = cls._parse_postfix(filename)
            if library_postfix and library_postfix != _library_postfix:
                warnings.warn(
                    'The supplied `library_postfix` does not match the '
                    'postfix given in `library_path` and will be ignored.',
                    UserWarning
                )
            library_postfix = _library_postfix
            library_path = Path(library_path).expanduser()

            if not library_path.exists():
                raise FileNotFoundError(
                    'No Amalgam library was found at the provided '
                    f'`library_path`: "{library_path}". Please check that the '
                    'path is correct.'
                )
        else:
            # No library_path was provided so, auto-determine the correct one
            # to use for this running environment. For this, the operating
            # system, the machine architecture and postfix are used.
            os = platform.system().lower()

            arch_supported = False
            if not arch:
                arch = platform.machine().lower()

                if arch == 'x86_64':
                    arch = 'amd64'
                elif arch.startswith('aarch64') or arch.startswith('arm64'):
                    # see: https://stackoverflow.com/q/45125516/440805
                    arch = 'arm64'

            if os == 'windows':
                path_os = 'windows'
                path_ext = 'dll'
                arch_supported = arch in ['amd64']
            elif os == "darwin":
                path_os = 'darwin'
                path_ext = 'dylib'
                arch_supported = arch in ['amd64', 'arm64']
            elif os == "linux":
                path_os = 'linux'
                path_ext = 'so'
                arch_supported = arch in ['amd64', 'arm64', 'arm64_8a']
            else:
                raise RuntimeError(
                    f'Detected an unsupported machine platform type "{os}". '
                    'Please specify the `library_path` to the Amalgam shared '
                    'library to use with this platform.')

            if not arch_supported:
                raise RuntimeError(
                    f'An unsupported machine architecture "{arch}" was '
                    'detected or provided. Please specify the `library_path` '
                    'to the Amalgam shared library to use with this machine '
                    'architecture.')

            if not library_postfix:
                library_postfix = '-mt' if arch != "arm64_8a" else '-st'

            # Default path for Amalgam binary should be at <package_root>/lib
            lib_root = Path(Path(__file__).parent, 'lib')

            # Build path
            dir_path = Path(lib_root, path_os, arch)
            filename = f'amalgam{library_postfix}.{path_ext}'
            library_path = Path(dir_path, filename)

            if not library_path.exists():
                # First check if invalid postfix, otherwise show generic error
                allowed_postfixes = cls._get_allowed_postfixes(dir_path)
                _library_postfix = cls._parse_postfix(filename)
                if (
                    allowed_postfixes and
                    _library_postfix not in allowed_postfixes
                ):
                    raise RuntimeError(
                        'An unsupported `library_postfix` value of '
                        f'"{_library_postfix}" was provided. Supported options '
                        "for your machine's platform and architecture include: "
                        f'{", ".join(allowed_postfixes)}.'
                    )
                raise FileNotFoundError(
                    'The auto-determined Amalgam library to use was not found '
                    f'at "{library_path}". This could indicate that the '
                    'combination of operating system, machine architecture and '
                    'library-postfix is not yet supported.'
                )

        return library_path, library_postfix

    def is_sbf_datastore_enabled(self) -> bool:
        """
        Return whether the SBF Datastore is implemented.

        Returns
        -------
        bool
            True if sbf tree structures are currently enabled.
        """
        return self.amlg.is_sbf_datastore_enabled()

    def set_amlg_flags(self, sbf_datastore_enabled: bool = True):
        """
        Set various amalgam flags for data structure and compute features.

        Parameters
        ----------
        sbf_datastore_enabled : bool, default True
            If true, sbf tree structures are enabled.
        """
        self.amlg.set_sbf_datastore_enabled(sbf_datastore_enabled)

    def get_max_num_threads(self) -> int:
        """
        Get the maximum number of threads currently set.

        Returns
        -------
        int
            The maximum number of threads that Amalgam is configured to use.
        """
        self._log_execution(b"GET_MAX_NUM_THREADS")
        result = self.amlg.get_max_num_threads()
        self._log_reply(result)

        return result

    def set_max_num_threads(self, max_num_threads: int = 0):
        """
        Set the maximum number of threads.

        Will have no effect if a single-threaded version of Amalgam is used.

        Parameters
        ----------
        max_num_threads : int, default 0
            If a multithreaded Amalgam binary is used, sets the maximum number
            of threads to the value specified. If 0, will use the number of
            visible logical cores.

        Raises
        ------
        ValueError
            If ``max_num_threads`` is negative. Nothing is written to the trace.
        """
        if max_num_threads < 0:
            raise ValueError("max_num_threads must not be negative")
        self._log_execution(f"SET_MAX_NUM_THREADS {max_num_threads}".encode())
        self.amlg.set_max_num_threads(max_num_threads)
        self._log_reply(None)

    def get_num_active_threads(
        self
    ) -> int:
        """
        Return the current number of threads actively executing.

        This is an instantaneous measurement and is only a handful of CPU instructions.
        Due to the nature of task dispatching and task decomposition, it is possible
        that the number of active threads can change very rapidly.  the best way to use
        this method is to aggregate many samples per second with some form of average
        or rolling average over a time period.

        This does not include OpenMP threads in the count.

        Returns
        -------
        int
            The current number of active threads.
        """
        result = self.amlg.get_num_active_threads()

        return result

    def get_garbage_collection_params(self) -> bytes:
        """
        Get native garbage-collection parameters as JSON bytes.

        Parameters are global to the library and shared across entities.

        Returns
        -------
        bytes
            JSON containing the current parameters.
        """
        self._log_execution(b"GET_GARBAGE_COLLECTION_PARAMS")
        result = self.amlg.get_garbage_collection_params()
        self._log_reply(result)

        return result

    def set_garbage_collection_params(
        self,
        json_params: str | bytes
    ) -> None:
        """
        Update native garbage-collection parameters from JSON.

        Parameters are global to the library and shared across entities.
        Omitted keys remain unchanged and unknown keys are ignored. Values
        outside allowed ranges reset that parameter to its default.

        Parameters
        ----------
        json_params : str or bytes
            A JSON object containing any subset of
            min_gc_nodes_threshold, max_gc_nodes_threshold,
            extra_memory_capacity_factor, min_memory_retention_factor,
            and alloc_expansion_factor.
        """
        self._log_execution_std(
            b"SET_GARBAGE_COLLECTION_PARAMS",
            suffix=json_params
        )
        self.amlg.set_garbage_collection_params(json_params)
        self._log_reply(None)

    def reset_trace(self, file: str):
        """
        Close the open trace file and opens a new one with the specified name.

        Parameters
        ----------
        file : str
            The file name for the new execution trace.
        """
        with self._trace_lock:
            if self._trace is None:
                # Trace was not enabled
                return
            _logger.debug(f"Execution trace file being reset: "
                          f"{self.execution_trace_filepath} to be closed ...")
            # Write exit command.
            self._trace.write(b"EXIT\n")
            self._trace.close()
            self.execution_trace_filepath = Path(self.execution_trace_dir, file)

            # increment a counter on the file name, if file already exists..
            if not self.append_trace_file:
                counter = 1
                while self.execution_trace_filepath.exists():
                    self.execution_trace_filepath = Path(
                        self.execution_trace_dir, f'{file}.{counter}')
                    counter += 1

            self._trace = self.execution_trace_filepath.open("wb+")
            _logger.debug(f"New trace file: {self.execution_trace_filepath} "
                          f"opened.")
            # Write load command used to instantiate the amalgam instance.
            if self.load_command_log_entry is not None:
                self._trace.write(self.load_command_log_entry + b"\n")
            self._trace.flush()

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return (f"Amalgam Path:\t\t {self.library_path}\n"
                f"Amalgam GC Interval:\t {self.gc_interval}\n")

    def __del__(self):
        """Implement a "destructor" method to finalize log files, if any."""
        # May run on a partially-constructed instance, so nothing here can
        # assume __init__ finished.
        lock = getattr(self, '_trace_lock', None)
        if lock is None or getattr(self, '_trace', None) is None:
            return
        try:
            with lock:
                if self._trace:
                    self._trace.write(b"EXIT\n")
                    self._trace.flush()
        except Exception:  # noqa - deliberately broad
            pass

    def _log_comment(self, comment: str):
        """
        Log a comment into the execution trace file.

        Allows notes of information not captured in the raw execution commands.

        Parameters
        ----------
        reply : str
            The raw reply string to log.
        """
        # NOTE: We check if `self._trace` is set to avoid setting a lock when
        #       it isn't needed. We check again inside the lock, because the
        #       state of `self._trace` may have changed while waiting to
        #       acquire the lock.
        if self._trace:
            with self._trace_lock:
                if self._trace:
                    self._trace.write(b"# NOTE >" + comment.encode() + b"\n")
                    self._trace.flush()

    def _log_reply(self, reply: t.Any):
        """
        Log a raw reply from the amalgam process.

        Uses a pre-pended '#RESULT >' so it can be filtered by tools like grep.

        Parameters
        ----------
        reply : Any
            The raw reply string to log.
        """
        # See note in _log_comment()
        if self._trace:
            with self._trace_lock:
                if self._trace:
                    if isinstance(reply, ResultWithLog):
                        if reply.json:
                            self._trace.write(b"# RESULT >" + reply.json + b"\n")
                        if reply.log:
                            self._trace.write(b"# LOG >" + reply.log + b"\n")
                    else:
                        self._trace.write(b"# RESULT >" + str(reply).encode() + b"\n")
                    self._trace.flush()

    def _log_time(self, label: str):
        """
        Log a labelled timestamp to the trace file.

        Parameters
        ----------
        label: str
            A string to annotate the timestamped trace entry
        """
        # See note in _log_comment()
        if self._trace:
            with self._trace_lock:
                if self._trace:
                    dt = datetime.now()
                    time_str = (f"{label} {dt:%Y-%m-%d %H:%M:%S},{f'{dt:%f}'[:3]} "
                                f"tid={threading.get_ident()}")
                    self._trace.write(b"# TIME " + time_str.encode() + b"\n")
                    self._trace.flush()

    def _log_execution(self, execution_string: bytes):
        """
        Log an execution string.

        Logs an execution string that is sent to the amalgam process for use in
        command line debugging.

        Parameters
        ----------
        execution_string : bytes
            A formatted string that can be piped into an amalgam command line
            process for use in debugging.

            .. NOTE::
                No formatting checks are performed, it is assumed the execution
                string passed is valid.
        """
        # See note in _log_comment()
        if self._trace:
            with self._trace_lock:
                if self._trace:
                    self._trace.write(execution_string + b"\n")
                    self._trace.flush()

    def _log_execution_std(self, command: bytes, *args: str, suffix: str | bytes | None = None) -> None:
        """
        Log an execution string in a canonical form.

        This looks like ``COMMAND "arg" "arg" suffix``.

        Parameters
        ----------
        command : bytes
            The trace file command string.
        args : str
            Arbitrary parameters to the command, will have double quotes escaped.
        suffix : bytes, optional
            Arbitrary binary data to append to the command string unprocessed.
        """
        # See note in _log_comment()
        if self._trace:
            with self._trace_lock:
                if self._trace:
                    words = [b"\"" + self.escape_double_quotes(arg).encode() + b"\"" for arg in args]
                    words.insert(0, command)
                    if isinstance(suffix, str):
                        words.append(suffix.encode())
                    elif isinstance(suffix, bytes):
                        words.append(suffix)
                    self._trace.write(b" ".join(words) + b"\n")
                    self._trace.flush()

    def gc(self):
        """Force garbage collection when called if self.force_gc is set."""
        if (
            self.gc_interval is not None
            and self.op_count > self.gc_interval
        ):
            _logger.debug("Collecting Garbage")
            gc.collect()
            self.op_count = 0
        self.op_count += 1

    def get_json_from_label(self, handle: str, label: str) -> bytes:
        """
        Get a label from amalgam and returns it in json format.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to retrieve.

        Returns
        -------
        bytes
            The byte-encoded json representation of the amalgam label.
        """
        self._log_execution_std(b"GET_JSON_FROM_LABEL", handle, label)
        result = self.amlg.get_json_from_label(handle, label)
        self._log_reply(result)

        self.gc()

        return result

    def set_json_to_label(
        self,
        handle: str,
        label: str,
        json: str | bytes
    ):
        """
        Set a label in amalgam using json.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to set.
        json : str or bytes
            The json representation of the label value.
        """
        self._log_execution_std(b"SET_JSON_TO_LABEL", handle, label, suffix=json)
        self.amlg.set_json_to_label(handle, label, json)
        self._log_reply(None)

        self.gc()

    def load_entity(
        self,
        handle: str,
        file_path: str,
        *,
        file_type: str = "",
        persist: bool = False,
        json_file_params: str = "",
        write_log: str = "",
        print_log: str = "",
        entity_path: list[str] | None = None,
    ) -> LoadEntityStatus:
        """
        Load an entity from an amalgam source file.

        Parameters
        ----------
        handle : str
            The handle to assign the entity.
        file_path : str
            The path of the file name to load.
        file_type : str, default ""
            If set to a nonempty string, will represent the type of file to load.
        persist : bool, default False
            If set to true, all transactions that update the entity will also be
            written to the files.
        json_file_params : str, default ""
            Either empty string or a string of json specifying a set of key-value pairs
            which are parameters specific to the file type.  See Amalgam documentation
            for details of allowed parameters.
        write_log : str, default ""
            Path to the write log. If empty string, the write log is
            not generated.
        print_log : str, default ""
            Path to the print log. If empty string, the print log is
            not generated.
        entity_path: list[str], optional
            If provided and non-empty, load the content into an entity
            contained within `handle` at this path.

        Returns
        -------
        LoadEntityStatus
            Status of LoadEntity call.
        """
        self.load_command_log_entry = (
            f"LOAD_ENTITY \"{self.escape_double_quotes(handle)}\" "
            f"\"{self.escape_double_quotes(file_path)}\" "
            f"\"{self.escape_double_quotes(file_type)}\" {str(persist).lower()} "
            f"{json_lib.dumps(json_file_params)} "
            f"\"{write_log}\" \"{print_log}\" \"\" \"{' '.join(entity_path or [])}\""
        ).encode()
        self._log_execution(self.load_command_log_entry)
        result = LoadEntityStatus._from_native(self.amlg.load_entity(
            handle, file_path, file_type, persist, json_file_params, write_log, print_log, entity_path))
        self._log_reply(result)

        self.gc()

        return result

    def load_entity_from_memory(
        self,
        handle: str,
        contents: bytes,
        *,
        file_type: str,
        json_file_params: str = "",
        write_log: str = "",
        print_log: str = "",
        entity_path: list[str] | None = None,
    ) -> LoadEntityStatus:
        """
        Load an entity from an in-memory buffer.

        Parameters
        ----------
        handle : str
            The handle to assign the entity.
        contents : bytes
            The content to load.
        file_type : str
            The type of file to store, typically ``"amlg"`` for plain-text Amalgam or ``"caml"``
            for binary compressed Amalgam.
        json_file_params : str, default ""
            Either empty string or a string of json specifying a set of key-value pairs
            which are parameters specific to the file type.  See Amalgam documentation
            for details of allowed parameters.
        write_log : str, default ""
            Path to the write log. If empty string, the write log is
            not generated.
        print_log : str, default ""
            Path to the print log. If empty string, the print log is
            not generated.
        entity_path: list[str], optional
            If provided and non-empty, load the content into an entity
            contained within `handle` at this path.

        Returns
        -------
        LoadEntityStatus
            Status of LoadEntity call.
        """
        self.load_command_log_entry = None
        if self._trace:
            self.load_command_log_entry = (
                f"LOAD_ENTITY_FROM_MEMORY \"{self.escape_double_quotes(handle)}\" "
                f"\"{b64encode(contents).decode()}\" "
                f"\"{self.escape_double_quotes(file_type)}\" false "
                f"{json_lib.dumps(json_file_params)} "
                f"\"{write_log}\" \"{print_log}\" \"\" \"{' '.join(entity_path or [])}\""
            ).encode()
            self._log_execution(self.load_command_log_entry)
        result = LoadEntityStatus._from_native(self.amlg.load_entity_from_memory(
            handle, contents, file_type, json_file_params, write_log, print_log, entity_path))
        self._log_reply(result)

        self.gc()

        return result

    def verify_entity(
        self,
        file_path: str
    ) -> LoadEntityStatus:
        """
        Verify an entity from an amalgam source file.

        Parameters
        ----------
        file_path : str
            The path to the filename.amlg/caml file.

        Returns
        -------
        LoadEntityStatus
            Status of VerifyEntity call.
        """
        self._log_execution_std(b"VERIFY_ENTITY", file_path)
        result = LoadEntityStatus._from_native(self.amlg.verify_entity(file_path))
        self._log_reply(result)

        self.gc()

        return result

    def get_entity_permissions(
        self,
        handle: str
    ) -> bytes:
        """
        Get the entity permissions as a JSON object.

        Parameters
        ----------
        handle : str
            The handle of the entity.

        Returns
        -------
        str
            A JSON object representing the entity permissions.
        """
        self._log_execution_std(b"GET_ENTITY_PERMISSIONS", handle)
        result = self.amlg.get_entity_permissions(handle)
        self._log_reply(result)

        self.gc()

        return result

    def set_entity_permissions(
        self,
        handle: str,
        json_permissions: str | bytes
    ) -> bool:
        """
        Set the entity permissions to the object in json_permissions.

        See Amalgam language documentation for details of valid permissions.

        Parameters
        ----------
        handle : str
            The handle of the entity.
        json_permissions : str or bytes
            A JSON object representing the entity permissions.

        Returns
        -------
        bool
            True if the set was successful, false if not.
        """
        self._log_execution_std(b"SET_ENTITY_PERMISSIONS", handle, suffix=json_permissions)
        result = self.amlg.set_entity_permissions(handle, json_permissions)
        self._log_reply(result)

        self.gc()

        return result

    def clone_entity(
        self,
        handle: str,
        clone_handle: str,
        *,
        file_path: str = "",
        file_type: str = "",
        persist: bool = False,
        json_file_params: str = "",
        write_log: str = "",
        print_log: str = ""
    ) -> bool:
        """
        Clones entity specified by handle into a new entity specified by clone_handle.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity to clone.
        clone_handle : str
            The handle to clone the entity into.
        file_path : str, default ""
            The path of the file name to load.
        file_type : str, default ""
            If set to a nonempty string, will represent the type of file to load.
        persist : bool, default False
            If set to true, all transactions that update the entity will also be
            written to the files.
        json_file_params : str, default ""
            Either empty string or a string of json specifying a set of key-value pairs
            which are parameters specific to the file type.  See Amalgam documentation
            for details of allowed parameters.
        write_log : str, default ""
            Path to the write log. If empty string, the write log is
            not generated.
        print_log : str, default ""
            Path to the print log. If empty string, the print log is
            not generated.

        Returns
        -------
        bool
            True if cloned successfully, False if not.
        """
        self._log_execution_std(b"CLONE_ENTITY", handle, clone_handle, file_path, file_type,
                                suffix=(
                                    f"{str(persist).lower()} "
                                    f"{json_lib.dumps(json_file_params)} "
                                    f"\"{write_log}\" \"{print_log}\""
                                )
                                )
        result = self.amlg.clone_entity(
            handle, clone_handle, file_path, file_type, persist, json_file_params, write_log, print_log)
        self._log_reply(result)

        self.gc()

        return result

    def store_entity(
        self,
        handle: str,
        file_path: str,
        *,
        file_type: str = "",
        persist: bool = False,
        json_file_params: str = "",
        entity_path: list[str] | None = None,
    ) -> bool:
        """
        Store entity to the file type specified within file_path.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        file_path : str
            The path of the file name to load.
        file_type : str, default ""
            If set to a nonempty string, will represent the type of file to load.
        persist : bool, default False
            If set to true, all transactions that update the entity will also be
            written to the files.
        json_file_params : str, default ""
            Either empty string or a string of json specifying a set of key-value pairs
            which are parameters specific to the file type.  See Amalgam documentation
            for details of allowed parameters.
        entity_path: list[str], optional
            If provided and non-empty, store the content from an entity
            contained within `handle` at this path.

        Returns
        -------
        bool
            True if the entity file was saved successfully, False otherwise.
        """
        self._log_execution_std(b"STORE_ENTITY", handle, file_path, file_type,
                                suffix=(f"{str(persist).lower()} {json_lib.dumps(json_file_params)} "
                                        f"\"{' '.join(entity_path or [])}\""))
        result = self.amlg.store_entity(handle, file_path, file_type, persist, json_file_params, entity_path)
        self._log_reply(result)

        self.gc()
        return result

    def store_entity_to_memory(
        self,
        handle: str,
        *,
        file_type: str,
        json_file_params: str = "",
        entity_path: list[str] | None = None,
    ) -> bytes | None:
        """
        Store entity to memory as a bytes object.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        file_type : str
            The type of file to store, typically ``"amlg"`` for plain-text Amalgam or ``"caml"``
            for binary compressed Amalgam.
        json_file_params : str, default ""
            Either empty string or a string of json specifying a set of key-value pairs
            which are parameters specific to the file type.  See Amalgam documentation
            for details of allowed parameters.
        entity_path: list[str], optional
            If provided and non-empty, store the content from an entity
            contained within `handle` at this path.

        Returns
        -------
        bytes | None
            The serialized entity contents. They are empty when no entity has the
            handle ``handle``, and None if the engine returns no buffer.
        """
        self._log_execution_std(b"STORE_ENTITY_TO_MEMORY", handle, file_type,
                                suffix=f"false {json_lib.dumps(json_file_params)} \"{' '.join(entity_path or [])}\"")
        result = self.amlg.store_entity_to_memory(handle, file_type, json_file_params, entity_path)
        if self._trace:
            self._log_reply(b64encode(result).decode() if result is not None else None)

        self.gc()
        return result

    def destroy_entity(
        self,
        handle: str
    ):
        """
        Destroys an entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        """
        self._log_execution_std(b"DESTROY_ENTITY", handle)
        self.amlg.destroy_entity(handle)
        self._log_reply(None)

        self.gc()

    def set_random_seed(
        self,
        handle: str,
        rand_seed: str
    ) -> bool:
        """
        Set entity's random seed.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        rand_seed : str
            A string representing the random seed to set.

        Returns
        -------
        bool
            True if the set was successful, false if not.
        """
        self._log_execution_std(b"SET_RANDOM_SEED", handle, rand_seed)
        result = self.amlg.set_random_seed(handle, rand_seed)
        self._log_reply(None)

        self.gc()
        return result

    def get_entities(self) -> list[str]:
        """
        Get loaded top level entities.

        Returns
        -------
        list of str
            The list of entity handles.
        """
        result = self.amlg.get_entities()
        self.gc()

        return result

    def execute_entity_json(
        self,
        handle: str,
        label: str,
        json: str | bytes
    ) -> bytes:
        """
        Execute a label with parameters provided in json format.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to execute.
        json : str or bytes
            A json representation of parameters for the label to be executed.

        Returns
        -------
        bytes
            A byte-encoded json representation of the response.
        """
        self._log_time("EXECUTION START")
        self._log_execution_std(b"EXECUTE_ENTITY_JSON", handle, label, suffix=json)
        result = self.amlg.execute_entity_json(handle, label, json)
        self._log_time("EXECUTION STOP")
        self._log_reply(result)

        return result

    def execute_entity_json_logged(
        self,
        handle: str,
        label: str,
        json: str | bytes
    ) -> ResultWithLog:
        """
        Execute a label, and also return a transaction log.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.

        label : str
            The label to execute.
        json : str or bytes
            A json representation of parameters for the label to be executed.

        Returns
        -------
        ResultWithLog
            Both a JSON-encoded response and the Amalgam-format transaction log entry.

        """
        self._log_time("EXECUTION START")
        self._log_execution_std(b"EXECUTE_ENTITY_JSON_LOGGED", handle, label, suffix=json)
        result_json, result_log = self.amlg.execute_entity_json_logged(handle, label, json)
        result = ResultWithLog(json=result_json, log=result_log)
        self._log_time("EXECUTION STOP")
        self._log_reply(result)

        return result

    def eval_on_entity(
        self,
        handle: str,
        amlg: str | bytes
    ) -> bytes:
        """
        Execute arbitrary Amalgam code against an entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        amlg : str | bytes
            The code to execute.

        Returns
        -------
        bytes
            A byte-encoded json representation of the response.

        """
        self._log_time("EXECUTION START")
        self._log_execution_std(b"EVAL_ON_ENTITY", handle, str(amlg))
        result = self.amlg.eval_on_entity(handle, amlg)
        self._log_time("EXECUTION STOP")
        self._log_reply(result)

        return result

    def get_version_string(self) -> bytes:
        """
        Get the version string of the amalgam dynamic library.

        Returns
        -------
        bytes
            A version byte-encoded string with semver.
        """
        amlg_version = self.amlg.get_version_string()
        self._log_comment(f"call to amlg.GetVersionString() - returned: "
                          f"{amlg_version}\n")
        return amlg_version

    def get_concurrency_type_string(self) -> bytes:
        """
        Get the concurrency type string of the amalgam dynamic library.

        Returns
        -------
        bytes
            A byte-encoded string with library concurrency type.
            Ex. b'MultiThreaded'
        """
        amlg_concurrency_type = self.amlg.get_concurrency_type_string()
        self._log_comment(
            f"call to amlg.GetConcurrencyTypeString() - returned: "
            f"{amlg_concurrency_type}\n")
        return amlg_concurrency_type

    @staticmethod
    def escape_double_quotes(s: str) -> str:
        """
        Get the string with backslashes preceding contained double quotes.

        Parameters
        ----------
        s : str
            The input string.

        Returns
        -------
        str
            The modified version of s with escaped double quotes.
        """
        return s.replace('"', '\\"')
