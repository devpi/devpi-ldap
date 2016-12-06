from __future__ import print_function, unicode_literals
import ldap3
import sys
import pytest
import yaml


def test_importable():
    import devpi_ldap
    assert devpi_ldap.__version__


@pytest.fixture
def ldap_config(tmpdir):
    config = tmpdir.join('ldap.yaml')

    def dump(c):
        yml = yaml.dump(c, default_flow_style=False, explicit_start=True)
        print(yml, file=sys.stderr)
        config.write(yml)
    config.dump = dump

    return config


@pytest.fixture
def user_template_config(ldap_config):
    ldap_config.dump({"devpi-ldap": {
        "url": "ldap://localhost",
        "user_template": "{username}"}})
    return ldap_config


@pytest.fixture
def user_search_config(ldap_config):
    ldap_config.dump({"devpi-ldap": {
        "url": "ldap://localhost",
        "user_search": {
            "base": "",
            "filter": "user:{username}",
            "attribute_name": "dn"}}})
    return ldap_config


@pytest.fixture
def userdn_search_config(ldap_config):
    ldap_config.dump({"devpi-ldap": {
        "url": "ldap://localhost",
        "user_search": {
            "userdn": "search",
            "password": "foo",
            "base": "",
            "filter": "user:{username}",
            "attribute_name": "dn"}}})
    return ldap_config


@pytest.fixture
def group_user_template_config(ldap_config):
    ldap_config.dump({"devpi-ldap": {
        "url": "ldap://localhost",
        "user_template": "{username}",
        "group_search": {
            "base": "",
            "filter": "group:{userdn}",
            "attribute_name": "cn"}}})
    return ldap_config


@pytest.fixture
def group_user_search_config(ldap_config):
    ldap_config.dump({"devpi-ldap": {
        "url": "ldap://localhost",
        "user_search": {
            "base": "",
            "filter": "user:{username}",
            "attribute_name": "dn"},
        "group_search": {
            "base": "",
            "filter": "group:{userdn}",
            "attribute_name": "cn"}}})
    return ldap_config


@pytest.fixture
def group_userdn_search_config(ldap_config):
    ldap_config.dump({"devpi-ldap": {
        "url": "ldap://localhost",
        "user_search": {
            "userdn": "search",
            "password": "foo",
            "base": "",
            "filter": "user:{username}",
            "attribute_name": "dn"},
        "group_search": {
            "base": "",
            "filter": "group:{userdn}",
            "attribute_name": "cn"}}})
    return ldap_config


@pytest.fixture
def reject_as_unknown_config(ldap_config):
    ldap_config.dump({"devpi-ldap": {
        "url": "ldap://localhost",
        "user_template": "{username}",
        "reject_as_unknown": True,
    }})
    return ldap_config


@pytest.fixture
def MockServer():
    class MockServer:
        users = {}

        def __init__(self, url, tls=None):
            self.url = url
    return MockServer


class MockConnection:
    def __init__(self, server, **kw):
        self.server = server
        self.user = kw.get('user')
        self.password = kw.get('password')

    def open(self):
        pass

    def bind(self):
        if self.user is None:
            return True
        user = self.server.users.get(self.user)
        if user is None:
            self.result = "Bind failed, user not found"
            return False
        if self.password == '' or user['pw'] == self.password:
            return True
        self.result = "Bind failed, invalid credentials"
        return False

    def search(self, base, search_filter, search_scope, attributes):
        # We have some hariness here to simulate the handling for openLDAP
        # servers that dont return dn as an attribute which we also do in
        # LDAP._search() in devpi_ldap/main.py
        class dnplaceholder(object):
            triggered = False

        def fixDn(user, k):
            if k in ('dn', 'distinguishedName'):
                dnplaceholder.triggered = k
                return dnplaceholder
            else:
                raise KeyError()

        search_filter = search_filter.split(":")
        if search_filter[0] == 'user':
            user = self.server.users.get(search_filter[1])
            if user is not None:
                self.response = [dict(attributes=dict(
                    (k, [user.get(k, fixDn(user, k))]) for k in attributes if fixDn(user, k) is not dnplaceholder))]
                if dnplaceholder.triggered:
                    self.response[0][dnplaceholder.triggered] = search_filter[1]
                return True
        elif search_filter[0] == 'group':
            user = self.server.users.get(search_filter[1])
            if user is not None and 'groups' in user:
                self.response = [
                    dict(attributes=dict(
                        (k, [g[k]]) for k in attributes))
                    for g in user['groups']]
                return True
        self.result = "Search failed"
        return False


class MockLDAP3:
    Connection = MockConnection
    try:
        BASE = ldap3.BASE
        LEVEL = ldap3.LEVEL
        SUBTREE = ldap3.SUBTREE
    except AttributeError:
        SEARCH_SCOPE_BASE_OBJECT = ldap3.SEARCH_SCOPE_BASE_OBJECT
        SEARCH_SCOPE_SINGLE_LEVEL = ldap3.SEARCH_SCOPE_SINGLE_LEVEL
        SEARCH_SCOPE_WHOLE_SUBTREE = ldap3.SEARCH_SCOPE_WHOLE_SUBTREE


@pytest.fixture
def LDAP(MockServer):
    from devpi_ldap.main import LDAP
    LDAP.ldap3 = MockLDAP3()
    LDAP.ldap3.Server = MockServer
    return LDAP


@pytest.fixture
def getpass(mock, monkeypatch):
    gp = mock.Mock()
    monkeypatch.setattr("getpass.getpass", gp)
    gp.return_value = ''
    return gp


@pytest.fixture
def main(getpass, LDAP, monkeypatch):
    from devpi_ldap.main import main
    return main


