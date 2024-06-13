from __future__ import annotations

from ctypes import (
    _Pointer, Array, byref, c_bool, c_char, c_char_p, c_double, c_size_t, c_uint64, c_void_p,
    cast, cdll, POINTER, Structure
)
from datetime import datetime
import gc
import logging
from pathlib import Path
import platform
import re
import typing as t
import warnings

# Set to amalgam
_logger = logging.getLogger('amalgam')


class _LoadEntityStatus(Structure):
    """
    A private status returned from Amalgam binary LoadEntity C API.

    This is implemented with ctypes for accessing binary Amalgam builds.
    """

    _fields_ = [
        ("loaded", c_bool),
        ("message", POINTER(c_char)),
        ("version", POINTER(c_char))
    ]


class LoadEntityStatus:
    """
    Status returned by :func:`~api.Amalgam.load_entity`.

    This is implemented with python types and is meant to wrap _LoadEntityStatus
    which uses ctypes and directly interacts with the Amalgam binaries.

    Parameters
    ----------
    api : Amalgam
        The Python Amalgam interface.
    c_status : _LoadEntityStatus, optional
        _LoadEntityStatus instance.
    """

    def __init__(self, api: Amalgam, c_status: t.Optional[_LoadEntityStatus] = None):
        """Initialize LoadEntityStatus."""
        if c_status is None:
            self.loaded = True
            self.message = ""
            self.version = ""
        else:
            self.loaded = bool(c_status.loaded)
            self.message = api.char_p_to_bytes(c_status.message).decode("utf-8")
            self.version = api.char_p_to_bytes(c_status.version).decode("utf-8")

    def __str__(self) -> str:
        """
        Return a human-readable string representation.

        Returns
        -------
        str
            The human-readable string representation.
        """
        return f"{self.loaded},\"{self.message}\",\"{self.version}\""


