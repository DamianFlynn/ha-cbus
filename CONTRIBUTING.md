# Contributing to ha-cbus

## Prerequisites

- Python 3.12+ (3.13 also tested in CI)
- Git
- A C-Bus PCI or CNI is **not** required for development — the library
  includes offline command builders and the test suite is fully mocked.

## Quick start

```bash
# Clone and enter the repo
git clone https://github.com/DamianFlynn/ha-cbus.git
cd ha-cbus

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the library in editable mode with dev dependencies
pip install -e ".[dev]"

# (Optional) Install HA test framework for integration tests
pip install pytest-homeassistant-custom-component
```

## Tooling overview

| Tool | Purpose | Config |
|---|---|---|
| [ruff](https://docs.astral.sh/ruff/) | Linting + formatting (replaces flake8, isort, black) | `pyproject.toml` `[tool.ruff]` |
| [mypy](https://mypy-lang.org/) | Static type checking (strict mode) | `pyproject.toml` `[tool.mypy]` |
| [pytest](https://docs.pytest.org/) | Test runner with async and coverage support | `pyproject.toml` `[tool.pytest]` |
| [pytest-cov](https://pytest-cov.readthedocs.io/) | Coverage reporting | via `--cov` flag |
| [pytest-homeassistant-custom-component](https://github.com/MatthewFlamworthy/pytest-homeassistant-custom-component) | HA integration test fixtures (`hass`, `enable_custom_integrations`) | optional install |

### Ruff rule set

The project enables these [ruff rule categories](https://docs.astral.sh/ruff/rules/):

```toml
select = ["E", "F", "I", "UP", "B", "SIM", "TCH", "RUF"]
```

| Rule | What it catches |
|---|---|
| `E` / `F` | pycodestyle errors + pyflakes |
| `I` | isort import ordering |
| `UP` | pyupgrade (modern Python syntax) |
| `B` | flake8-bugbear (common pitfalls) |
| `SIM` | flake8-simplify (unnecessary complexity) |
| `TCH` | flake8-type-checking (move imports to `TYPE_CHECKING`) |
| `RUF` | Ruff-specific rules (unused noqa, etc.) |

## Development workflow

```mermaid
graph TD
  A[Create feature branch] --> B[Write code]
  B --> C[Run ruff check + format]
  C --> D{Lint clean?}
  D -- No --> B
  D -- Yes --> E[Run mypy]
  E --> F{Types clean?}
  F -- No --> B
  F -- Yes --> G[Run pytest]
  G --> H{Tests pass?}
  H -- No --> B
  H -- Yes --> I[Commit + push]
  I --> J[CI runs automatically]
  J --> K{CI green?}
  K -- No --> B
  K -- Yes --> L[Open / update PR]
```

### 1. Branch

Always work in a feature branch:

```bash
git checkout -b feat/my-feature
```

### 2. Lint and format

```bash
# Check for lint errors
ruff check pycbus/ tests/ custom_components/

# Auto-fix what ruff can
ruff check --fix pycbus/ tests/ custom_components/

# Check formatting (dry run)
ruff format --check pycbus/ tests/ custom_components/

# Apply formatting
ruff format pycbus/ tests/ custom_components/
```

### 3. Type check

```bash
mypy pycbus/
```

Mypy runs in strict mode — all functions need type annotations and
third-party imports must be typed or stubbed.

### 4. Test

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=pycbus --cov-report=term-missing

# Run only library tests (no HA dependency)
python -m pytest tests/lib/ -v

# Run only CLI tests
python -m pytest tests/cli/ -v

# Run only integration tests (requires pytest-homeassistant-custom-component)
python -m pytest tests/integration/ -v
```

### 5. Use the CLI

The standalone CLI (`python -m cli`) can control a live C-Bus network:

```bash
# Turn on a light
python -m cli light on --host 192.168.1.50 --group 1

# Monitor all traffic
python -m cli monitor --host 192.168.1.50

# Query group status
python -m cli status --host 192.168.1.50
```

The pycbus package CLI works without hardware for offline building:

```bash
# Build a Lighting ON frame
python -c "from pycbus.cli import main; main(['build', 'on', '--group', '1'])"

# Compute a checksum
python -c "from pycbus.cli import main; main(['checksum', '05', '38', '00', '79', '01', 'FF'])"
```

## CI pipelines

Two GitHub Actions workflows run automatically on push/PR:

```mermaid
graph LR
  subgraph "CI: pycbus library"
    direction TB
    L1[ruff check] --> L2[ruff format --check]
    L2 --> L3[mypy --strict]
    L3 --> L4["pytest 3.12 + coverage"]
    L3 --> L5["pytest 3.13"]
  end

  subgraph "CI: HA integration"
    direction TB
    I1[ruff check] --> I2[ruff format --check]
    I2 --> I3[manifest.json validation]
    I3 --> I4["pytest config flow"]
  end
```

### CI: pycbus library (`ci-library.yml`)

Triggered when `pycbus/`, `tests/`, or `pyproject.toml` change.

| Job | Steps |
|---|---|
| **Lint & type-check** | `ruff check` -> `ruff format --check` -> `mypy --strict` |
| **Test (3.12)** | `pytest tests/lib/ tests/cli/ --cov` + upload coverage artifact |
| **Test (3.13)** | `pytest tests/lib/ tests/cli/` |

### CI: HA integration (`ci-integration.yml`)

Triggered when `custom_components/`, `tests/integration/`, or
`tests/conftest.py` change.

| Job | Steps |
|---|---|
| **Validate** | `ruff check` -> `ruff format --check` -> manifest.json schema check |
| **Test** | `pytest tests/integration/` with `pytest-homeassistant-custom-component` |

## Versioning

| Component | Scheme | Current | Where |
|---|---|---|---|
| `pycbus` library | [SemVer](https://semver.org/) | `0.1.0` | `pyproject.toml` `version` |
| HA integration | [CalVer](https://calver.org/) `YYYY.M.PATCH` | `2026.4.0` | `manifest.json` `version` |

- Bump `pycbus` version for library changes (breaking → major, feature → minor, fix → patch).
- Bump the integration version to match the current HA release cycle.

## Test structure

```
tests/
├── conftest.py                 # Root fixtures (shared)
├── lib/                        # Library-only tests (150 tests)
│   ├── conftest.py             # lib-specific fixtures
│   ├── test_checksum.py        #   4 — checksum algorithm
│   ├── test_commands.py        #  49 — SAL builders, parsers, measurement
│   ├── test_constants.py       #  28 — enums, bitmasks, spec compliance
│   ├── test_model.py           #  14 — dataclass validation
│   ├── test_protocol.py        #  23 — protocol state machine + init
│   └── test_transport.py       #  32 — TCP + serial + CRLF edge cases
├── cli/                        # CLI tests (21 tests)
│   └── test_cli.py             #  21 — build/checksum sub-commands
└── integration/                # HA integration tests (65 tests)
    ├── conftest.py             # HA fixtures (hass, enable_custom_integrations)
    ├── test_config_flow.py     #   8 — config flow
    ├── test_coordinator.py     #  22 — coordinator state + SAL dispatch
    ├── test_light.py           #  16 — light entity
    ├── test_switch.py          #  10 — switch entity
    └── test_event.py           #   9 — event entity
```

**Total: 236 tests** (150 library + 21 CLI + 65 integration)

Library and CLI tests have no HA dependency — they work with just
`pip install -e ".[dev]"`. Integration tests require
`pytest-homeassistant-custom-component`.

## Code style guidelines

- **Line length**: 88 characters (ruff default)
- **Imports**: sorted by ruff (`I` rules), type-only imports in `TYPE_CHECKING` blocks (`TCH` rules)
- **Docstrings**: every public module, class, and function gets a docstring
- **Type annotations**: all function signatures must be fully typed (mypy strict)
- **ASCII only in source**: no smart quotes, em-dashes, or non-ASCII in strings (ruff `RUF001`/`RUF002`)
