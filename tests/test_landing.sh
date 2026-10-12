#!/bin/sh
# Apply the image's patch to a disposable copy; leave the submodule untouched.
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
landing_tmp=$(mktemp -d "${TMPDIR:-/tmp}/rdpgw-landing-tests.XXXXXX")
trap 'rm -rf "$landing_tmp"' EXIT HUP INT TERM
cp -a "$repo_dir/rdpgw/." "$landing_tmp/"
rm -f "$landing_tmp/.git"
cd "$landing_tmp"
patch --batch --forward --fuzz=0 -p1 < "$repo_dir/patches/landing.patch"
# Some developer environments default to cross-compiling. Tests run locally.
export GOOS="$(go env GOHOSTOS)" GOARCH="$(go env GOHOSTARCH)"
export GOCACHE="${GOCACHE:-${TMPDIR:-/tmp}/rdpgw-go-cache}"
export GOMODCACHE="${GOMODCACHE:-${TMPDIR:-/tmp}/rdpgw-go-mod}"
go mod tidy -compat=1.19
go test ./cmd/rdpgw/... "$@"
