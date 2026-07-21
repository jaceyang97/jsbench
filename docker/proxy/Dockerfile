FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
# FILTER selects the blocklist: `filter` (Claude: allow Anthropic, block OpenAI)
# or `filter.codex` (Codex: allow OpenAI, block Anthropic). Both block every
# solution source; only the inference endpoint differs, kept symmetric.
ARG FILTER=filter
COPY ${FILTER} /etc/tinyproxy/filter
# -d: stay in foreground, log to stdout
ENTRYPOINT ["tinyproxy", "-d"]
