# Contributing to better-code-review-graph

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

### Prerequisites

- **Python 3.13** (required -- `requires-python = "==3.13.*"`)
- [uv](https://docs.astral.sh/uv/)
- Git

### Setup Development Environment

1. **Fork the repository** and clone your fork

```bash
git clone https://github.com/YOUR_USERNAME/better-code-review-graph
cd better-code-review-graph
```

2. **Install dependencies**

```bash
uv sync --group dev
```

3. **Run checks**

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

## Development Workflow

### Making Changes

1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Run checks: `uv run ruff check --fix . && uv run ruff format .`
4. Run tests: `uv run pytest`
5. Commit your changes (see [Commit Convention](#commit-convention))
6. Push to your fork: `git push origin feature/your-feature-name`
7. Open a Pull Request

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>[optional scope]: <description>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

### Examples

```text
feat: add Ruby language support
fix: resolve multi-word search AND logic edge case
docs: update embedding configuration guide
feat!: refactor tools to 3-tier architecture
```

## Release Process

Releases are automated using **python-semantic-release (PSR) v10**. We strictly follow the **Conventional Commits** specification to determine version bumps and generate changelogs automatically.

### How to Release

1. Create a Pull Request with your changes.
2. Ensure your commit messages follow the convention above.
3. Merge the PR to `main`.
4. A maintainer triggers the CD workflow manually via **workflow_dispatch**:
   - Choose `beta` or `stable` release type.
   - PSR analyzes commits since the last release.
   - Bumps version, updates `CHANGELOG.md`, creates a tag.
   - Publishes to PyPI.
   - Creates a GitHub Release.
   - Builds and pushes Docker images.

You do **not** need to create manual tags or changelog entries.

## Pull Request Guidelines

- Keep PRs focused on a single feature or fix
- Update documentation if needed
- Add tests for new functionality
- Ensure all checks pass

### PR Checklist

Before submitting your PR, ensure:

- [ ] Code follows Python best practices
- [ ] All tests pass (`uv run pytest`)
- [ ] Linting passes (`uv run ruff check .`)
- [ ] Formatting is correct (`uv run ruff format --check .`)
- [ ] Commit messages follow **Conventional Commits**
- [ ] Documentation updated (if needed)
- [ ] Coverage stays above 95%

## Code Style

This project uses **Ruff** for formatting and linting.

```bash
uv run ruff check .       # Check for issues
uv run ruff check --fix . # Auto-fix issues
uv run ruff format .      # Format code
```

## Testing

```bash
uv run pytest              # Run all tests
uv run pytest -v           # Verbose output
uv run pytest --tb=short   # Short tracebacks
```

## Questions?

Feel free to open an issue for:

- Bug reports
- Feature requests
- Questions about the codebase

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
