#!/bin/sh
set -eox

whoami

sudo apt-get install 389-ds-base python3-lib389


cat << EOF | sudo tee /root/instance.inf
# /root/instance.inf
[general]
config_version = 2

[slapd]
root_password = YOUR_ADMIN_PASSWORD_HERE

[backend-userroot]
sample_entries = yes
suffix = dc=example,dc=com
EOF

sudo dscreate from-file /root/instance.inf

dsctl localhost status

cat << EOF | sudo tee /root/.dsrc
[localhost]
# Note that '/' is replaced to '%%2f'.
uri = ldapi://%%2fvar%%2frun%%2fslapd-localhost.socket
basedn = dc=example,dc=com
binddn = cn=Directory Manager
EOF

sudo dsidm localhost user create --uid eve --cn Eve --displayName 'Eve User - Devpi test' --uidNumber 1001 --gidNumber 1001 --homeDirectory /home/eve
sudo dsidm localhost user create --uid alice --cn Alice --displayName 'Alice User - Devpi test' --uidNumber 1002 --gidNumber 1002 --homeDirectory /home/alice

sudo dsidm localhost group create --cn devpi_admins
sudo dsidm localhost group add_member devpi_admins uid=alice,ou=people,dc=example,dc=com
