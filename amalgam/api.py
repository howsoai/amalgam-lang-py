from ctypes import (
    byref, c_bool, c_char, c_char_p, c_double, c_size_t, c_uint64, c_void_p,
    cdll, POINTER
)
from datetime import datetime
import gc
import logging
from pathlib import Path
import platform
import re
from typing import Any, List, Optional, Tuple, Union
import warnings

# Set to amalgam
_logger = logging.getLogger('amalgam')


class Amalgam:
    """
    A general python direct interface to the Amalgam library.

    This is implemented with ctypes for accessing binary amalgam builds in
    Linux, MacOS and Windows.

    Parameters
    ----------
    library_path : Path or str
        Path to either the amalgam DLL, DyLib or SO (Windows, MacOS or
        Linux, respectively). If not specified it will build a path to the
        appropriate library bundled with the package.

    append_trace_file : bool, default False
        If True, new content will be appended to a tracefile if the file
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
            library_path, library_postfix)

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
                self.execution_trace_dir.mkdir(parents=True)

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
        if not self.library_path.exists():
            if library_path:
                raise FileNotFoundError(
                    'No Amalgam library was found at the provided '
                    '`library_path`. Please check that the path is correct.'
                )
            else:
                raise FileNotFoundError(
                    'The auto-determined Amalgam binary to use was not found. '
                    'This could indicate that the combination of operating '
                    'system, machine architecture and library-postfix is not '
                    'yet supported.'
                )
        _logger.debug(f"SBF_DATASTORE enabled: {sbf_datastore_enabled}")
        self.amlg = cdll.LoadLibrary(str(self.library_path))
        self.set_amlg_flags(sbf_datastore_enabled)
        self.set_max_num_threads(max_num_threads)
        self.gc_interval = gc_interval
        self.op_count = 0
        self.load_command_log_entry = None

    def _get_library_path(
        self,
        library_path: Optional[Union[Path, str]] = None,
        library_postfix: str = '-mt'
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

        Returns
        -------
        Path
            The path to the appropriate Amalgam shared lib (.dll, .so, .dylib).
        str
            The library prefix
        """
        if library_path:
            # Find the library postfix, if one is present in the given
            # library_path.
            filename = Path(library_path).name
            matches = re.findall(r'-(.+?)\.', filename)
            if len(matches) > 0:
                _library_postfix = f'-{matches[-1]}'
            else:
                _library_postfix = None
            if library_postfix and library_postfix != _library_postfix:
                warnings.warn(
                    'The supplied `library_postfix` does not match the '
                    'postfix given in `library_path` and will be ignored.',
                    UserWarning
                )
            library_postfix = _library_postfix

            library_path = Path(library_path).expanduser()
        else:
            # No library_path was provided so, auto-determine the correct one
            # to use for this running environment. For this, the operating
            # system, the machine architecture and postfix are used.
            os = platform.system().lower()

            if os == 'windows':
                path_os = 'windows'
                path_ext = 'dll'
            elif os == "darwin":
                path_os = 'darwin'
                path_ext = 'dylib'
            elif os == "linux":
                path_os = 'linux'
                path_ext = 'so'
            else:
                raise RuntimeError(
                    'Detected an unsupported machine platform type. Please '
                    'specify the `library_path` to the Amalgam shared library '
                    'to use with this platform.')

            arch = platform.machine().lower()

            if arch in ['x86_64', 'amd64']:
                path_arch = 'amd64'
            elif arch.startswith('aarch64') or arch.startswith('arm64'):
                # see: https://stackoverflow.com/q/45125516/440805
                path_arch = 'arm64'
            else:
                raise RuntimeError(
                    'Detected an unsupported machine architecture. Please '
                    'specify the `library_path` to the Amalgam shared library '
                    'to use with this machine architecture.')

            if not library_postfix:
                library_postfix = '-mt'

            # Default path for Amalgam binary should be at <package_root>/lib
            lib_root = Path(Path(__file__).parent, 'lib')

            # Build path
            library_path = Path(lib_root, path_os, path_arch,
                                f'amalgam{library_postfix}.{path_ext}')

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
        Log a labelled timestamp to the tracefile.

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

    def gc(self) -> None:
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
        value: Union[str, bytes],
        size: Optional[int] = None
    ) -> c_char:
        """
        Convert a string to a c++ char pointer.

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
            A c++ char point for the string.
        """
        if isinstance(value, str):
            value = value.encode('utf-8')
        buftype = c_char * (size if size is not None else (len(value) + 1))
        buf = buftype()
        buf.value = value
        return buf

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
        self.amlg.GetJSONPtrFromLabel.restype = c_char_p
        self.amlg.GetJSONPtrFromLabel.argtype = [c_char_p, c_char_p]
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        result = self.amlg.GetJSONPtrFromLabel(handle_buf, label_buf)
        self._log_execution(f"GET_JSON_FROM_LABEL {handle} {label}")
        del handle_buf
        del label_buf
        self.gc()
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
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        json_buf = self.str_to_char_p(json)
        self._log_execution(f"SET_JSON_TO_LABEL {handle} {label} {json}")
        self.amlg.SetJSONToLabel(handle_buf, label_buf, json_buf)
        del handle_buf
        del label_buf
        del json_buf
        self.gc()

    def load_entity(
        self,
        handle: str,
        amlg_path: str,
        persist: bool = False,
        load_contained: bool = False,
        write_log: str = "",
        print_log: str = ""
    ) -> bool:
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
        bool
            True if the entity was successfully loaded.
        """
        self.amlg.LoadEntity.argtype = [
            c_char_p, c_char_p, c_bool, c_bool, c_char_p, c_char_p]
        self.amlg.LoadEntity.restype = c_bool
        handle_buf = self.str_to_char_p(handle)
        amlg_path_buf = self.str_to_char_p(amlg_path)
        write_log_buf = self.str_to_char_p(write_log)
        print_log_buf = self.str_to_char_p(print_log)

        result = self.amlg.LoadEntity(
            handle_buf, amlg_path_buf, persist, load_contained,
            write_log_buf, print_log_buf)
        self.load_command_log_entry = (
            f"LOAD_ENTITY {handle} {amlg_path} {str(persist).lower()} "
            f"{str(load_contained).lower()} {write_log} {print_log}"
        )
        self._log_execution(self.load_command_log_entry)
        self._log_reply(result)
        del handle_buf
        del amlg_path_buf
        del write_log_buf
        del print_log_buf
        self.gc()
        return result

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
        self.amlg.ExecuteEntityJsonPtr.restype = c_char_p
        self.amlg.ExecuteEntityJsonPtr.argtype = [
            c_char_p, c_char_p, c_char_p]
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        json_buf = self.str_to_char_p(json)
        self._log_time("EXECUTION START")
        self._log_execution(f"EXECUTE_ENTITY_JSON {handle} {label} {json}")
        result = self.amlg.ExecuteEntityJsonPtr(
            handle_buf, label_buf, json_buf)
        self._log_time("EXECUTION STOP")
        self._log_reply(result)
        del handle_buf
        del label_buf
        del json_buf
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
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        val = c_double(value)
        self.amlg.SetNumberValue(handle_buf, label_buf, val)
        del handle_buf
        del label_buf
        del val
        self.gc()

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
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        result = self.amlg.GetNumberValue(handle_buf, label_buf)
        del handle_buf
        del label_buf
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
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        val_buf = self.str_to_char_p(value)
        self.amlg.SetStringValue(handle_buf, label_buf, val_buf)
        del handle_buf
        del label_buf
        del val_buf
        self.gc()

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
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        size = self.amlg.GetStringListLength(handle_buf, label_buf)
        value_buf = self.amlg.GetStringListPtr(handle_buf, label_buf)
        result = None
        if value_buf is not None and size > 0:
            result = value_buf[0]
        del handle_buf
        del label_buf
        del value_buf
        self.gc()
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
        value_buf = (c_char_p * size)()
        for i in range(size):
            if isinstance(value[i], bytes):
                value_buf[i] = c_char_p(value[i])
            else:
                value_buf[i] = c_char_p(value[i].encode('utf-8'))

        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        self.amlg.SetStringList(handle_buf, label_buf, value_buf, size)
        del handle_buf
        del label_buf
        del value_buf
        self.gc()

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
        handle_buf = self.str_to_char_p(handle)
        label_buf = self.str_to_char_p(label)
        size = self.amlg.GetStringListLength(handle_buf, label_buf)
        value_buf = self.amlg.GetStringListPtr(handle_buf, label_buf)
        value = [value_buf[i] for i in range(size)]
        del handle_buf
        del label_buf
        del value_buf
        self.gc()
        return value

    def get_version_string(self) -> bytes:
        """
        Get the version string of the amalgam dynamic library.

        Returns
        -------
        bytes
            A version byte-encoded string with semver.
        """
        self.amlg.GetVersionString.restype = c_char_p
        amlg_version = self.amlg.GetVersionString()
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
        self.amlg.GetConcurrencyTypeString.restype = c_char_p
        amlg_concurrency_type = self.amlg.GetConcurrencyTypeString()
        self._log_comment(
            f"call to amlg.GetConcurrencyTypeString() - returned: "
            f"{amlg_concurrency_type}\n")
        return amlg_concurrency_type
