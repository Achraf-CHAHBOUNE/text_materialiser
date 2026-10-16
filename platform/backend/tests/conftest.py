"""Each test file runs against its own database and folder, as if run alone.

A test file sets its environment when it is imported (DB_DIR, FILESTORE_DIR, ...).
pytest imports every file before running any, so without this the files would all
share whichever database was opened first, and one file's rulings would leak into
another's counts. Here each file's environment is noted once it is imported, and put
back -- settings re-read, database and store reconnected -- before its tests run.
"""
import os

import pytest

_ENV: dict = {}


def pytest_collectreport(report):
    if report.nodeid.endswith(".py") and report.passed:
        _ENV[report.nodeid.split("::")[0]] = dict(os.environ)


@pytest.fixture(autouse=True, scope="module")
def _own_environment(request):
    env = _ENV.get(request.node.nodeid.split("::")[0])
    if env is None or "DB_DIR" not in env:
        yield
        return
    os.environ.clear()
    os.environ.update(env)
    import server
    server.configure()
    yield
