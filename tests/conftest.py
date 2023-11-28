from devpi_common.metadata import parse_version
from devpi_server import __version__ as _devpi_server_version
devpi_server_version = parse_version(_devpi_server_version)
if devpi_server_version < parse_version("6.9.3dev"):
    from test_devpi_server.conftest import gentmp, httpget, makemapp  # noqa
    from test_devpi_server.conftest import maketestapp, makexom, mapp  # noqa
    from test_devpi_server.conftest import pypiurls, testapp  # noqa
    from test_devpi_server.conftest import mock  # noqa
    try:
        from test_devpi_server.conftest import proxymock  # noqa
    except ImportError:
        pass
    try:
        from test_devpi_server.conftest import storage_info  # noqa
    except ImportError:
        pass
else:
    pytest_plugins = ["pytest_devpi_server", "test_devpi_server.plugin"]