class Amalgam:
    """
    A general python direct interface to the Amalgam library.

    This is implemented with ctypes for accessing binary Amalgam builds.

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

            self.trace = open(self.execution_trace_filepath, 'w+',
                              encoding='utf-8')
            _logger.debug("Opening Amalgam trace file: "
                          f"{self.execution_trace_filepath}")
        else:
            self.trace = None

        _logger.debug(f"Loading amalgam library: {self.library_path}")
        _logger.debug(f"SBF_DATASTORE enabled: {sbf_datastore_enabled}")
        self.amlg = cdll.LoadLibrary(str(self.library_path))
        if sbf_datastore_enabled is not None:
            self.set_amlg_flags(sbf_datastore_enabled)
        if max_num_threads is not None:
            self.set_max_num_threads(max_num_threads)
        self.gc_interval = gc_interval
        self.op_count = 0
        self.load_command_log_entry = None

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
        self.amlg.IsSBFDataStoreEnabled.restype = c_bool
        return self.amlg.IsSBFDataStoreEnabled()

    def set_amlg_flags(self, sbf_datastore_enabled: bool = True):
        """
        Set various amalgam flags for data structure and compute features.

        Parameters
        ----------
        sbf_datastore_enabled : bool, default True
            If true, sbf tree structures are enabled.
        """
        self.amlg.SetSBFDataStoreEnabled.argtypes = [c_bool]
        self.amlg.SetSBFDataStoreEnabled.restype = c_void_p
        self.amlg.SetSBFDataStoreEnabled(sbf_datastore_enabled)

    def get_max_num_threads(self) -> int:
        """
        Get the maximum number of threads currently set.

        Returns
        -------
        int
            The maximum number of threads that Amalgam is configured to use.
        """
        self.amlg.GetMaxNumThreads.restype = c_size_t
        self._log_execution("GET_MAX_NUM_THREADS")
        result = self.amlg.GetMaxNumThreads()
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
        """
        self.amlg.SetMaxNumThreads.argtypes = [c_size_t]
        self.amlg.SetMaxNumThreads.restype = c_void_p

        self._log_execution(f"SET_MAX_NUM_THREADS {max_num_threads}")
        result = self.amlg.SetMaxNumThreads(max_num_threads)
        self._log_reply(result)

    def reset_trace(self, file: str):
        """
        Close the open trace file and opens a new one with the specified name.

        Parameters
        ----------
        file : str
            The file name for the new execution trace.
        """
        if self.trace is None:
            # Trace was not enabled
            return
        _logger.debug(f"Execution trace file being reset: "
                      f"{self.execution_trace_filepath} to be closed ...")
        # Write exit command.
        self.trace.write("EXIT\n")
        self.trace.close()
        self.execution_trace_filepath = Path(self.execution_trace_dir, file)

        # increment a counter on the file name, if file already exists..
        if not self.append_trace_file:
            counter = 1
            while self.execution_trace_filepath.exists():
                self.execution_trace_filepath = Path(
                    self.execution_trace_dir, f'{file}.{counter}')
                counter += 1

        self.trace = open(self.execution_trace_filepath, 'w+')
        _logger.debug(f"New trace file: {self.execution_trace_filepath} "
                      f"opened.")
        # Write load command used to instantiate the amalgam instance.
        if self.load_command_log_entry is not None:
            self.trace.write(self.load_command_log_entry + "\n")
        self.trace.flush()

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return (f"Amalgam Path:\t\t {self.library_path}\n"
                f"Amalgam GC Interval:\t {self.gc_interval}\n")

    def __del__(self):
        """Implement a "destructor" method to finalize log files, if any."""
        if (
            getattr(self, 'debug', False) and
            getattr(self, 'trace', None) is not None
        ):
            try:
                self.trace.write("EXIT\n")
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
        if self.trace:
            self.trace.write("# NOTE >" + str(comment) + "\n")
            self.trace.flush()

    def _log_reply(self, reply: t.Any):
        """
        Log a raw reply from the amalgam process.

        Uses a pre-pended '#RESULT >' so it can be filtered by tools like grep.

        Parameters
        ----------
        reply : Any
            The raw reply string to log.
        """
        if self.trace:
            self.trace.write("# RESULT >" + str(reply) + "\n")
            self.trace.flush()

    def _log_time(self, label: str):
        """
        Log a labelled timestamp to the trace file.

        Parameters
        ----------
        label: str
            A string to annotate the timestamped trace entry
        """
        if self.trace:
            dt = datetime.now()
            self.trace.write(f"# TIME {label} {dt:%Y-%m-%d %H:%M:%S},"
                             f"{f'{dt:%f}'[:3]}\n")
            self.trace.flush()

    def _log_execution(self, execution_string: str):
        """
        Log an execution string.

        Logs an execution string that is sent to the amalgam process for use in
        command line debugging.

        Parameters
        ----------
        execution_string : str
            A formatted string that can be piped into an amalgam command line
            process for use in debugging.

            .. NOTE::
                No formatting checks are performed, it is assumed the execution
                string passed is valid.
        """
        if self.trace:
            self.trace.write(execution_string + "\n")
            self.trace.flush()

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

    def str_to_char_p(
        self,
        value: str | bytes,
        size: t.Optional[int] = None
    ) -> Array[c_char]:
        """
        Convert a string to an Array of C char.

        User must call `del` on returned buffer

        Parameters
        ----------
        value : str or bytes
            The value of the string.
        size : int, optional
            The size of the string. If not provided, the length of
            the string is used.

        Returns
        -------
        Array of c_char
            An Array of C char datatypes which form the given string
        """
        if isinstance(value, str):
            value = value.encode('utf-8')
        buftype = c_char * (size if size is not None else (len(value) + 1))
        buf = buftype()
        buf.value = value
        return buf

    def char_p_to_bytes(self, p: _Pointer[c_char] | c_char_p) -> bytes | None:
        """
        Copy native C char pointer to bytes, cleaning up memory correctly.

        Parameters
        ----------
        p : c_char_p
            The char pointer to convert

        Returns
        -------
        bytes or None
            The byte-encoded char
        """
        bytes_str = cast(p, c_char_p).value

        self.amlg.DeleteString.argtypes = [c_char_p]
        self.amlg.DeleteString.restype = None
        self.amlg.DeleteString(p)

        return bytes_str

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
        self.amlg.GetJSONPtrFromLabel.restype = POINTER(c_char)
        self.amlg.GetJSONPtrFromLabel.argtypes = [c_char_p, c_char_p]
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)

        self._log_execution((
            f"GET_JSON_FROM_LABEL \"{self.escape_double_quotes(handle)}\" "
            f"\"{self.escape_double_quotes(label)}\""
        ))
        result = self.char_p_to_bytes(self.amlg.GetJSONPtrFromLabel(handle_buf, label_buf))
        self._log_reply(result)

        del handle_buf
        del label_buf
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
        self.amlg.SetJSONToLabel.restype = c_void_p
        self.amlg.SetJSONToLabel.argtypes = [c_char_p, c_char_p, c_char_p]
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        json_buf = self.str_to_char_p(json)

        self._log_execution((
            f"SET_JSON_TO_LABEL \"{self.escape_double_quotes(handle)}\" "
            f"\"{self.escape_double_quotes(label)}\" "
            f"{json}"
        ))
        self.amlg.SetJSONToLabel(handle_buf, label_buf, json_buf)
        self._log_reply(None)

        del handle_buf
        del label_buf
        del json_buf
        self.gc()

    def load_entity(
        self,
        handle: str,
        amlg_path: str,
        *,
        persist: bool = False,
        load_contained: bool = False,
        escape_filename: bool = False,
        escape_contained_filenames: bool = True,
        write_log: str = "",
        print_log: str = ""
    ) -> LoadEntityStatus:
        """
        Load an entity from an amalgam source file.

        Parameters
        ----------
        handle : str
            The handle to assign the entity.
        amlg_path : str
            The path to the filename.amlg/caml file.
        persist : bool, default False
            If set to true, all transactions will trigger the entity to be
            saved over the original source.
        load_contained : bool, default False
            If set to true, contained entities will be loaded.
        escape_filename : bool, default False
            If set to true, the filename will be aggressively escaped.
        escape_contained_filenames : bool, default True
            If set to true, the filenames of contained entities will be
            aggressively escaped.
        write_log : str, default ""
            Path to the write log. If empty string, the write log is
            not generated.
        print_log : str, default ""
            Path to the print log. If empty string, the print log is
            not generated.

        Returns
        -------
        LoadEntityStatus
            Status of LoadEntity call.
        """
        self.amlg.LoadEntity.argtypes = [
            c_char_p, c_char_p, c_bool, c_bool, c_bool, c_bool, c_char_p, c_char_p]
        self.amlg.LoadEntity.restype = _LoadEntityStatus
        handle_buf = self.str_to_char_p(handle)
        amlg_path_buf = self.str_to_char_p(amlg_path)
        write_log_buf = self.str_to_char_p(write_log)
        print_log_buf = self.str_to_char_p(print_log)

        load_command_log_entry = (
            f"LOAD_ENTITY \"{self.escape_double_quotes(handle)}\" "
            f"\"{self.escape_double_quotes(amlg_path)}\" {str(persist).lower()} "
            f"{str(load_contained).lower()} {str(escape_filename).lower()} "
            f"{str(escape_contained_filenames).lower()} \"{write_log}\" "
            f"\"{print_log}\""
        )
        self._log_execution(load_command_log_entry)
        result = LoadEntityStatus(self, self.amlg.LoadEntity(
            handle_buf, amlg_path_buf, persist, load_contained,
            escape_filename, escape_contained_filenames,
            write_log_buf, print_log_buf))
        self._log_reply(result)

        del handle_buf
        del amlg_path_buf
        del write_log_buf
        del print_log_buf
        self.gc()

        return result

    def verify_entity(
        self,
        amlg_path: str
    ) -> LoadEntityStatus:
        """
        Verify an entity from an amalgam source file.

        Parameters
        ----------
        amlg_path : str
            The path to the filename.amlg/caml file.

        Returns
        -------
        LoadEntityStatus
            Status of VerifyEntity call.
        """
        self.amlg.VerifyEntity.argtypes = [c_char_p]
        self.amlg.VerifyEntity.restype = _LoadEntityStatus
        amlg_path_buf = self.str_to_char_p(amlg_path)

        self._log_execution(f"VERIFY_ENTITY \"{self.escape_double_quotes(amlg_path)}\"")
        result = LoadEntityStatus(self, self.amlg.VerifyEntity(amlg_path_buf))
        self._log_reply(result)

        del amlg_path_buf
        self.gc()

        return result

    def clone_entity(
        self,
        handle: str,
        clone_handle: str,
        *,
        amlg_path: str = "",
        persist: bool = False,
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
        amlg_path : str, default ""
            The path to store the filename.amlg/caml file.  Only relevant if persist is True.
        persist : bool, default False
            If set to true, all transactions will trigger the entity to be
            saved over the original source.
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
        self.amlg.CloneEntity.argtypes = [
            c_char_p, c_char_p, c_char_p, c_bool, c_char_p, c_char_p]
        handle_buf = self.str_to_char_p(handle)
        clone_handle_buf = self.str_to_char_p(clone_handle)
        amlg_path_buf = self.str_to_char_p(amlg_path)
        write_log_buf = self.str_to_char_p(write_log)
        print_log_buf = self.str_to_char_p(print_log)

        clone_command_log_entry = (
            f'CLONE_ENTITY "{self.escape_double_quotes(handle)}" '
            f'"{self.escape_double_quotes(clone_handle)}" '
            f'"{self.escape_double_quotes(amlg_path)}" {str(persist).lower()} '
            f'"{write_log}" "{print_log}"'
        )
        self._log_execution(clone_command_log_entry)
        result = self.amlg.CloneEntity(
            handle_buf, clone_handle_buf, amlg_path_buf, persist,
            write_log_buf, print_log_buf)
        self._log_reply(result)

        del handle_buf
        del clone_handle_buf
        del amlg_path_buf
        del write_log_buf
        del print_log_buf
        self.gc()

        return result

    def store_entity(
        self,
        handle: str,
        amlg_path: str,
        *,
        update_persistence_location: bool = False,
        store_contained: bool = False
    ):
        """
        Store entity to the file type specified within amlg_path.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        amlg_path : str
            The path to the filename.amlg/caml file.
        update_persistence_location : bool
            If set to true, updates location entity is persisted to.
        store_contained : bool
            If set to true, contained entities will be stored.
        """
        self.amlg.StoreEntity.argtypes = [
            c_char_p, c_char_p, c_bool, c_bool]
        handle_buf = self.str_to_char_p(handle)
        amlg_path_buf = self.str_to_char_p(amlg_path)

        store_command_log_entry = (
            f"STORE_ENTITY \"{self.escape_double_quotes(handle)}\" "
            f"\"{self.escape_double_quotes(amlg_path)}\" "
            f"{str(update_persistence_location).lower()} "
            f"{str(store_contained).lower()}"
        )
        self._log_execution(store_command_log_entry)
        self.amlg.StoreEntity(
            handle_buf, amlg_path_buf, update_persistence_location, store_contained)
        self._log_reply(None)

        del handle_buf
        del amlg_path_buf
        self.gc()

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
        self.amlg.DestroyEntity.argtypes = [c_char_p]
        handle_buf = self.str_to_char_p(handle)

        self._log_execution(f"DESTROY_ENTITY \"{self.escape_double_quotes(handle)}\"")
        self.amlg.DestroyEntity(handle_buf)
        self._log_reply(None)

        del handle_buf
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
        self.amlg.SetRandomSeed.argtypes = [c_char_p, c_char_p]
        self.amlg.SetRandomSeed.restype = c_bool

        handle_buf = self.str_to_char_p(handle)
        rand_seed_buf = self.str_to_char_p(rand_seed)

        self._log_execution(f'SET_RANDOM_SEED "{self.escape_double_quotes(handle)}"'
                            f'"{self.escape_double_quotes(rand_seed)}"')
        result = self.amlg.SetRandomSeed(handle_buf, rand_seed)
        self._log_reply(None)

        del handle_buf
        del rand_seed_buf
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
        self.amlg.GetEntities.argtypes = [POINTER(c_uint64)]
        self.amlg.GetEntities.restype = POINTER(c_char_p)
        num_entities = c_uint64()
        entities = self.amlg.GetEntities(byref(num_entities))
        result = [entities[i].decode() for i in range(num_entities.value)]

        del entities
        del num_entities
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
        self.amlg.ExecuteEntityJsonPtr.restype = POINTER(c_char)
        self.amlg.ExecuteEntityJsonPtr.argtypes = [
            c_char_p, c_char_p, c_char_p]
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        json_buf = self.str_to_char_p(json)

        self._log_time("EXECUTION START")
        self._log_execution((
            "EXECUTE_ENTITY_JSON "
            f"\"{self.escape_double_quotes(handle)}\" "
            f"\"{self.escape_double_quotes(label)}\" "
            f"{json}"
        ))
        result = self.char_p_to_bytes(self.amlg.ExecuteEntityJsonPtr(
            handle_buf, label_buf, json_buf))
        self._log_time("EXECUTION STOP")
        self._log_reply(result)

        del handle_buf
        del label_buf
        del json_buf

        return result

    def get_version_string(self) -> bytes:
        """
        Get the version string of the amalgam dynamic library.

        Returns
        -------
        bytes
            A version byte-encoded string with semver.
        """
        self.amlg.GetVersionString.restype = POINTER(c_char)
        amlg_version = self.char_p_to_bytes(self.amlg.GetVersionString())
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
        self.amlg.GetConcurrencyTypeString.restype = POINTER(c_char)
        amlg_concurrency_type = self.char_p_to_bytes(self.amlg.GetConcurrencyTypeString())
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
