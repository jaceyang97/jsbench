FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY filter /etc/tinyproxy/filter
# -d: stay in foreground, log to stdout
ENTRYPOINT ["tinyproxy", "-d"]
