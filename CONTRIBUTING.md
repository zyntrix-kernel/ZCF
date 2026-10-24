# Contributing to Zyntrix Compatibility Fabric (ZCF)

Thank you for your interest in contributing to ZCF!

---

## 1. Development Principles

1. **Python 3.10+ Standard Library First:** Core modules must minimize external dependencies to preserve universal Linux distribution portability.
2. **Strict Typing:** All new code must include complete type annotations (`typing`, `dataclasses`, `enum`).
3. **Automated Tests Mandatory:** Every PR must include unit tests covering both positive and negative/failure paths.
4. **Evidence Over Conjecture:** When contributing compatibility data, always attach reproducible logs, hashes, and environment details.

---

## 2. Running Tests

```bash
# Run the complete test suite
python -m unittest discover -s tests -v

# Run with coverage (if coverage is installed)
python -m unittest tests/test_*.py
```

---

## 3. Pull Request Guidelines

1. Fork the repository and create a feature branch (`feature/new-runtime-adapter`).
2. Implement code, tests, and documentation.
3. Verify all tests pass locally.
4. Submit the Pull Request with a clear description referencing any relevant issues.
