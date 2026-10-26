# ke-neo4j: the official Neo4j Community image without products/ (Q67).
# products/ holds the commercially licensed fleet-management plugin (and the
# unused GenAI plugin); the stack never sets NEO4J_PLUGINS (design-notes N16).
# Config below re-set from `docker image inspect <ref> --format '{{json .Config}}'`;
# re-read it on every digest bump.
FROM neo4j:5-community@sha256:0a6e7aedf54a531f76286032d4365ead65b11cca05e4a15cdf23b8e53d6db02b AS runtime
RUN rm -rf /var/lib/neo4j/products

# One layer: a delete in a layer on the base would leave the jar in the saved tar.
# USER stays unset (root): the entrypoint chowns NEO4J_HOME, /data and /logs,
# then drops to uid 7474. The base sets no HEALTHCHECK, LABEL or STOPSIGNAL.
FROM scratch
COPY --from=runtime / /
ENV PATH=/var/lib/neo4j/bin:/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    JAVA_HOME=/opt/java/openjdk \
    NEO4J_SHA256=d279ae6a9b38034280681a558b0cd222dce89f87cc3d9867f1f7bd28ef5ebc30 \
    NEO4J_TARBALL=neo4j-community-5.26.32-unix.tar.gz \
    NEO4J_EDITION=community \
    NEO4J_HOME=/var/lib/neo4j \
    LANG=C.UTF-8
WORKDIR /var/lib/neo4j
VOLUME ["/data", "/logs"]
EXPOSE 7473 7474 7687
ENTRYPOINT ["tini", "-g", "--", "/startup/docker-entrypoint.sh"]
CMD ["neo4j"]
