# Plugins

You can extend Neph by providing it with additional classes for the different base features, such as Nodes and Edges. 
You can do this by using Python entry points (see [1](https://setuptools.pypa.io/en/latest/userguide/entry_point.html#entry-points-for-plugins) and [2](https://packaging.python.org/en/latest/specifications/entry-points/)).

## Entry points

Neph uses the following entry points:

- `neph.node`: Node classes
- `neph.edge`: Edge classes
- `neph.enrichment`: Enrichment classes
- `neph.lead`: Lead classes
- `neph.report`: Report classes

## Example: Node

To add a new Node to the graph, do the following:

1. Create a new Python project using your tooling of choice.

2. Define your new Node class. This example will use EBS Volumes, which use the Steampipe table `aws_ebs_volume`

```python
from neph.nodes import BaseGraphNode

class EBSVolume(BaseGraphNode):
    table = "aws_ebs_volume"
    id    = "arn"
    label = "EBSVolume"
```

2. Edit your project configuration to include the entry point. See above for the defined entry point names.

For `pyproject.toml`:

```toml
[project.entry-points."neph.node"]
ebsvolume = "<project>:EBSVolume"
```

- Make sure to put in your project name. You may also need to include the module name before the colon if the class is located in a module (e.g. if `EBSVolume` is in `<project>/classes.py`, the value would be `<project>.classes:EBSVolume`).

Note: Some Python packaging tool use their own conventions for defining plugin entry points. For example, to specify in a [Poetry](https://python-poetry.org/) project, do:

```toml
[tool.poetry.plugins."neph.node"]
ebsvolume = "<project>:EBSVolume"
```

(see https://python-poetry.org/docs/plugins/#creating-a-plugin for details)

3. Build your project
4. Install the project in the same (virtual) environment as your Neph installation
