from __future__ import print_function
from __future__ import unicode_literals
from devpi_server.log import threadlog
try:
    from devpi_server.auth import AuthException
except ImportError:
    class AuthException(Exception):
        pass
import getpass
import json
import ldap3
import os
import socket
import sys


def escape(s):
    repl = (
        ('*', '\\\\2A'),
        ('(', '\\\\28'),
        (')', '\\\\29'),
        ('\\', '\\\\5C'),
        ('\0', '\\\\00'))
    for c, r in repl:
        s = s.replace(c, r)
    return s


def fatal(msg):
    threadlog.error(msg)
    sys.exit(1)


class LDAP(dict):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        if not os.path.exists(self.path):
            fatal("No config at '%s'." % self.path)
        with open(self.path) as f:
            _config = json.load(f)
        self.update(_config.get('devpi-ldap', {}))
        if 'url' not in self:
            fatal("No url in LDAP config.")
        if 'user_template' in self:
            if 'user_search' in self:
                fatal("The LDAP options 'user_template' and 'user_search' are mutually exclusive.")
        else:
            if 'user_search' not in self:
                fatal("You need to set either 'user_template' or 'user_search' in LDAP config.")
        if 'group_search' not in self:
            threadlog.info("No group search setup for LDAP.")
        known_keys = set((
            'url', 'user_template', 'user_search', 'group_search', 'referrals'))
        unknown_keys = set(self.keys()) - known_keys
        if unknown_keys:
            fatal("Unknown option(s) '%s' in LDAP config." % ', '.join(
                sorted(unknown_keys)))

    def server(self):
        return ldap3.Server(self['url'])

    def connection(self, server, userdn=None, password=None):
        conn = ldap3.Connection(
            server,
            auto_referrals=self.get('referrals', True),
            read_only=True, user=userdn, password=password)
        return conn

    def _search(self, conn, config, **kw):
        search_filter = config['filter'].format(**kw)
        attribute_name = config['attribute_name']
        found = conn.search(
            config['base'], search_filter, attributes=[attribute_name])
        if found:
            return sum((x['attributes'][attribute_name] for x in conn.response), [])
        else:
            threadlog.error("Search failed %s %s: %s" % (search_filter, config, conn.result))
            return []

    def _open_and_bind(self, conn):
        try:
            conn.open()
            if not conn.bind():
                return False
        except socket.timeout:
            msg = "Timeout on LDAP connect to %s" % self['url']
            threadlog.exception(msg)
            raise AuthException(msg), None, sys.exc_traceback
        except ldap3.core.exceptions.LDAPException:
            msg = "Couldn't open LDAP connection to %s" % self['url']
            threadlog.exception(msg)
            raise AuthException(msg), None, sys.exc_traceback
        return True

    def _userdn(self, username):
        if 'user_template' in self:
            return self['user_template'].format(username=username)
        else:
            conn = self.connection(self.server())
            self._open_and_bind(conn)
            result = self._search(conn, self['user_search'], username=username)
            if len(result) == 1:
                return result[0]
            elif not result:
                threadlog.info("No user '%s' found." % username)
            else:
                threadlog.error("Multiple results for user '%s' found.")

    def validate(self, username, password):
        """ Tries to bind the user against the LDAP server using the supplied
            username and password.

            If no user can be found, returns None.
            If the binding fails, returns False.
            On success a list of group names the user is member of will be
            returned, if no group search is set up, then the list will always
            be empty.
        """
        threadlog.debug("Validating user '%s' against LDAP at %s." % (username, self['url']))
        username = escape(username)
        userdn = self._userdn(username)
        if not userdn:
            return None
        conn = self.connection(self.server(), userdn=userdn, password=password)
        if not self._open_and_bind(conn):
            return False
        config = self.get('group_search', None)
        if not config:
            return []
        return self._search(conn, config, username=username, userdn=userdn)


def main():
    import argparse
    import logging
    socket.setdefaulttimeout(10)

    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s %(levelname)-5.5s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument(action='store', dest='config')
    parser.add_argument(nargs='?', action='store', dest='username')
    args = parser.parse_args()
    ldap = LDAP(args.config)
    username = args.username
    if not username:
        username = raw_input("Username: ")
    password = getpass.getpass("Password: ")
    result = ldap.validate(username, password)
    print("Result: %s" % result)
    if result is None:
        print("No user named '%s' found." % username)
    elif result is False:
        print("Authentication of user named '%s' failed." % username)
    else:
        print("Authentication successful, the user is member of the following groups: %s" % ', '.join(result))
