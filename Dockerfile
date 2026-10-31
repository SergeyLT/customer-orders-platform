FROM nginx:1.30.6-alpine

ARG APP_VERSION=dev
ARG RELEASE_ID=local
LABEL org.opencontainers.image.title="Customer Orders Platform" \
      org.opencontainers.image.revision="${APP_VERSION}"

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY web/index.html /usr/share/nginx/html/index.html
RUN printf '{"status":"ok","component":"web","version":"%s","release":"%s"}\n' \
      "$APP_VERSION" "$RELEASE_ID" > /usr/share/nginx/html/health.json \
    && chmod -R a+rX /usr/share/nginx/html /etc/nginx/nginx.conf

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
