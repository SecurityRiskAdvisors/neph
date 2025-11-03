# Neo4j graphs in Jupyter

Neph provides a preconfigured JupyterLab service as part of the Compose file.
This JupyterLab server comes preinstalled with the Neph Python package, [yfiles-jupyter-graphs-for-neo4j](https://github.com/yWorks/yfiles-jupyter-graphs-for-neo4j), and [Pandas](https://pandas.pydata.org/).
It also has has a notebook with queries and analysis documentation.
Instruction for using this notebook can be found at the top of the notebook (`queries.ipynb` within JupyterLab).

When querying data using the provided notebook, you can make use of the following functions to display data:

To return a Graph:

```{code-cell}
g.show_cypher("<Cypher query>")
```

To return as Pandas DataFrame (for example, tabular data):

```{code-cell}
query_as_df("<Cypher query>")
```

## Example analysis queries

The included JupyterLab server includes a notebook containing example queries (see [here](../dockerfiles/jupyter/queries.md)).
