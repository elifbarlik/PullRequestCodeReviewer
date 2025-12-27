# PR Code Reviewer

An AI-powered code review tool that automatically analyzes pull requests opened on GitHub. It finds bugs in written code, detects security issues, and provides development suggestions.

## Problem

Manual code review is time-consuming and can create consistency issues. In large projects, it becomes difficult to review every pull request in detail, and some bugs may be missed. There is a need for an automated solution, especially for critical issues such as security vulnerabilities and performance problems.

## Solution

PR Code Reviewer automatically analyzes pull requests using AI technology. It can be used in three different ways:

1. **Local Review**: Send code diff directly to the system for analysis
2. **GitHub Integration**: Automatically fetch pull request from GitHub, review it, and post results as comments
3. **Webhook Support**: System automatically activates when a PR is opened or updated and performs evaluation

## Key Features

- **Multiple Analysis Types**: Short summary, bug detection, security review, performance analysis
- **Two-Stage Analysis**: Quick summary and detailed review stages
- **Robust JSON Parser**: Reliable JSON parsing with 5 different fallback strategies
- **Token Management**: Manage token limits with automatic diff truncation
- **GitHub Webhook Support**: Automatic PR event handling
- **Parser Statistics**: Success rate tracking and monitoring

## Tech Stack

- **Framework**: FastAPI
- **Server**: Uvicorn
- **AI Model**: Google Gemini (google-generativeai)
- **GitHub Integration**: PyGithub
- **Testing**: Pytest
- **Containerization**: Docker, Docker Compose
- **Language**: Python 3.11

## Architecture Notes

The project consists of three main components:

1. **reviewer.py**: Performs analysis in two stages
   - Stage 1: Quick summary generation (low token usage)
   - Stage 2: Detailed review (bug detection, security, performance)

2. **json_parser.py**: Parses AI responses using five different methods
   - Direct JSON parse
   - Markdown code block extraction
   - Common error fixing (single quotes, unquoted keys, trailing commas)
   - Regex extraction
   - Fallback template

3. **github_client.py**: Communicates with GitHub API to fetch pull request information and is responsible for writing comments

### Analysis Types

The system performs code review from four different perspectives:
- **Short Summary**: Change summary and importance level
- **Bug Detection**: Potential bugs and logic issues in written code
- **Security Review**: Security vulnerabilities and data protection deficiencies
- **Performance Analysis**: Performance issues and improvement suggestions

## Getting Started

### Option 1: Docker Compose (Recommended)

The easiest and most consistent way to run:

```bash
# Create .env file
GITHUB_TOKEN=your_github_token
GEMINI_API_KEY=your_gemini_api_key
GITHUB_WEBHOOK_SECRET=your_webhook_secret  # (optional)

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

The system will run at `http://localhost:8000`.

### Option 2: Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file
GITHUB_TOKEN=your_github_token
GEMINI_API_KEY=your_gemini_api_key
GITHUB_WEBHOOK_SECRET=your_webhook_secret  # (optional)

# Start the application
uvicorn app.main:app --reload
```

The system will run at `http://localhost:8000`.

## Environment Variables

You need to define the following environment variables in the `.env` file or system environment:

- `GITHUB_TOKEN`: GitHub Personal Access Token (required to read PRs and write comments)
- `GEMINI_API_KEY`: Google Gemini API key (required for AI analysis)
- `GITHUB_WEBHOOK_SECRET`: Used for GitHub webhook signature verification (optional, but recommended for production)

## API Endpoints

**Health Check:**
```bash
curl http://localhost:8000/health
```

**Local Diff Analysis:**
```bash
curl -X POST http://localhost:8000/local-review \
  -H "Content-Type: application/json" \
  -d '{
    "diff_text": "--- a/file.py\n+++ b/file.py\n...",
    "review_types": ["short_summary", "bug_detection"]
  }'
```

**GitHub PR Review:**
```bash
curl -X POST http://localhost:8000/github-review \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "username",
    "repo": "repo-name",
    "pr_number": 1
  }'
```

**Statistics:**
```bash
curl http://localhost:8000/stats
```

## Testing

```bash
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_local_review.py -v

# Coverage
pytest tests/ --cov=app --cov-report=html
```

The system has 24 tests and all pass successfully. These cover schema validation, parser robustness, and different code scenarios.

## GitHub Webhook Setup

Repository settings → Webhooks → Add webhook
- **Payload URL**: `https://your-domain/webhook`
- **Content type**: `application/json`
- **Events**: Pull requests
- **Secret**: Your `GITHUB_WEBHOOK_SECRET` value

After the webhook is set up, the system will automatically analyze when a PR is opened or updated and add the results as comments to the PR.
