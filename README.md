# Amalgam&reg;

Amalgam&reg; is an LLM-ready, tree-structured language for safe, sandboxed code generation, manipulation, and advanced information-theoretic inference.  Unlike traditional languages that prioritize developer shorthand, Amalgam focuses on code-data symmetry and semantic consistency.  These properties give it unique strengths in a wide variety of domains, including [genetic programming](https://en.wikipedia.org/wiki/Generic_programming), [instance-based machine learning](https://en.wikipedia.org/wiki/Instance-based_learning), simulation, agent-based modeling, data storage and retrieval, the mathematics of probability theory and information theory, and game content and AI.  This package supports directly calling the language via Python.

Coding in [Amalgam](https://github.com/howsoai/amalgam) can be done natively as demonstrated in the [Amalgam User Guide](https://github.com/howsoai/amalgam/blob/main/AMALGAM-BEGINNER-GUIDE.md) or through this Python wrapper.


## Supported Platforms

Compatible with Python versions: 3.11, 3.12, 3.13, 3.14, and 3.15.

#### Operating Systems

Binaries are built for the following operating systems, though in theory they could be built for virtually any modern system.
| OS      | x86_64 | arm64 |
|---------|--------|-------|
| Windows | Yes    | No    |
| Linux   | Yes    | Yes   |
| MacOS   | No     | Yes   |


## Install

To install the current release:
```bash
pip install amalgam-lang
```

## Usage

This wrapper allows the user to write and execute Amalgam&trade; code in Python, just like any other Python program. Once the wrapper is imported, the code handles like native Python code as shown below:

```python
from amalgam.api import Amalgam
import json

amlg = Amalgam()
# Load entity .amlg or .caml file
amlg.load_entity("handle_name", "/path/to/file.amlg")
# Execute a label in the loaded entity, passing parameters as JSON
response = amlg.execute_entity_json("handle_name", "label_name", json.dumps({ "abc": 123 }))
result = json.loads(response)
```

The wrapper handles the Amalgam language binary (so/dll/dylib) automatically for the user, however the default binary can be overridden using the `library_path` parameter.

```python
amlg = Amalgam(library_path="/path/to/amalgam-mt.so")
```

### Native backends

The wrapper calls the Amalgam C library through one of two backends: the compiled C extension `amalgam._api`, or a fallback backend that calls the library through `ctypes`. Both backends pass `bytes` arguments to the engine without copying them; the C extension also passes ASCII `str` arguments, such as `json.dumps()` output, without the UTF-8 copy the `ctypes` backend makes, which matters for large payloads. The `AMALGAM_PY_BACKEND` environment variable selects one:

- `auto` (the default, also used when the variable is unset or empty) uses the C extension when it is installed and `ctypes` otherwise.
- `c` uses the C extension, and raises `ImportError` when it is not installed.
- `ctypes` always uses `ctypes`.

Releases publish `cp311-abi3` wheels that include the C extension for Linux (manylinux, x86_64 and aarch64), macOS (arm64), and Windows (amd64), plus a `py3-none-any` wheel without it that always uses `ctypes`. A source or editable install (`pip install .` or `pip install -e .`) compiles it, which needs a C compiler; without one, the install still succeeds and uses the `ctypes` backend.

## Testing
There is a `Pytest` unit test suite located in `amalgam/test`. Most tests load the Amalgam library from `amalgam/lib/{os}/{architecture}` and are skipped when it is not there; link or copy the libraries from a local [Amalgam](https://github.com/howsoai/amalgam) build into that directory, or download a release matching `version.json` and copy its `lib/` files there.

To specify whether the tests should use single-threaded or multi-threaded `Amalgam`, set the `AMALGAM_LIBRARY_POSTFIX` environment variable to the desired postfix, e.g., `-st` or `-mt`.

Tests that call the library run once per native backend. The C extension backend is skipped when the extension is not built; pass `--require-c-extension` (on by default when the `CI` environment variable is set to a truthy value, meaning anything other than empty, `0`, `false`, `no`, or `off`, ignoring case and surrounding whitespace) to make a missing extension a test failure instead.

## License

[License](LICENSE.txt)

## Contributing

[Contributing](CONTRIBUTING.md)
