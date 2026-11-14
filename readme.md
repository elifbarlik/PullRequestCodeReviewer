# SecPR-TR

**An AI-assisted GitHub Pull Request reviewer with a security-first workflow and Turkish-language feedback.**

SecPR-TR is a GitHub App that reviews pull requests, scans changed code with Semgrep, and uses Google's Gemini models to summarize changes and explain security findings. Review feedback is posted back to GitHub, including inline comments when a finding can be mapped to an added line.

> **Project status:** Portfolio project. The hosted demo is not guaranteed to remain available. Run the application locally to explore it. SecPR-TR is an assistive tool, not a substitute for human code review or a professional security audit.

## What it does

- **GitHub App integration:** Receives pull-request and installation webhooks and uses GitHub App JWTs with installation-scoped access tokens.
- **Security scanning:** Runs Semgrep against supported changed files and filters findings to lines added or changed in the pull request.
- **AI-assisted explanations:** Uses Gemini for pull-request summaries and Turkish explanations of detected security findings. Semgrep is the detection layer; Gemini explains findings rather than acting as the sole vulnerability detector.
- **Inline feedback:** Posts findings as inline pull-request review comments where GitHub accepts the diff position. Findings that cannot be placed inline are included in the summary review.
- **Dashboard and persistence:** Includes a dashboard with review history and detail views, GitHub OAuth sign-in, and PostgreSQL-backed installation/review metadata.
- **Security controls:** Includes webhook HMAC-SHA256 verification, OAuth state validation, signed HttpOnly session cookies, installation-scoped access, and request rate limiting.
- **Operational visibility and cost controls:** Includes health and metrics endpoints, structured logging, optional Sentry integration, bounded LLM caching, and output-token limits.

## How a review works

```text
GitHub Pull Request event
        |
        v
FastAPI webhook endpoint
        |
        +--> Verify webhook signature and delivery metadata
        |
        v
GitHub App installation token
        |
        +-------------------------+
        |                         |
        v                         v
   Semgrep scan             Gemini summary
   (changed code)           (PR context)
        |                         |
        +------------+------------+
                     |
                     v
        Gemini explains Semgrep findings
                     |
                     v
     GitHub review: summary + inline comments
                     |
                     v
       PostgreSQL metadata (when configured)
```

The security pipeline deliberately separates **detection** from **explanation**. If Semgrep is unavailable or a scan cannot be completed, the application reports that the scan was unavailable instead of presenting the result as a clean security scan.

## Technology stack

| Area | Technologies |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| GitHub integration | GitHub Apps, Webhooks, GitHub REST API, PyJWT |
| Security analysis | Semgrep |
| AI | Google Gemini API (`google-genai`) |
| Data layer | PostgreSQL, SQLAlchemy, Alembic |
| Dashboard | HTML, CSS, JavaScript |
| Authentication | GitHub OAuth, signed session cookies |
| Operations | Docker, Docker Compose, structured logging, Sentry |
| Testing | pytest, SQLite in-memory tests, Semgrep benchmark suite |

## Run locally

### Requirements

- Docker and Docker Compose
- A GitHub App for webhook and repository access
- A Google Gemini API key

### 1. Configure environment

```bash
cp .env.example .env
```

Fill in the required values in `.env`:

- `GEMINI_API_KEY`
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY_PATH` or `GITHUB_APP_PRIVATE_KEY`
- `GITHUB_WEBHOOK_SECRET`
- `ADMIN_SECRET`

The Docker Compose setup provides PostgreSQL. The `GITHUB_OAUTH_*` variables are needed when you want to use the authenticated dashboard. Set `GITHUB_OAUTH_REDIRECT_URI` to your registered callback URL when it differs from the automatically derived `/auth/github/callback` URL.

### 2. Start the application

```bash
docker compose up --build -d
docker compose logs -f pr-reviewer
```

The application is available at `http://localhost:8000`.

### 3. Configure GitHub webhooks

For a deployed or tunneled local instance, set the GitHub App webhook URL to:

```text
https://<your-host>/webhook
```

Enable the `Pull request`, `Installation`, and `Installation repositories` events. Grant the app the minimum permissions documented in your GitHub App configuration: Pull requests (read/write) and Contents (read-only), plus GitHub's required Metadata permission.

For local webhook testing, the repository includes `scripts/smee_proxy.py`.

### 4. Stop the application

```bash
docker compose down
```

Add `-v` only when you intentionally want to remove the local PostgreSQL volume and its data.

## Useful endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Application and dependency health |
| `GET /stats` | Parser and usage statistics |
| `POST /webhook` | GitHub App webhook receiver |
| `POST /local-review` | Submit a diff for a local review |
| `GET /dashboard` | Review dashboard |
| `GET /dashboard/api/summary` | Dashboard summary |
| `GET /dashboard/api/reviews` | Review history |
| `GET /installations/{id}/settings` | Read installation scan settings |
| `PUT /installations/{id}/settings` | Update installation scan settings |

The `/local-review` endpoint accepts a diff directly and does not run the full Semgrep file-content workflow. Use the GitHub App webhook path when evaluating the normal changed-file security scan.

## Tests

Run the automated test suite:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests that require external credentials, network access, or an installed Semgrep CLI may be skipped according to the test markers and environment. A successful local test run does not establish that the hosted production deployment is healthy.

## Security benchmark

The repository contains a small, reproducible benchmark for the deterministic Semgrep scanning layer:

```bash
python scripts/run_benchmark.py
```

The last committed result covers 28 curated scenarios (20 vulnerable and 8 clean): **52.4% recall, 100.0% precision, and 68.8% F1**. These figures apply only to the benchmark cases and Semgrep detection layer; they are not a claim of real-world vulnerability-detection accuracy. See [benchmark methodology](benchmarks/README.md) and [recorded results](benchmarks/RESULTS.md).

## Known limitations

- Semgrep coverage depends on the configured community rulesets and supported file types. A missing finding does not prove that code is secure.
- The benchmark is intentionally limited and does not represent the distribution of vulnerabilities in production repositories.
- Gemini explanations may be incomplete or incorrect and must be reviewed by a developer.
- PR analysis uses the application's background-task and persistence design; it is not a guarantee of durable, exactly-once job execution across every infrastructure failure.
- A live hosted endpoint and third-party API availability are not guaranteed.

## Project documentation

- [Privacy policy](PRIVACY.md)
- [Support and issue reporting](SUPPORT.md)
- [MIT License](LICENSE)
- [Benchmark methodology](benchmarks/README.md)
- [Benchmark results](benchmarks/RESULTS.md)

---

Built as an individual software engineering project.
