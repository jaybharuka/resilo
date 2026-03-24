FROM nginx:1.25-alpine

# Install openssl for self-signed cert generation
RUN apk add --no-cache openssl

# Generate self-signed TLS certificate (replace with real cert in production)
RUN mkdir -p /etc/nginx/certs && \
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout /etc/nginx/certs/server.key \
      -out    /etc/nginx/certs/server.crt \
      -subj   "/C=US/ST=State/L=City/O=AIOps/CN=aiops-local" \
      -extensions v3_req \
      -addext "subjectAltName=DNS:localhost,DNS:aiops-local,IP:127.0.0.1" \
    2>/dev/null

COPY nginx.conf /etc/nginx/nginx.conf

# React build is volume-mounted or COPY'd in docker-compose
# COPY ../dashboard/build/ /usr/share/nginx/html/

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
