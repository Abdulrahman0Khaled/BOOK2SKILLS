# Contributing to Book2Skills 🚀

Thank you for your interest in contributing to **Book2Skills**! We welcome contributions from developers, researchers, and open-source enthusiasts of all skill levels.

This document outlines the guidelines and workflow for contributing to the project.

---

## 📋 Table of Contents

- [Code of Conduct](#-code-of-conduct)
- [How Can I Contribute?](#-how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features](#suggesting-features)
  - [Submitting Pull Requests](#submitting-pull-requests)
- [Development Setup](#-development-setup)
- [Code Quality & Testing](#-code-quality--testing)
  - [Code Formatting & Linting](#code-formatting--linting)
  - [Type Checking](#type-checking)
  - [Running Tests](#running-tests)
- [Commit Message Guidelines](#-commit-message-guidelines)
- [Pull Request Checklist](#-pull-request-checklist)

---

## 📜 Code of Conduct

We aim to foster a welcoming, inclusive, and respectful community. Please ensure all interactions—whether in issues, pull requests, or discussions—remain professional and encouraging.

---

## 💡 How Can I Contribute?

### Reporting Bugs

Before creating a new bug report, please check existing [GitHub Issues](https://github.com/Abdulrahman0Khaled/BOOK2SKILLS/issues) to avoid duplicates.

When filing a bug report, please include:
1. **Clear Summary**: A descriptive title and short overview.
2. **Steps to Reproduce**: Detailed steps to consistently reproduce the issue.
3. **Expected vs. Actual Behavior**: What you expected to happen vs. what actually occurred.
4. **Environment**: Python version, OS, LLM provider (`B2S_LLM__PROVIDER`), and model used.
5. **Logs & Stack Trace**: Full log output (wrap in triple backticks \`\`\` ).

### Suggesting Features

We welcome feature requests! Please submit an issue detailing:
- The problem your feature solves or the capability it adds.
- Proposed API / CLI interface changes (if applicable).
- Additional context or example use cases.

---

## 🛠️ Development Setup

Follow these steps to set up your local development environment:

### 1. Fork & Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/BOOK2SKILLS.git
cd BOOK2SKILLS
```

### 2. Create Virtual Environment
```bash
python -m venv .venv

# On Linux/macOS
source .venv/bin/activate

# On Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies in Editable Mode
```bash
pip install -e ".[dev,all]"
```

### 4. Install Pre-Commit Hooks
```bash
pre-commit install
```

---

## 🧪 Code Quality & Testing

We enforce strict code quality standards to ensure consistency and reliability.

### Code Formatting & Linting

We use [Ruff](https://github.com/astral-sh/ruff) for lightning-fast linting and formatting.

```bash
# Check code for linting issues
ruff check .

# Automatically fix linting issues
ruff check --fix .

# Format code
ruff format .
```

### Type Checking

We use [MyPy](https://github.com/python/mypy) for static type safety.

```bash
mypy src/
```

### Running Tests

We use [pytest](https://docs.pytest.org/) for automated testing.

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run end-to-end tests
pytest tests/e2e/

# Run all tests with coverage report
pytest --cov=src/book_to_skills
```

---

## 📝 Commit Message Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/) format for clear, readable git histories:

```text
<type>(<scope>): <short description>
```

### Types:
- `feat`: A new feature or capability.
- `fix`: A bug fix.
- `docs`: Documentation changes (`README.md`, `docs/`, `mkdocs.yml`).
- `style`: Formatting, missing semi-colons, etc. (no code change).
- `refactor`: Code refactoring without changing public behavior.
- `test`: Adding missing tests or refactoring existing tests.
- `chore`: Maintenance tasks, dependency updates, CI/CD configuration.

### Examples:
```text
feat(pipeline): add support for EPUB book extraction
fix(llm): resolve schema validation fallback error in Ollama provider
docs(readme): update quickstart commands and architecture diagram
```

---

## ✅ Pull Request Checklist

Before submitting your PR, verify the following:

- [ ] My code follows the project's style guidelines (`ruff check .` passes clean).
- [ ] Static type checking passes (`mypy src/` has 0 errors).
- [ ] All unit and integration tests pass (`pytest`).
- [ ] I have added tests for new features or bug fixes.
- [ ] I have updated relevant documentation (`docs/` or `README.md`).
- [ ] My commits follow the Conventional Commits format.

---

Thank you for helping make **Book2Skills** better for everyone! 🚀
