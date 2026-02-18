# Contributing

We want to make contributing to this project as easy and transparent as possible.

## Install latest version

Before you request a feature or report an issue, verify whether the proposal has already been implemented in one of the commits on the branch `master`. Instruct `pip` to install the package directly from source control rather than PyPI:

```sh
pip install git+https://github.com/hunyadi/md2conf.git@master
```

Due to constrained capacity, we only support the latest release of *md2conf*.

## Pull requests

We actively welcome your pull requests. Keep changes concise to help reviewers. Make sure you focus on a single bugfix or a single feature.

### Prerequisites

Python is installed. Minimum version we support is Python 3.9.

### Helping you get set up

1. Create a GitHub issue proposing the feature you would like to have added.
2. Fork the repo and create your branch from `master`.
3. Set up your environment:

   ```sh
   git clone git@github.com:<your github username>/md2conf.git
   python -m venv ".venv"
   source .venv/bin/activate
   python -m pip install ".[formulas,dev]"
   ```

4. If you've added code that should be tested, add tests to either `tests` or `integration_tests` directory.
   Note: The directory `integration_tests` assumes you have an active Confluence instance to run those against.

### Running unit tests

```
python -m unittest discover -s tests
```

### Running integration tests

Before running these tests, you must set up your environment variables (e.g. add to your `~/.profile` on Linux, or `~/.bash_profile` or `~/.zshenv` on MacOS, or *System properties* on Windows.):

**For Confluence Cloud:**
```bash
CONFLUENCE_DOMAIN='<your domain>.atlassian.net'
CONFLUENCE_PATH='/wiki/'
CONFLUENCE_USER_NAME='<your email>'
CONFLUENCE_API_KEY='0123456789abcdef'
CONFLUENCE_SPACE_KEY='<your space key>'
```

**For Confluence Data Center/Server:**
```bash
CONFLUENCE_DEPLOYMENT_TYPE='datacenter'  # or 'server'
CONFLUENCE_DOMAIN='confluence.company.com'
CONFLUENCE_PATH='/wiki/'
CONFLUENCE_API_KEY='<your personal access token>'
CONFLUENCE_SPACE_KEY='<your space key>'
CONFLUENCE_USER_NAME='<your username>'  # Optional: omit to use Bearer token auth (recommended)
```

Running the tests:
```bash
# Run all integration tests (Cloud)
python -m unittest discover -s integration_tests

# Run Data Center-specific tests
python -m unittest integration_tests.test_api_datacenter

# Run Cloud-specific tests
python -m unittest integration_tests.test_api
```

**Note**: When contributing features or bug fixes, ensure you test both Cloud (v2 API) and Data Center (v1 API) when possible. The `test_api.py` suite tests Cloud/v2, while `test_api_datacenter.py` tests Data Center/v1.

### Running static code checks

Verify that all code you have added passes static code checks. Depending on your OS, there is a script for you to use. If using Windows, run `check.bat`, otherwise run `./check.sh`.

### Generating documentation

Verify that newly contributed classes, data-classes and functions have a doc-string, including public members, parameters, return values and exceptions raised. You can generate human-readable Markdown documentation with [markdown_doc](https://github.com/hunyadi/markdown_doc):

```
python -m markdown_doc -d md2conf
```
