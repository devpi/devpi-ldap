from devpi_common.metadata import Version
from devpi_server import __version__ as server_version
from devpi_server.log import threadlog
from devpi_server.auth import AuthException
from pluggy import HookimplMarker
import argparse
import getpass
import ldap3
import os
import socket
import sys
import yaml
import warnings


ldap = None
notset = object()
server_hookimpl = HookimplMarker("devpiserver")
DEFAULT_TIMEOUT = 10


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
            _config = yaml.safe_load(f)
        self.update(_config.get('devpi-ldap', {}))
        if 'server_pool' in self and 'url' in self:
            fatal("Both 'server_pool' and 'url' in LDAP config. Bad indentation?")
        if 'server_pool' not in self and 'url' not in self:
            fatal("Neither 'server_pool' nor 'url' in LDAP config.")
        if 'server_pool' in self:
            server_pool = self['server_pool']
            if not isinstance(server_pool, list):
                fatal("LDAP 'server_pool' needs to be a list.")
            if not server_pool:
                fatal("LDAP 'server_pool' is empty.")
            for server in server_pool:
                if 'url' not in server:
                    fatal("No 'url' in 'server_pool' server config.")
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
            'server_pool',
            'url',
            'user_template',
            'user_search',
            'group_search',
            'referrals',
            'reject_as_unknown',
            'tls',
            'login_template',
            'group_required'
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
        warnings.warn("'server()' is deprecated, please use 'server_pool()'.", category=DeprecationWarning, stacklevel=2)
        return self.server_pool()

    def _server(self, url, cfg):
        tls = cfg and self.ldap3.Tls(**cfg)
        return self.ldap3.Server(url, tls=tls)

    def server_pool(self):
        server_pool = self.ldap3.ServerPool()
        if 'server_pool' in self:
            for server in self['server_pool']:
                server_pool.add(self._server(server['url'], server.get('tls', None)))
        else:
            server_pool.add(self._server(self['url'], self.get('tls', None)))
        return server_pool

    def connection(self, server, userdn=None, password=None):
        conn = self.ldap3.Connection(
            server,
            auto_referrals=self.get('referrals', True),
            receive_timeout=self.get('timeout', DEFAULT_TIMEOUT),
            read_only=True, user=userdn, password=password)
        return conn

    def _search_scope(self, config):
        try:
            scopes = {
                'base-object': self.ldap3.BASE,
                'single-level': self.ldap3.LEVEL,
                'whole-subtree': self.ldap3.SUBTREE}
        except AttributeError:
            scopes = {
                'base-object': self.ldap3.SEARCH_SCOPE_BASE_OBJECT,
                'single-level': self.ldap3.SEARCH_SCOPE_SINGLE_LEVEL,
                'whole-subtree': self.ldap3.SEARCH_SCOPE_WHOLE_SUBTREE}
        return scopes[config.get('scope', 'whole-subtree')]

    def _build_search_conn(self, conn, config):
        """
        Given an existing bound connection and ldap search config,
        assess if the existing connection is suitable for search,
        and if not, attempt to bind such a connection. Return
        None if no suitable connection can be bound.

        side-effect: always mutates config to mask a password.
        """
        search_userdn = config.get('userdn')
        search_password = config.get('password')
        if search_userdn is None:
            search_password = None
        if 'password' in config:
            # obscure password in logs
            config['password'] = '********'
        needs_conn = (
            conn is None
            or (search_userdn is not None and conn.user != search_userdn)
        )
        if needs_conn:
            conn = self.connection(
                self.server_pool(),
                userdn=search_userdn, password=search_password)
            if not self._open_and_bind(conn):
                threadlog.error("Search failed, couldn't bind user %s %s: %s" % (search_userdn, config, conn.result))
                return
        return conn

    def _search(self, conn, config, **kw):
        config = dict(config)
        conn = self._build_search_conn(conn, config)
        if not conn:
            return []
        search_filter = config['filter'].format(**kw)
        search_scope = self._search_scope(config)
        attribute_name = config['attribute_name']
        found = conn.search(
            config['base'], search_filter,
            search_scope=search_scope, attributes=[attribute_name])
        if found:
            if any(attribute_name in x.get('attributes', {}) for x in conn.response):
                def extract_search(s):
                    if 'attributes' in s:
                        attributes = s['attributes'][attribute_name]
                        if not isinstance(attributes, list):
                            attributes = [attributes]
                        return attributes
                    else:
                        return []
            elif attribute_name in ('dn', 'distinguishedName'):
                def extract_search(s):
                    return [s[attribute_name]]
            else:
                threadlog.error('configured attribute_name {} not found in any search results'.format(attribute_name))
                return []

            return sum((extract_search(x) for x in conn.response), [])
        else:
            threadlog.error("Search failed %s %s: %s" % (search_filter, config, conn.result))
            return []

    def _open_and_bind(self, conn):
        try:
            conn.open()
            if not conn.bind():
                return False
        except socket.timeout:
            msg = "Timeout on LDAP connect to %s" % conn.server
            threadlog.exception(msg)
            # TODO: is re-raising an exception here still correct with a pool? Can it still happen?
            raise AuthException(msg)
        except self.LDAPException:
            msg = "Couldn't open LDAP connection to %s" % conn.server
            threadlog.exception(msg)
            # TODO: is re-raising an exception here still correct with a pool? Can it still happen?
            raise AuthException(msg)
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
        reject_as_unknown = self.get('reject_as_unknown', True)
        if reject_as_unknown:
            return dict(status="unknown")
        return dict(status="reject")

    def validate(self, username, password):
        """ Tries to bind the user against the LDAP server using the supplied
            username and password.

            Returns a dictionary with status and if configured groups of the
            authenticated user.
        """
        if 'server_pool' in self:
            threadlog.debug("Validating user '%s' against LDAP at %s." % (username, [
                server['url'] for server in self['server_pool']
            ]))
        else:
            threadlog.debug("Validating user '%s' against LDAP at %s." % (username, self['url']))
        username = escape(username)
        if 'login_template' in self:
            userdn = self['login_template'].format(self._userdn(username))
        else:
            userdn = self._userdn(username)

        if not userdn:
            return dict(status="unknown")
        if not password.strip():
            return self._rejection()
        conn = self.connection(self.server_pool(), userdn=userdn, password=password)
        if not self._open_and_bind(conn):
            return self._rejection()
        config = self.get('group_search', None)
        if not config:
            return dict(status="ok")
        groups = self._search(conn, config, username=username, userdn=userdn)
        group_required = self.get('group_required', False)
        if group_required and len(groups) < 1:
            return self._rejection()
        return dict(status="ok", groups=groups)


class LDAPConfigAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        global ldap
        ldap = LDAP(values)
        setattr(namespace, self.dest, ldap)


@server_hookimpl
def devpiserver_add_parser_options(parser):
    ldap = parser.addgroup("LDAP authentication")
    ldap.addoption(
        "--ldap-config", action=LDAPConfigAction,
        help="LDAP configuration file")


if Version(server_version) < Version("6dev"):
    @server_hookimpl
    def devpiserver_auth_user(userdict, username, password):
        if ldap is None:
            threadlog.debug("No LDAP settings given on command line.")
            return dict(status="unknown")
        return ldap.validate(username, password)
else:
    # because we are making network requests this plugin should run
    # last, so other plugins which don't require network requests are
    # running first and can possibly shortcut the authentication
    @server_hookimpl(trylast=True)
    def devpiserver_auth_request(request, userdict, username, password):
        if ldap is None:
            threadlog.debug("No LDAP settings given on command line.")
            return None
        # check for cached result
        result = getattr(request, '__devpi_ldap_validate_result', notset)
        if result is notset:
            result = ldap.validate(username, password)
            # cache result on request if available
            if request is not None:
                # we have to use setattr to avoid name mangling of prefix dunder
                setattr(request, '__devpi_ldap_validate_result', result)
        if result["status"] == "unknown":
            return None
        return result


def main(argv=None):
    import json
    import logging

    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s %(levelname)-5.5s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument(action='store', dest='config')
    parser.add_argument(nargs='?', action='store', dest='username')
    args = parser.parse_args(argv)
    ldap = LDAP(args.config)
    username = args.username
    if not username:
        username = input("Username: ")
    password = getpass.getpass("Password: ")
    result = ldap.validate(username, password)
    print("Result: %s" % json.dumps(result, sort_keys=True))

    if result["status"] == "unknown":
        print("No user named '%s' found." % username)
        raise SystemExit(1)

    if result["status"] == "reject":
        print("Authentication of user named '%s' failed." % username)
        raise SystemExit(2)

    print("Authentication successful, the user is member of the following groups: %s" % ', '.join(result.get("groups", [])))
    
