# syntax=docker/dockerfile:1

# builder stage
FROM golang:1.22-alpine as builder

# install build dependencies
RUN apk --no-cache add \
    gcc \
    musl-dev \
    linux-pam-dev \
    openssl

# copy source code
COPY rdpgw/ /src
WORKDIR /src

# generate certificates
RUN mkdir -p /opt/rdpgw && cd /opt/rdpgw && \
    random=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1) && \
    openssl genrsa -des3 -passout pass:$random -out server.pass.key 2048 && \
    openssl rsa -passin pass:$random -in server.pass.key -out key.pem && \
    rm server.pass.key && \
    openssl req -new -sha256 -key key.pem -out server.csr \
    -subj "/C=US/ST=VA/L=SomeCity/O=MyCompany/OU=MyDivision/CN=rdpgw" && \
    openssl x509 -req -days 365 -in server.csr -signkey key.pem -out server.pem

# build applications
ARG CACHEBUST
RUN go mod tidy -compat=1.19 && \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -tags '' -ldflags '' -o '/opt/rdpgw/rdpgw' ./cmd/rdpgw && \
    CGO_ENABLED=1 GOOS=linux go build -trimpath -tags '' -ldflags '' -o '/opt/rdpgw/rdpgw-auth' ./cmd/auth && \
    chmod +x /opt/rdpgw/rdpgw && \
    chmod +x /opt/rdpgw/rdpgw-auth && \
    chmod u+s /opt/rdpgw/rdpgw-auth

# runtime stage
FROM ghcr.io/linuxserver/baseimage-debian:bookworm

# set version label
ARG BUILD_DATE
ARG VERSION
ARG RDPGW_RELEASE
LABEL build_version="Linuxserver.io version:- ${VERSION} Build-date:- ${BUILD_DATE}"

# add local files
COPY root/ /

# create necessary directories
RUN mkdir -p /config /opt/rdpgw

# set ownership
RUN chown -R abc:abc /config /opt/rdpgw

# copy built binaries and certificates
COPY --from=builder /opt/rdpgw/ /opt/rdpgw/

# ports and volumes
EXPOSE 443/tcp
VOLUME /config
