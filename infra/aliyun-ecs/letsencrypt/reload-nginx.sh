#!/bin/sh
set -eu

/usr/local/nginx/sbin/nginx -t
/usr/local/nginx/sbin/nginx -s reload