def test_empty_password_fails(LDAP, user_template_config):
    ldap = LDAP(user_template_config.strpath)
    assert ldap.validate('user', '') == dict(status="reject")


def test_main_no_user(capsys, main, user_template_config):
    with pytest.raises(SystemExit) as e:
        main([user_template_config.strpath, 'user'])
    assert e.value.code == 2
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"status": "reject"}',
        "Authentication of user named 'user' failed."]


def test_main_user(MockServer, capsys, getpass, main, user_template_config):
    MockServer.users['user'] = dict(pw="password")
    getpass.return_value = "password"
    main([user_template_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"status": "ok"}',
        "Authentication successful, the user is member of the following groups: "]


def test_main_no_user_with_search(capsys, main, user_search_config):
    with pytest.raises(SystemExit) as e:
        main([user_search_config.strpath, 'user'])
    assert e.value.code == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"status": "unknown"}',
        "No user named 'user' found."]


def test_main_user_with_search(MockServer, capsys, getpass, main, user_search_config):
    MockServer.users['user'] = dict(pw="password", dn="user")
    getpass.return_value = "password"
    main([user_search_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"status": "ok"}',
        "Authentication successful, the user is member of the following groups: "]


def test_main_user_with_search_userdn(MockServer, capsys, getpass, main, userdn_search_config):
    MockServer.users['search'] = dict(pw="foo", dn="search")
    MockServer.users['user'] = dict(pw="password", dn="user")
    getpass.return_value = "password"
    main([userdn_search_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"status": "ok"}',
        "Authentication successful, the user is member of the following groups: "]


def test_main_user_with_group(MockServer, capsys, getpass, main, group_user_template_config):
    MockServer.users['user'] = dict(pw="password", groups=[dict(cn='users')])
    getpass.return_value = "password"
    main([group_user_template_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"groups": ["users"], "status": "ok"}',
        "Authentication successful, the user is member of the following groups: users"]


def test_main_user_with_search_with_group(MockServer, capsys, getpass, main, group_user_search_config):
    MockServer.users['user'] = dict(pw="password", dn="user", groups=[dict(cn='users')])
    getpass.return_value = "password"
    main([group_user_search_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"groups": ["users"], "status": "ok"}',
        "Authentication successful, the user is member of the following groups: users"]


def test_main_user_with_search_nodnattribute(MockServer, capsys, getpass, main, user_search_config):
    MockServer.users['user'] = dict(pw="password", cn="user")
    getpass.return_value = 'password'
    main([user_search_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"status": "ok"}',
        "Authentication successful, the user is member of the following groups: "]


def test_main_user_with_search_userdn_with_group(MockServer, capsys, getpass, main, group_userdn_search_config):
    MockServer.users['search'] = dict(pw="foo", dn="search")
    MockServer.users['user'] = dict(pw="password", dn="user", groups=[dict(cn='users')])
    getpass.return_value = "password"
    main([group_userdn_search_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        'Result: {"groups": ["users"], "status": "ok"}',
        "Authentication successful, the user is member of the following groups: users"]


def test_reject_as_unknown(LDAP, reject_as_unknown_config):
    ldap = LDAP(reject_as_unknown_config.strpath)
    assert ldap._rejection() == dict(status="unknown")


def test_reject_as_unknown_empty(LDAP, reject_as_unknown_config):
    ldap = LDAP(reject_as_unknown_config.strpath)
    assert ldap.validate('user', '') == dict(status="unknown")


def test_socket_timeout(LDAP, mock, monkeypatch, user_template_config):
    from devpi_ldap.main import AuthException
    import socket
    monkeypatch.setattr(LDAP.ldap3.Connection, 'open', mock.Mock(side_effect=socket.timeout()))
    ldap = LDAP(user_template_config.strpath)
    with pytest.raises(AuthException) as e:
        ldap.validate('user', 'foo')
    assert e.value.args[0] == "Timeout on LDAP connect to ldap://localhost"


def test_ldap_exception(LDAP, mock, monkeypatch, user_template_config):
    from devpi_ldap.main import AuthException
    monkeypatch.setattr(LDAP.ldap3.Connection, 'open', mock.Mock(side_effect=LDAP.LDAPException()))
    ldap = LDAP(user_template_config.strpath)
    with pytest.raises(AuthException) as e:
        ldap.validate('user', 'foo')
    assert e.value.args[0] == "Couldn't open LDAP connection to ldap://localhost"


def test_extra_result_data(LDAP, MockServer, group_user_template_config):
    class Connection(MockConnection):
        def search(self, base, search_filter, search_scope, attributes):
            result = MockConnection.search(self, base, search_filter, search_scope, attributes)
            if self.response:
                self.response.insert(0, {})
            return result
    MockServer.users['user'] = dict(pw="password", groups=[dict(cn='users')])
    LDAP.ldap3.Connection = Connection
    ldap = LDAP(group_user_template_config.strpath)
    assert ldap.validate('user', 'password') == dict(status="ok", groups=[u'users'])


class TestAuthPlugin:
    @pytest.fixture
    def xom(self, makexom, user_template_config):
        import devpi_ldap.main
        xom = makexom(
            opts=['--ldap-config', user_template_config.strpath],
            plugins=[(devpi_ldap.main, None)])
        return xom

    def test_plugin_call(self, LDAP, MockServer, mapp, mock, monkeypatch, testapp):
        import devpi_ldap.main
        MockServer.users['user'] = dict(pw="password")
        validate = mock.Mock()
        validate.side_effect = devpi_ldap.main.ldap.validate
        monkeypatch.setattr(devpi_ldap.main.ldap, 'validate', validate)
        api = mapp.getapi()
        r = testapp.post_json(
            api.login, {"user": 'user', "password": 'password'})
        assert r.json['message'] == 'login successful'
        assert validate.called
