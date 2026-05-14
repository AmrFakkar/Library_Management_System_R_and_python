# Task 4 — API Testing (pytest)

## Responsible For
- Complete pytest test suite for all requirements
- conftest.py with all shared fixtures and in-memory SQLite DB
- Auth tests, Book CRUD tests, Borrow logic tests, Edge case tests

## Running Tests
```bash
pytest                                          # all tests
pytest --cov=app --cov-report=term-missing      # with coverage
pytest --cov=app --cov-report=html              # HTML coverage report
pytest tests/test_borrows.py -v                 # single file
pytest -v --durations=10                        # show slowest tests
```
