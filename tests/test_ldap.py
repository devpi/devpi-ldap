from __future__ import print_function
import mock
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
def MockServer():
    class MockServer:
        users = {}

        def __init__(self, url):
            self.url = url
    return MockServer


class MockConnection:
    def __init__(self, server, **kw):
        self.server = server
        self.kw = kw

    def open(self):
        pass

    def bind(self):
        username = self.kw.get('user')
        user = self.server.users.get(username)
        if user is None:
            return False
        password = self.kw.get('password', False)
        if password == '' or user['pw'] == password:
            return True
        return False

    def search(self, base, search_filter, search_scope, attributes):
        search_filter = search_filter.split(":")
        if search_filter[0] == 'user':
            user = self.server.users.get(search_filter[1])
            if user is not None:
                self.response = [dict(attributes=dict(
                    (k, [user[k]]) for k in attributes))]
                return True
        elif search_filter[0] == 'group':
            group = self.server.groups.get(search_filter[1])
            if group is not None:
                self.response = [dict(attributes=dict(
                    (k, [group[k]]) for k in attributes))]
                return True
        self.result = "Search failed"
        return False


class MockLDAP3:
    Connection = MockConnection
    SEARCH_SCOPE_BASE_OBJECT = 0
    SEARCH_SCOPE_SINGLE_LEVEL = 1
    SEARCH_SCOPE_WHOLE_SUBTREE = 2


@pytest.fixture
def LDAP(MockServer):
    from devpi_ldap.main import LDAP
    LDAP = LDAP
    LDAP.ldap3 = MockLDAP3()
    LDAP.ldap3.Server = MockServer
    return LDAP


@pytest.fixture
def getpass(monkeypatch):
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
    main([user_template_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "Result: {'status': u'reject'}",
        "Authentication of user named 'user' failed."]


def test_main_user(MockServer, capsys, getpass, main, user_template_config):
    MockServer.users['user'] = dict(pw="password")
    getpass.return_value = "password"
    main([user_template_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "Result: {'status': u'ok'}",
        "Authentication successful, the user is member of the following groups: "]


def test_main_no_user_with_search(capsys, main, user_search_config):
    main([user_search_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "Result: {'status': u'unknown'}",
        "No user named 'user' found."]


def test_main_user_with_search(MockServer, capsys, getpass, main, user_search_config):
    MockServer.users['user'] = dict(pw="password", dn="user")
    getpass.return_value = "password"
    main([user_search_config.strpath, 'user'])
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "Result: {'status': u'ok'}",
        "Authentication successful, the user is member of the following groups: "]
