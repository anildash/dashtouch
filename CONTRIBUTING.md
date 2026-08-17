Contributing
============

The protocol is documented in [docs/protocol.md](docs/protocol.md) and the
security model in [docs/security.md](docs/security.md). Improvements,
feedback, and pull requests are very welcome.

Running tests locally
---------------------

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e helper --no-deps
```

That last line is the one that's easy to skip and hard to diagnose. The tests
import `dashtouch_helper`, and nothing puts `helper/` on the import path on its
own — without the editable install you get `ModuleNotFoundError` from every
test file. (If you've already run `./setup`, it did this for you.)

Then:

```sh
cd helper
pytest -q
```

To run just the fast tests, or just the slow ones:

```sh
pytest -q -m "not integration"
pytest -q -m integration
```

Test layout
-----------

`helper/tests/` holds the unit tests. They're fast, and they already drive a
real HTTP server over real sockets — "unit" here means "no external services,"
not "no I/O."

`helper/tests/integration/` is for tests that cross a seam between components
that each have their own unit tests, where the seam itself is what breaks. The
current one starts the helper and then authenticates to it from the CLI side
using only the session token the helper left in the Keychain — a handoff that
neither half's own tests can see. Mark these with `@pytest.mark.integration`;
the marker is declared in `helper/pytest.ini`.

If you're adding a test that just exercises one module's behavior, it belongs
in the unit tests, even if it's doing socket work.

Dependencies
------------

`helper/pyproject.toml` is what governs an actual install of the helper.
`requirements.txt` at the repo root exists to pin CI and give the pip cache a
stable key; its runtime entries need to stay in step with pyproject's. If you
add a runtime dependency, it goes in both. Test-only dependencies go in
`requirements.txt` alone.

CI
--

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs the fast unit tests
on every push and pull request, and the integration tests on pushes to `main`
or on manual dispatch. It installs exactly the way the instructions above do,
so if it works locally it should work there.

CI runs on Linux, which has no macOS Keychain. The tests that cover Keychain
behavior patch `subprocess.run`, so they exercise the real argument-building
and read-back logic without ever invoking the `security` binary. Keep it that
way — a test that shells out to `security` for real will pass on your Mac and
fail in CI.
