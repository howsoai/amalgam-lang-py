# Amalgam&reg;

Amalgam&reg; is an LLM-ready, tree-structured language for safe, sandboxed code generation, manipulation, and advanced information-theoretic inference.  Unlike traditional languages that prioritize developer shorthand, Amalgam focuses on code-data symmetry and semantic consistency.  These properties give it unique strengths in a wide variety of domains, including [genetic programming](https://en.wikipedia.org/wiki/Generic_programming), [instance based machine learning](https://en.wikipedia.org/wiki/Instance-based_learning), simulation, agent-based modeling, data storage and retrieval, the mathematics of probability theory and information theory, and game content and AI.  This package supports directly calling the language via Python.

Coding in [Amalgam](https://github.com/howsoai/amalgam) can be done natively as demonstrated in the [Amalgam User Guide](https://github.com/howsoai/amalgam/blob/main/AMALGAM-BEGINNER-GUIDE.md) or through this Python wrapper.


## Supported Platforms

Compatible with Python versions: 3.11, 3.12, 3.13, and 3.14.

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

## Testing
There is a `Pytest` unit test suite located in `amalgam/test`. The tests in `test_standalone.py` will only execute if an `Amalgam` binary is located in the default expected path of `amalgam/lib/{os}/{architecture}`.

To specify whether `test_standalone.py` should use single-threaded or multi-threaded `Amalgam` (assuming the appropriate binary is in the above path), set the `AMALGAM_LIBRARY_POSTFIX` environment variable to the desired postfix, e.g., `-st` or `-mt`.

## License

[License](LICENSE.txt)

## Contributing

[Contributing](CONTRIBUTING.md)
