# Contributing to Instagram & TikTok Scraper

Thank you for your interest in contributing! This project is part of an academic
research effort, and we welcome contributions that improve code quality,
documentation, and support for new platforms.

## How to Contribute

1. **Fork** the repository and create a new branch from `main`.
2. **Install** the development environment:
   ```bash
   python -m venv venv
   source venv/bin/activate    # macOS / Linux
   pip install -r requirements.txt
   playwright install chromium
   ```
3. **Run the tests** before and after your changes:
   ```bash
   python -m pytest tests/ -v
   ```
4. **Submit a Pull Request** describing what you changed and why.

## Reporting Issues

Open a GitHub Issue with:

- A clear description of the problem or enhancement.
- Steps to reproduce (if applicable).
- Your Python version and operating system.

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Use type hints where practical.
- Keep functions focused and well-documented.

## Tests

All new functionality should include corresponding tests in `tests/`.
Run the full suite with `python -m pytest tests/ -v` and ensure **all tests
pass** before submitting a PR.

## Code of Conduct

Be respectful and constructive. This is an academic project — focus on
collaborative improvement and evidence-based discussion.

## License

By contributing you agree that your contributions will be licensed under the
[GNU General Public License v3.0](LICENSE).
