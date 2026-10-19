# ke-gateway: the official unprivileged nginx with the config baked in.
# Build context is the repository root (see docker-compose.yml).
FROM nginxinc/nginx-unprivileged:1.28-alpine@sha256:7377697a821c131a924a7105fafbe7414db4e9fcc77a6f08f776f33f141ec3f8

USER root
COPY docker/gateway/nginx.conf /etc/nginx/nginx.conf
COPY docker/gateway/templates/ /etc/nginx/templates/
COPY --chmod=0755 docker/gateway/10-ke-bind-check.sh /docker-entrypoint.d/10-ke-bind-check.sh
COPY --chmod=0755 docker/gateway/11-ke-upstream-check.sh /docker-entrypoint.d/11-ke-upstream-check.sh
COPY --chmod=0755 docker/gateway/12-ke-port-check.sh /docker-entrypoint.d/12-ke-port-check.sh
RUN rm -f /etc/nginx/conf.d/default.conf \
 && mkdir -p /etc/nginx/stream-conf.d \
 && chown nginx:nginx /etc/nginx/conf.d /etc/nginx/stream-conf.d

# Only KE_ variables and the resolver are substituted into the templates, so
# nginx's own $variables are left alone.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NGINX_ENVSUBST_FILTER='^(KE_|PHOENIX_PORT$|NGINX_LOCAL_RESOLVERS$)'
USER nginx
