#!/bin/sh
set -eox

whoami

sudo apt-get install 389-ds-base

cat <<EOF > /root/instance.inf
# /root/instance.inf
[general]
config_version = 2

[slapd]
root_password = YOUR_ADMIN_PASSWORD_HERE

[backend-userroot]
sample_entries = yes
suffix = dc=example,dc=com
EOF

dscreate from-file /root/instance.inf

dsctl localhost status

cat << EOF > /root/.dsrc
[localhost]
# Note that '/' is replaced to '%%2f'.
uri = ldapi://%%2fvar%%2frun%%2fslapd-localhost.socket
basedn = dc=example,dc=com
binddn = cn=Directory Manager
EOF

dsidm localhost user create --uid eve --cn Eve --displayName 'Eve User - Devpi test' --uidNumber 1001 --gidNumber 1001 --homeDirectory /home/eve
dsidm localhost user create --uid alice --cn Alice --displayName 'Alice User - Devpi test' --uidNumber 1002 --gidNumber 1002 --homeDirectory /home/alice

dsidm localhost group create --cn devpi_admins
dsidm localhost group add_member devpi_admins uid=alice,ou=people,dc=example,dc=com
