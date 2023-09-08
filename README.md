# Amalgam&trade; Wrapper - Python

This Python module allows running programs written in the [Amalgam language](https://github.com/howsoai/amalgam) through the Amalgam dynamic library.

## Supported Platforms

Compatible with Python versions: 3.8, 3.9, 3.10, and 3.11

#### Operating Systems

| OS      | x86_64 | arm64 |
|---------|--------|-------|
| Windows | Yes    | No    |
| Linux   | Yes    | Yes   |
| MacOS   | Yes    | Yes   |

## Installing

```bash
pip install amalgam-lang
```

## Getting Started

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

The path to the Amalgam language binary (so/dll/dylib) can be overridden using the `library_path` parameter.

```python
amlg = Amalgam(library_path="/path/to/amalgam-mt.so")
```

## Development

1. Install development dependencies `pip install -r requirements-dev.in`
2. Run tests: `python -m pytest amalgam`

## License

[License](LICENSE.txt)

## Contributing

[Contributing](CONTRIBUTING.md)
