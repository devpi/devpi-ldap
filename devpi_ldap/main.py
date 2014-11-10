from __future__ import print_function
from __future__ import unicode_literals
from devpi_server.log import threadlog
try:
    from devpi_server.auth import AuthException
except ImportError:
    class AuthException(Exception):
        pass
import argparse
import getpass
import ldap3
import os
import socket
import sys
import yaml


ldap = None


PY3 = sys.version_info[0] == 3


if PY3:
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
else:
    exec("""def reraise(tp, value, tb=None):\n    raise tp, value, tb""")


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
    ldap3 = ldap3  # for dependency injection
    LDAPException = ldap3.core.exceptions.LDAPException  # for dependency injection

    def __init__(self, path):
        self.path = os.path.abspath(path)
        if not os.path.exists(self.path):
            fatal("No config at '%s'." % self.path)
        with open(self.path) as f:
            _config = yaml.load(f)
        self.update(_config.get('devpi-ldap', {}))
        if 'url' not in self:
            fatal("No url in LDAP config.")
        if 'user_template' in self:
            if 'user_search' in self:
                fatal("The LDAP options 'user_template' and 'user_search' are mutually exclusive.")
        else:
            if 'user_search' not in self:
                fatal("You need to set either 'user_template' or 'user_search' in LDAP config.")
            self._validate_search_settings('user_search')
        if 'group_search' not in self:
            threadlog.info("No group search setup for LDAP.")
        else:
            self._validate_search_settings('group_search')
        known_keys = set((
            'url',
            'user_template',
            'user_search',
            'group_search',
            'referrals',
            'reject_as_unknown',
        ))
        unknown_keys = set(self.keys()) - known_keys
        if unknown_keys:
            fatal("Unknown option(s) '%s' in LDAP config." % ', '.join(
                sorted(unknown_keys)))

    def _validate_search_settings(self, configname):
        config = self[configname]
        for key in ('base', 'filter', 'attribute_name'):
            if key not in config:
                fatal("Required option '%s' not in LDAP '%s' config." % (
                    key, configname))
        known_keys = set((
            'base', 'filter', 'scope', 'attribute_name', 'userdn', 'password'))
        unknown_keys = set(config.keys()) - known_keys
        if unknown_keys:
            fatal("Unknown option(s) '%s' in LDAP '%s' config." % (
                ', '.join(sorted(unknown_keys)), configname))
        if 'scope' in config:
            try:
                self._search_scope(config)
            except KeyError:
                fatal("Unknown search scope '%s'." % config['scope'])
        if 'userdn' in config:
            if 'password' not in config:
                fatal("You have to set a 'password' if you use a 'userdn' in LDAP '%s' config." % configname)

    def server(self):
        return self.ldap3.Server(self['url'])

    def connection(self, server, userdn=None, password=None):
        conn = self.ldap3.Connection(
            server,
            auto_referrals=self.get('referrals', True),
            read_only=True, user=userdn, password=password)
        return conn

    def _search_scope(self, config):
        scopes = {
            'base-object': self.ldap3.SEARCH_SCOPE_BASE_OBJECT,
            'single-level': self.ldap3.SEARCH_SCOPE_SINGLE_LEVEL,
            'whole-subtree': self.ldap3.SEARCH_SCOPE_WHOLE_SUBTREE}
        return scopes[config.get('scope', 'whole-subtree')]

    def _search(self, conn, config, **kw):
        config = dict(config)
        search_userdn = config.get('userdn')
        search_password = config.get('password')
        if 'password' in config:
            # obscure password in logs
            config['password'] = '********'
        if conn is None:
            if search_userdn is None:
                conn = self.connection(self.server())
            else:
                conn = self.connection(
                    self.server(),
                    userdn=search_userdn, password=search_password)
            if not self._open_and_bind(conn):
                threadlog.error("Search failed, couldn't bind user %s %s: %s" % (search_userdn, config, conn.result))
                return []
        else:
            if search_userdn is not None and conn.user != search_userdn:
                conn = self.connection(
                    self.server(),
                    userdn=search_userdn, password=search_password)
                if not self._open_and_bind(conn):
                    threadlog.error("Search failed, couldn't bind user %s %s: %s" % (search_userdn, config, conn.result))
                    return []
        search_filter = config['filter'].format(**kw)
        search_scope = self._search_scope(config)
        attribute_name = config['attribute_name']
        found = conn.search(
            config['base'], search_filter,
            search_scope=search_scope, attributes=[attribute_name])
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
            reraise(AuthException, AuthException(msg), sys.exc_info()[2])
        except self.LDAPException:
            msg = "Couldn't open LDAP connection to %s" % self['url']
            threadlog.exception(msg)
            reraise(AuthException, AuthException(msg), sys.exc_info()[2])
        return True

    def _userdn(self, username):
        if 'user_template' in self:
            return self['user_template'].format(username=username)
        else:
            result = self._search(None, self['user_search'], username=username)
            if len(result) == 1:
                return result[0]
            elif not result:
                threadlog.info("No user '%s' found." % username)
            else:
                threadlog.error("Multiple results for user '%s' found.")

    def _rejection(self):
        reject_as_unknown = self.get('reject_as_unknown', False)
        if reject_as_unknown:
            return dict(status="unknown")
        return dict(status="reject")

    def validate(self, username, password):
        """ Tries to bind the user against the LDAP server using the supplied
            username and password.

            Returns a dictionary with status and if configured groups of the
            authenticated user.
        """
        threadlog.debug("Validating user '%s' against LDAP at %s." % (username, self['url']))
        username = escape(username)
        userdn = self._userdn(username)
        if not userdn:
            return dict(status="unknown")
        if not password.strip():
            return self._rejection()
        conn = self.connection(self.server(), userdn=userdn, password=password)
        if not self._open_and_bind(conn):
            return self._rejection()
        config = self.get('group_search', None)
        if not config:
            return dict(status="ok")
        groups = self._search(conn, config, username=username, userdn=userdn)
        return dict(status="ok", groups=groups)


class LDAPConfigAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        global ldap
        ldap = LDAP(values)
        setattr(namespace, self.dest, ldap)


def devpiserver_add_parser_options(parser):
    ldap = parser.addgroup("LDAP authentication")
    ldap.addoption(
        "--ldap-config", action=LDAPConfigAction,
        help="LDAP configuration file")


def devpiserver_auth_user(userdict, username, password):
    if ldap is None:
        threadlog.debug("No LDAP settings given on command line.")
        return dict(status="unknown")
    return ldap.validate(username, password)


def main(argv=None):
    import json
    import logging
    socket.setdefaulttimeout(10)

    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s %(levelname)-5.5s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument(action='store', dest='config')
    parser.add_argument(nargs='?', action='store', dest='username')
    args = parser.parse_args(argv)
    ldap = LDAP(args.config)
    username = args.username
    if not username:
        username = raw_input("Username: ")
    password = getpass.getpass("Password: ")
    result = ldap.validate(username, password)
    print("Result: %s" % json.dumps(result, sort_keys=True))
    if result["status"] == "unknown":
        print("No user named '%s' found." % username)
    elif result["status"] == "reject":
        print("Authentication of user named '%s' failed." % username)
    else:
        print("Authentication successful, the user is member of the following groups: %s" % ', '.join(result.get("groups", [])))
