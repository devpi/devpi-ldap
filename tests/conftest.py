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
