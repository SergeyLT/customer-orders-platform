FROM node:24-alpine AS frontend
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM nginx:1.30.6-alpine

ARG APP_VERSION=dev
ARG RELEASE_ID=local
LABEL org.opencontainers.image.title="Customer Orders Platform" \
      org.opencontainers.image.revision="${APP_VERSION}"

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend /build/dist/ /usr/share/nginx/html/
RUN printf '{"status":"ok","component":"web","version":"%s","release":"%s"}\n' \
      "$APP_VERSION" "$RELEASE_ID" > /usr/share/nginx/html/health.json \
    && chmod -R a+rX /usr/share/nginx/html /etc/nginx/nginx.conf

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/health"]
# Статическому серверу не нужны общие секреты ресурса Coolify.
ENTRYPOINT ["/usr/bin/env", "-i", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "nginx"]
CMD ["-g", "daemon off;"]
