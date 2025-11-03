FROM quay.io/jupyter/base-notebook:python-3.12

WORKDIR /app
COPY dist/neph-*-py3-none-any.whl .
RUN pip install *.whl
RUN pip install yfiles_jupyter_graphs_for_neo4j neo4j jupytext pandas

WORKDIR /notebooks
COPY dockerfiles/jupyter/*.md .
RUN jupytext --to ipynb *.md
RUN rm *.md
