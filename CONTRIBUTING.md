Contributing
============

Quick developer guide for running tests and understanding CI.

Running tests locally
---------------------
It's recommended to use a virtual environment for Python work. From the repository root:

- Create and activate a venv (macOS/Linux):
  python -m venv .venv
  source .venv/bin/activate

- Install test dependencies:
  pip install --upgrade pip
  pip install pytest pyserial cryptography

- Run unit tests only (fast):
  cd helper
  pytest -q -m "not integration"

- Run integration tests (slower, network-like):
  cd helper
  pytest -q -m integration

- Run the full test suite:
  cd helper
  pytest -q

Test markers
------------
The test suite separates fast unit tests from slower integration tests using a pytest marker named "integration". Unit/test runs exclude integration tests by default in CI; use the -m flag shown above to include or exclude them locally.

GitHub Actions CI
-----------------
The repository includes a GitHub Actions workflow at .github/workflows/ci.yml that runs a fast "unit" job on PRs and pushes, and an "integration" job (dependent on unit) that runs only on main pushes or when manually triggered. The CI caches pip downloads to speed up repeated runs.

If you add new Python test dependencies, update the install steps in the workflow or add a requirements file at the repository root for a more stable cache key.

If you want help adding more information to this guide (e.g., contributing style, commit message conventions, or how to run tests on macOS runners), say which section to expand.