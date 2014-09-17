import yaml
import pytest


def test_importable():
    import devpi_ldap
    assert devpi_ldap.__version__


@pytest.fixture
def basic_ldap_config():
    return {"devpi-ldap": {"url": "ldap://localhost"}}


@pytest.fixture
def ldap_config(basic_ldap_config, tmpdir):
    config = tmpdir.join('ldap.yaml')
    d = dict(basic_ldap_config)
    d["devpi-ldap"]["user_template"] = "{username}"

    def dump(c):
        yml = yaml.dump(c, default_flow_style=False, explicit_start=True)
        print yml
        config.write(yml)
    config.dump = dump

    config.dump(d)
    return config


class MockConnection:
    def __init__(self, **kw):
        self.kw = kw

    def open(self):
        pass

    def bind(self):
        if self.kw.get('password') == '':
            return True
        return False


class MockLDAP3:
    def Server(self, url):
        pass

    def Connection(self, server, **kw):
        return MockConnection(**kw)


@pytest.fixture
def ldap(ldap_config):
    from devpi_ldap.main import LDAP
    ldap = LDAP(ldap_config.strpath)
    ldap.ldap3 = MockLDAP3()
    return ldap


def test_empty_password_fails(ldap):
    assert ldap.validate('user', '') is False
