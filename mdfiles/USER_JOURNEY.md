# Smart DevTool: A Developer's Journey

This guide walks you through a complete, step-by-step experience of using **Smart DevTool** in a real-world scenario. Imagine you are building a new Python backend that needs to talk to the GitHub API, needs to resolve some messy dependencies, and needs to be deployed via Docker.

Here is how you would use every single feature of Smart DevTool to build this project in record time.

---

## 🛠️ Step 1: Installation

First, we need to install Smart DevTool into our environment.

**Command:**
```bash
pip install -e .
```

**What you see:**
You'll see pip installing the package along with its dependencies like `typer`, `rich`, and `pydantic`.

**To verify it worked:**
```bash
smartdevtool --help
```

You'll see a beautifully formatted terminal interface (thanks to the `rich` library) listing the available commands:
* `wrap`: Generate API SDK wrappers
* `deps`: Resolve and install dependencies
* `docker`: Generate and sync Docker containers

---

## 🔌 Step 2: Feature 1 - The API Wrapper Generator

Your full-stack app needs to fetch user data from GitHub. Instead of writing `requests.get(...)` everywhere and guessing the JSON structure, let's generate a full SDK.

We have a sample cURL command that hits the GitHub API.

**Command:**
```bash
smartdevtool wrap curl "curl -H 'Authorization: Bearer my_token' https://api.github.com/users/octocat" --output my_github_sdk.py --no-llm
```
*(Note: We use `--no-llm` so it runs completely offline using the deterministic parsers).*

**What the tool does:**
1. Parses the cURL string.
2. Detects the `Authorization: Bearer` header and marks it as needing a secret token.
3. Maps the URL `https://api.github.com/users/{username}`.
4. Generates a typed Python SDK using a Jinja2 template.

**What you see in the terminal:**
```
[+] Parsed 1 endpoint from cURL command.
[+] Authentication detected: Bearer token (Env var: GITHUB_API_KEY expected)
[+] Generated SDK saved to: my_github_sdk.py
[+] AST Syntax Check Passed.
```

**The Output File (`my_github_sdk.py`):**
If you open the generated file, you will find a fully typed Python class:
```python
import httpx
import os

class GitHubAPIClient:
    def __init__(self, token: str = None):
        self.token = token or os.environ.get("GITHUB_API_KEY")
        # ... sets up async httpx client with retries ...

    async def get_users_octocat(self):
        # Automatically generated method!
        response = await self.client.get("https://api.github.com/users/octocat")
        response.raise_for_status()
        return response.json()
```
*Now you can import `GitHubAPIClient` directly into your web app!*

---

## 📦 Step 3: Feature 2 - Dependency & Conflict Resolver

Now you start writing your backend. You create an `app.py` and write:
```python
import fastapi
import uvicorn
import httpx
from my_github_sdk import GitHubAPIClient
```

Instead of manually figuring out what versions to put in a `requirements.txt`, let Smart DevTool do it.

### Sub-command: Scan
Let's see what the tool detects from your code.

**Command:**
```bash
smartdevtool deps scan
```

**What you see:**
```
Scanning project directory...
Found 4 import statements.
Mapping to PyPI packages...
  fastapi -> fastapi
  uvicorn -> uvicorn
  httpx   -> httpx
  my_github_sdk -> [LOCAL MODULE IGNORED]
```

### Sub-command: Resolve & Install
Now, let's lock these dependencies and install them.

**Command:**
```bash
smartdevtool deps resolve --install --no-llm
```

**What the tool does:**
1. Takes the scanned PyPI packages.
2. Runs `pip-compile` to figure out the exact sub-dependencies and version compatibility.
3. Generates a reproducible `requirements.lock` file.
4. Because `--install` was passed, it safely installs them into your environment.

**What you see in the terminal:**
```
[+] Generating requirements.lock...
[+] Lockfile created successfully. (34 packages locked)
[+] Installing dependencies...
[+] Installation complete!
```

---

## 🐳 Step 4: Feature 3 - Docker Generator & Live Sync

Your app is working locally. It's time to containerize it for production.

### Sub-command: Generate Dockerfile

**Command:**
```bash
smartdevtool docker generate --port 8000 --no-llm
```

**What the tool does:**
It looks at your `requirements.lock` and generates an optimized Dockerfile. It knows to copy the lockfile *first* to take advantage of Docker's layer caching, meaning rebuilds will be lightning fast.

**What you see in the terminal:**
```
[+] Detected Python 3.10
[+] Generated optimized Dockerfile
[+] Generated .dockerignore
```

**The Output File (`Dockerfile`):**
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]
```

### Sub-command: Live Sync
During development, you don't want to manually run `docker build` every time you change a line of code. 

**Command:**
```bash
smartdevtool docker sync --tag my-fullstack-app --no-llm
```

**What the tool does:**
1. Immediately runs a `docker build -t my-fullstack-app .`
2. Starts a file watcher (`watchdog`) on your project folder.
3. Calculates SHA-256 hashes of your code.
4. If you hit `CTRL+S` in your editor to save `app.py`, the tool detects the drift and intelligently triggers a fast rebuild in the background.

**What you see in the terminal:**
```
[+] Initial Docker build successful. Image: my-fullstack-app:latest
[*] Watching directory for changes... (Press Ctrl+C to stop)

(When you save a file)
[~] Detected change in app.py
[~] Rebuilding container...
[+] Build successful in 1.2s!
```

---

## 🎉 Summary of Your Journey

In just a few minutes, you used Smart DevTool to:
1. **Wrap**: Turn a random cURL command into a production-ready Python SDK.
2. **Deps**: Magically scan your code, map imports to PyPI, and lock down secure dependency versions.
3. **Docker**: Instantly generate an optimized Dockerfile and set up a hot-reloading background sync.

You built a robust, containerized application without writing a single line of boilerplate!



