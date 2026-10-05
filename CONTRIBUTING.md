# Contributing

Keep this a small local Python project. Put reusable logic in `tutor/` and keep UI events in `app.py`.

Use Python 3.12 and install `requirements-dev.txt` in a virtual environment. From the project root, run:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use synthetic credentials, fake pages, and mocked model/search transports. They do not need a real `api_key.txt`, a running Streamlit server, or paid API calls. Keep new routine tests deterministic. A test double is for development, not a selectable application demo mode.

For a change, describe the behavior, its reason, and relevant checks. Add meaningful tests when changing a contract, budget guard, scoring rule, or network boundary. Keep the README current. Do not claim that mocked checks establish live model quality or that generated solution code was executed.

Never include credentials, private answers, or raw provider errors in issues, pull requests, screenshots, fixtures, or PDFs. `api_key.example.txt` has empty fields for setup; real credentials belong in ignored local files or runtime environment variables. The application does not automatically load `.env` files.

The [test workflow](.github/workflows/tests.yml) runs on Windows with Python 3.12 and needs no provider secrets. Dependency installation still uses the network. Its setup follows [GitHub's Python workflow guide](https://docs.github.com/en/actions/tutorials/build-and-test-code/python), using the official [checkout](https://github.com/actions/checkout) and [setup-python](https://github.com/actions/setup-python) actions.
