FROM neo4j:5.26

ARG APOC_CORE_VER=5.26.0
ARG APOC_EXTENDED_VER=5.26.0
ARG PSQL_JDBC_VER=42.7.5

# add the plugin jars to the image
RUN mkdir /plugins
RUN wget -O /plugins/apoc.jar "https://github.com/neo4j/apoc/releases/download/$APOC_CORE_VER/apoc-$APOC_CORE_VER-core.jar"
RUN wget -O /plugins/apoc-extended.jar "https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases/download/$APOC_EXTENDED_VER/apoc-$APOC_EXTENDED_VER-extended.jar"
RUN wget -O /plugins/postgres-jdbc.jar "https://jdbc.postgresql.org/download/postgresql-$PSQL_JDBC_VER.jar"

# below originates from base neo4j image
# ex: https://github.com/docker-library/repo-info/blob/master/repos/neo4j/local/5.26.md
WORKDIR /var/lib/neo4j
ENTRYPOINT ["tini", "-g", "--", "/startup/docker-entrypoint.sh"]
CMD ["neo4j"]