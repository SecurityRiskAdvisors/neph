# Docs

| Document      | Description                          |
|---------------|--------------------------------------|
| Cli.md        | Command line usage                   |
| Collection.md | Data collection and customization    |
| Jupyter.md    | Jupyter notebook integration details |
| Overview.md   | Overall tool details                 |
| Plugins.md    | External module use and development  |
| Queries.md    | Example Cypher queries               |
| Quickstart.md | Quickstart guide                     |
| Simulator.md  | Local IAM simulation details         |
| Triggers.md   | Neph Neo4j eventing system           |

## Python API docs

Python API docs are available in the `autodocs` root directory. 
If you have developed Neph modules, you can include them in the API docs by regenerating the docs via the `autodocs` Make target.
To do so, you will need to first have the modules installed in the current Python (virtual) environment and uncomment the call to `load_all_plugins()` in `sphinx_config.py`.

