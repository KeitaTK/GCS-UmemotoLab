# GCS Development Guide

## 1. Repository Structure
- `app/`: application source code
- `config/`: runtime configuration
- `docs/`: specification and design docs
- `third_party/`: generated MAVLink libraries (custom XML output)

## 2. Python Environment
- Python 3.10+ recommended
- Use a dedicated virtual environment

## 3. Dependencies (MVP)
- `pymavlink`
- `PySide6`
- `pyyaml`

## 4. Configuration
- Copy `config/gcs.yml` and edit endpoints and system IDs

## 5. Running (planned)
- `python -m app.main`

## 6. Code Style and Naming
### 6.1 Naming
- Modules: `snake_case`
- Classes: `CapWords`
- Functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

### 6.2 Types
- Use type hints for public methods
- Use `dataclasses` for model objects

### 6.3 Logging
- Use `logging` module
- No `print` in production code

### 6.4 Error Policy
- Raise custom exceptions in `app/errors.py` for predictable failures
- Log and continue for telemetry decoding errors

## 7. GitHub Copilot Usage
- Use Copilot for boilerplate, but verify MAVLink message fields
- Require tests or simulation for command sending

## 8. References
- https://docs.github.com/en/issues/tracking-your-work-with-issues/creating-an-issue
