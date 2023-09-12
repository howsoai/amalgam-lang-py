
<div align="left">
  <img src="MarkdownLogo.svg">
</div>

The Howso Engine&trade; is a natively and fully explainable ML engine, serving as an alternative to black box AI neural networks. It’s core features give users data exploration and machine learning capabilities through the creation and use of Trainees that help users store, explore, and analyze the relationships in their data. Howso&trade; leverages an instance-based learning approach with strong ties to the [k-nearest neighbors algorithm](https://en.wikipedia.org/wiki/K-nearest_neighbors_algorithm) and [information theory](https://en.wikipedia.org/wiki/Information_theory) to scale for real world applications.

The Howso Engine is written in Amalgam&trade;, which is a domain specific language ([DSL](https://en.wikipedia.org/wiki/Domain-specific_language)) developed primarily for [genetic programming](https://en.wikipedia.org/wiki/Generic_programming) and [instance based machine learning](https://en.wikipedia.org/wiki/Instance-based_learning), but also for simulation, agent based modeling, data storage and retrieval, the mathematics of probability theory and information theory, and game content and AI. The language format is somewhat LISP-like in that it uses parenthesized list format with prefix notation and is geared toward functional programming, where there is a one-to-one mapping between the code and the corresponding parse tree.


## Resources
- [Amalgam](https://github.com/howsoai/amalgam)

## General Overview
Coding in [Amalgam](https://github.com/howsoai/amalgam) can be done natively as demonstrated in the [Amalgam User Guide](https://github.com/howsoai/amalgam/blob/main/AMALGAM-BEGINNER-GUIDE.md) or through this Amalgam&trade; Python wrapper. This Repo provides the Python Amalgam&trade; Wrapper which allows running programs written in the [Amalgam language](https://github.com/howsoai/amalgam) through the Amalgam dynamic library. This Python wrapper handles the binaries for the user so the user just needs to worry about the code. 


## Supported Platforms

Compatible with Python versions: 3.8, 3.9, 3.10, and 3.11

#### Operating Systems

| OS      | x86_64 | arm64 |
|---------|--------|-------|
| Windows | Yes    | No    |
| Linux   | Yes    | Yes   |
| MacOS   | Yes    | Yes   |


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

## License

[License](LICENSE.txt)

## Contributing

[Contributing](CONTRIBUTING.md)
