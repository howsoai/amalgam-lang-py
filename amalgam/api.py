from ctypes import (
    byref, c_bool, c_char, c_char_p, c_double, c_size_t, c_uint64, c_void_p,
    cast, cdll, POINTER, Structure
)
from datetime import datetime
import logging
from pathlib import Path
import platform
import re
from typing import Any, List, Optional, Tuple, Union
import warnings

from .scope_manager import CAPIScopeManager


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
    """

    def __init__(self, api, c_status: _LoadEntityStatus = None):
        if c_status is None:
            self.loaded = True
            self.message = ""
            self.version = ""
        else:
            self.loaded = bool(c_status.loaded)
            self.message = api.char_p_to_bytes(c_status.message).decode("utf-8")
            self.version = api.char_p_to_bytes(c_status.version).decode("utf-8")

    def __str__(self):
        """Emit a string representation."""
        return f'{self.loaded},"{self.message}","{self.version}"'


class Amalgam:
    """
    A general python direct interface to the Amalgam library.

    This is implemented with ctypes for accessing binary Amalgam builds.

    Parameters
    ----------
    library_path : Path or str
        Path to either the amalgam DLL, DyLib or SO (Windows, MacOS or
        Linux, respectively). If not specified it will build a path to the
        appropriate library bundled with the package.

    append_trace_file : bool, default False
        If True, new content will be appended to a trace file if the file
        already exists rather than creating a new file.

    execution_trace_dir : Union[str, None], default None
        A directory path for writing trace files.

    execution_trace_file : str, default "execution.trace"
        The full or relative path to the execution trace used in debugging.

    gc_interval : int, default None
        If set, garbage collection will be forced at the specified interval
        of amalgam operations. Note that this reduces memory consumption at
        the compromise of performance. Only use if models are exceeding
        your host's process memory limit or if paging to disk. As an
        example, if this operation is set to 0 (force garbage collection
        every operation), it results in a performance impact of 150x.
        Default value does not force garbage collection.

    library_postfix : str, optional
        For configuring use of different amalgam builds i.e. -st for
        single-threaded. If not provided, an attempt will be made to detect
        it within library_path. If neither are available, -mt (multi-threaded)
        will be used.

    max_num_threads : int, default 0
        If a multithreaded Amalgam binary is used, sets the maximum number
        of threads to the value specified. If 0, will use the number of
        visible logical cores.

    sbf_datastore_enabled : bool, default False
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
        library_path: Optional[Union[Path, str]] = None,
        *,
        arch: Optional[str] = None,
        append_trace_file: bool = False,
        execution_trace_dir: Optional[str] = None,
        execution_trace_file: str = "execution.trace",
        gc_interval: Optional[int] = None,
        library_postfix: Optional[str] = None,
        max_num_threads: int = 0,
        sbf_datastore_enabled: bool = True,
        trace: Optional[bool] = None,
        **kwargs
    ):
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
        self.set_amlg_flags(sbf_datastore_enabled)
        self.set_max_num_threads(max_num_threads)
        self.load_command_log_entry = None
        self.scope_manager = CAPIScopeManager(gc_interval=gc_interval)

    @classmethod
    def _get_allowed_postfixes(cls, library_dir: Path) -> List[str]:
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
    def _parse_postfix(cls, filename: str) -> Union[str, None]:
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
        matches = re.findall(r'-(.+?)\.', filename)
        if len(matches) > 0:
            return f'-{matches[-1]}'
        else:
            return None

    @classmethod
    def _get_library_path(
        cls,
        library_path: Optional[Union[Path, str]] = None,
        library_postfix: Optional[str] = None,
        arch: Optional[str] = None
    ) -> Tuple[Path, str]:
        """
        Return the full Amalgam library path and its library_postfix.

        Using the potentially empty parameters passed into the initializer,
        determine and return the prescribed or the correct default path and
        library postfix for the running environment.

        Parameters
        ----------
        library_path : Path or str, default None
            Optional, The path to the Amalgam shared library.
        library_postfix : str, default "-mt"
            Optional, The library type as specified by a postfix to the word
            "amalgam" in the library's filename. E.g., the "-mt" in
            `amalgam-mt.dll`.
        arch : str, default None
            Optional, the platform architecture of the embedded Amalgam
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

    def set_amlg_flags(self, sbf_datastore_enabled: bool = True) -> None:
        """
        Set various amalgam flags for data structure and compute features.

        Parameters
        ----------
        sbf_datastore_enabled : bool, default True
            If true, sbf tree structures are enabled.
        """
        self.amlg.SetSBFDataStoreEnabled.argtype = [c_bool]
        self.amlg.SetSBFDataStoreEnabled.restype = c_void_p
        self.amlg.SetSBFDataStoreEnabled(sbf_datastore_enabled)

    def set_max_num_threads(self, max_num_threads: int = 0) -> None:
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
        self.amlg.SetMaxNumThreads.argtype = [c_size_t]
        self.amlg.SetMaxNumThreads.restype = c_void_p
        self.amlg.SetMaxNumThreads(max_num_threads)

    def reset_trace(self, file: str) -> None:
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
        """Implement the str() method."""
        return (f"Amalgam Path:\t\t {self.library_path}\n"
                f"Amalgam GC Interval:\t {self.gc_interval}\n")

    def __del__(self) -> None:
        """Implement a "destructor" method to finalize log files, if any."""
        if (
            getattr(self, 'debug', False) and
            getattr(self, 'trace', None) is not None
        ):
            try:
                self.trace.write("EXIT\n")
            except Exception:  # noqa - deliberately broad
                pass

    def _log_comment(self, comment: str) -> None:
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

    def _log_reply(self, reply: Any) -> None:
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

    def _log_time(self, label: str) -> None:
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

    def _log_execution(self, execution_string: str) -> None:
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

    def str_to_char_p(
        self,
        value: Union[str, bytes],
        size: Optional[int] = None
    ) -> c_char:
        """
        Convert a string to a C char pointer.

        User must call `del` on returned buffer

        Parameters
        ----------
        value : str or bytes
            The value of the string.
        size : int or None
            The size of the string. If not provided, the length of the
            string is used.

        Returns
        -------
        c_char
            A C char pointer for the string.
        """
        if isinstance(value, str):
            value = value.encode('utf-8')
        buftype = c_char * (size if size is not None else (len(value) + 1))
        buf = buftype()
        buf.value = value
        return buf

    def char_p_to_bytes(self, p: POINTER(c_char)) -> bytes:
        """
        Copy a native C char pointer to bytes, cleaning up native memory correctly.

        Parameters
        ----------
        p : LP_char_p
            C pointer to string to convert

        Returns
        -------
        bytes
            The byte-encoded string from C pointer
        """
        bytes = cast(p, c_char_p).value

        self.amlg.DeleteString.argtypes = c_char_p,
        self.amlg.DeleteString.restype = None
        self.amlg.DeleteString(p)

        return bytes

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
        self.amlg.GetJSONPtrFromLabel.argtype = [c_char_p, c_char_p]

        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)

            self._log_execution((
                f'GET_JSON_FROM_LABEL "{self.escape_double_quotes(handle)}" '
                f'"{self.escape_double_quotes(label)}"'
            ))
            result = self.char_p_to_bytes(self.amlg.GetJSONPtrFromLabel(scope.handle_buf, scope.label_buf))
            self._log_reply(result)

        return result

    def set_json_to_label(
        self,
        handle: str,
        label: str,
        json: Union[str, bytes]
    ) -> None:
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
        self.amlg.SetJSONToLabel.argtype = [c_char_p, c_char_p, c_char_p]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)
            scope.json_buf = self.str_to_char_p(json)

            self._log_execution((
                f'SET_JSON_TO_LABEL "{self.escape_double_quotes(handle)}" '
                f'"{self.escape_double_quotes(label)}" {json}'))
            self.amlg.SetJSONToLabel(
                scope.handle_buf, scope.label_buf, scope.json_buf)
            self._log_reply(None)

    def load_entity(
        self,
        handle: str,
        amlg_path: str,
        persist: bool = False,
        load_contained: bool = False,
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
        persist : bool
            If set to true, all transactions will trigger the entity to be
            saved over the original source.
        load_contained : bool
            If set to true, contained entities will be loaded.
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
        self.amlg.LoadEntity.argtype = [
            c_char_p, c_char_p, c_bool, c_bool, c_char_p, c_char_p]
        self.amlg.LoadEntity.restype = _LoadEntityStatus
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.amlg_path_buf = self.str_to_char_p(amlg_path)
            scope.write_log_buf = self.str_to_char_p(write_log)
            scope.print_log_buf = self.str_to_char_p(print_log)

            load_command_log_entry = (
                f'LOAD_ENTITY "{self.escape_double_quotes(handle)}" '
                f'"{self.escape_double_quotes(amlg_path)}" '
                f'{str(persist).lower()} {str(load_contained).lower()} '
                f'"{write_log}" "{print_log}"'
            )
            self._log_execution(load_command_log_entry)
            result = LoadEntityStatus(self, self.amlg.LoadEntity(
                scope.handle_buf, scope.amlg_path_buf, persist, load_contained,
                scope.write_log_buf, scope.print_log_buf))
            self._log_reply(result)

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
        self.amlg.VerifyEntity.argtype = [c_char_p]
        self.amlg.VerifyEntity.restype = _LoadEntityStatus
        with self.scope_manager.capi_scope() as scope:
            scope.amlg_path_buf = self.str_to_char_p(amlg_path)

            self._log_execution(f'VERIFY_ENTITY "{self.escape_double_quotes(amlg_path)}"')
            result = LoadEntityStatus(self, self.amlg.VerifyEntity(scope.amlg_path_buf))
            self._log_reply(result)

        return result

    def store_entity(
        self,
        handle: str,
        amlg_path: str,
        update_persistence_location: bool = False,
        store_contained: bool = False
    ) -> None:
        """
        Store an entity to the file type specified within amlg_path.

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
        self.amlg.StoreEntity.argtype = [
            c_char_p, c_char_p, c_bool, c_bool]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.amlg_path_buf = self.str_to_char_p(amlg_path)

            store_command_log_entry = (
                f'STORE_ENTITY "{self.escape_double_quotes(handle)}" '
                f'"{self.escape_double_quotes(amlg_path)}" '
                f'{str(update_persistence_location).lower()} '
                f'{str(store_contained).lower()}'
            )
            self._log_execution(store_command_log_entry)
            self.amlg.StoreEntity(
                scope.handle_buf, scope.amlg_path_buf,
                update_persistence_location, store_contained)
            self._log_reply(None)

    def destroy_entity(
        self,
        handle: str
    ) -> None:
        """
        Destroys an entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        """
        self.amlg.DestroyEntity.argtype = [c_char_p]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)

            self._log_execution(
                f'DESTROY_ENTITY "{self.escape_double_quotes(handle)}"')
            self.amlg.DestroyEntity(scope.handle_buf)
            self._log_reply(None)

    def get_entities(self) -> List[str]:
        """
        Get loaded top level entities.

        Returns
        -------
        list of str
            The list of entity handles.
        """
        self.amlg.GetEntities.argtype = [POINTER(c_uint64)]
        self.amlg.GetEntities.restype = POINTER(c_char_p)
        with self.scope_manager.capi_scope() as scope:
            scope.num_entities = c_uint64()
            scope.entities = self.amlg.GetEntities(byref(scope.num_entities))
            result = [
                scope.entities[i].decode()
                for i in range(scope.num_entities.value)
            ]

        return result

    def execute_entity_json(
        self,
        handle: str,
        label: str,
        json: Union[str, bytes]
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
        self.amlg.ExecuteEntityJsonPtr.argtype = [
            c_char_p, c_char_p, c_char_p]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)
            scope.json_buf = self.str_to_char_p(json)

            self._log_time("EXECUTION START")
            self._log_execution((
                'EXECUTE_ENTITY_JSON '
                f'"{self.escape_double_quotes(handle)}" '
                f'"{self.escape_double_quotes(label)}" '
                f'{json}'
            ))
            result = self.char_p_to_bytes(self.amlg.ExecuteEntityJsonPtr(
                scope.handle_buf, scope.label_buf, scope.json_buf))
            self._log_time("EXECUTION STOP")
            self._log_reply(result)

        return result

    def set_number_value(self, handle: str, label: str, value: float) -> None:
        """
        Set a numeric value to a label in an amalgam entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to set.
        value : float
            A numeric value to assign to a label.
        """
        self.amlg.SetNumberValue.restype = c_void_p
        self.amlg.SetNumberValue.argtype = [c_char_p, c_char_p, c_double]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)
            scope.val = c_double(value)

            self.amlg.SetNumberValue(
                scope.handle_buf, scope.label_buf, scope.val)

    def get_number_value(self, handle: str, label: str) -> float:
        """
        Retrieve the numeric value of a label in an amalgam entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to execute.

        Returns
        -------
        float
            The numeric value of the label.
        """
        self.amlg.GetNumberValue.restype = c_double
        self.amlg.GetNumberValue.argtype = [c_char_p, c_char_p]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)

            result = self.amlg.GetNumberValue(
                scope.handle_buf, scope.label_buf)

        return result

    def set_string_value(
        self,
        handle: str,
        label: str,
        value: Union[str, bytes]
    ) -> None:
        """
        Set a string value to a label in an amalgam entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to set.
        value : str or bytes
            A string value.
        """
        self.amlg.SetStringValue.restype = c_void_p
        self.amlg.SetStringValue.argtype = [c_char_p, c_char_p, c_char_p]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)
            scope.val_buf = self.str_to_char_p(value)

            self.amlg.SetStringValue(
                scope.handle_buf, scope.label_buf, scope.val_buf)

    def get_string_value(self, handle: str, label: str) -> Union[bytes, None]:
        """
        Retrieve a string value from a label in an amalgam entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to retrieve.

        Returns
        -------
        bytes or None
            The byte-encoded string value of the label in the amalgam entity.
        """
        self.amlg.GetStringListPtr.restype = POINTER(c_char_p)
        self.amlg.GetStringListPtr.argtype = [c_char_p, c_char_p]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)

            size = self.amlg.GetStringListLength(scope.handle_buf, scope.label_buf)
            scope.value_buf = self.amlg.GetStringListPtr(scope.handle_buf, scope.label_buf)
            result = None
            if scope.value_buf is not None and size > 0:
                result = scope.value_buf[0]

        return result

    def set_string_list(
        self,
        handle: str,
        label: str,
        value: List[Union[str, bytes]]
    ) -> None:
        """
        Set a list of strings to an amalgam entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to set.
        value : list of str or list of bytes
            A 1d list of string values.
        """
        self.amlg.SetStringList.restype = c_void_p
        self.amlg.SetStringList.argtype = [
            c_char_p, c_char_p, POINTER(c_char_p), c_size_t]

        size = len(value)
        with self.scope_manager.capi_scope() as scope:
            scope.value_buf = (c_char_p * size)()
            for i in range(size):
                if isinstance(value[i], bytes):
                    scope.value_buf[i] = c_char_p(value[i])
                else:
                    scope.value_buf[i] = c_char_p(value[i].encode('utf-8'))

            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)
            self.amlg.SetStringList(
                scope.handle_buf, scope.label_buf, scope.value_buf, size)

    def get_string_list(self, handle: str, label: str) -> List[bytes]:
        """
        Retrieve a list of numbers from a label in an amalgam entity.

        Parameters
        ----------
        handle : str
            The handle of the amalgam entity.
        label : str
            The label to execute.

        Returns
        -------
        list of bytes
            A 1d list of byte-encoded string values from the label in the
            amalgam entity.
        """
        self.amlg.GetStringListLength.restype = c_size_t
        self.amlg.GetStringListLength.argtype = [c_char_p, c_char_p]
        self.amlg.GetStringListPtr.restype = POINTER(c_char_p)
        self.amlg.GetStringListPtr.argtype = [c_char_p, c_char_p]
        with self.scope_manager.capi_scope() as scope:
            scope.handle_buf = self.str_to_char_p(handle)
            scope.label_buf = self.str_to_char_p(label)

            size = self.amlg.GetStringListLength(scope.handle_buf,
                                                 scope.label_buf)
            scope.value_buf = self.amlg.GetStringListPtr(scope.handle_buf,
                                                         scope.label_buf)
            value = [scope.value_buf[i] for i in range(size)]

        return value

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
