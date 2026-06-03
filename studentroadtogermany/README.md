# Student Road to Germany

Myanmar → Deutschland consultation service — part of the [AlexSnow School Business](../) portfolio.

## Running locally

```bash
# Static site (from repo root)
python3 -m http.server 3001

# Contact form API — stores submissions in SQLite (dev only)
python3 studentroadtogermany/api.py
```

Open `http://localhost:3001/studentroadtogermany/` in your browser.

## Contact form — how submissions are stored

In **production**, form submissions are stored via GitHub Actions. When a visitor submits the contact form the browser POSTs directly to the GitHub repository dispatch API. A workflow runs, appends one row to `submissions.csv`, and commits the file back to the repository.

```mermaid
sequenceDiagram
    actor Visitor
    participant JS as script.js<br/>(browser)
    participant API as GitHub API
    participant Actions as GitHub Actions
    participant Repo as submissions.csv<br/>(main branch)

    Visitor->>JS: Submit contact form
    JS->>API: POST /repos/.../dispatches<br/>event_type: contact-form
    API-->>JS: 204 No Content
    JS-->>Visitor: Show success message

    Note over API,Actions: Asynchronous — visitor does not wait for this
    API->>Actions: Trigger store-submission workflow
    Actions->>Repo: git checkout main
    Actions->>Actions: store_submission.py<br/>appends one CSV row
    Actions->>Repo: git commit + push
```

> The visitor sees the success message as soon as GitHub acknowledges the dispatch (204). The CSV is written asynchronously — typically within 30–60 seconds.

In **local development**, `api.py` handles the same endpoint and writes to `submissions.db` (SQLite, gitignored).

## GitHub Actions one-time setup

### 1. Create a fine-grained Personal Access Token

Go to: `github.com/settings/personal-access-tokens/new`

| Field | Value |
|---|---|
| Resource owner | `alexsnowschool-business` |
| Repository access | Only `alexsnowschool-business.github.io` |
| Permissions → Contents | Read and write |

Copy the token and paste it into `script.js`:

```js
const GITHUB_TOKEN = 'github_pat_your_token_here';
```

### 2. Push to GitHub

The workflow at `.github/workflows/store-submission.yml` takes effect on the next push. It only runs on `repository_dispatch` events with type `contact-form` — regular git pushes skip it entirely.

No additional secrets or variables are needed. The workflow uses the built-in `GITHUB_TOKEN` (with `contents: write` permission declared in the workflow file) to push the CSV back to the repo.

## Reading submissions

`submissions.csv` in this directory is appended to by every form submission and committed to the repo. Open it directly or query it:

```bash
python3 -c "
import csv
rows = list(csv.DictReader(open('studentroadtogermany/submissions.csv')))
print(f'{len(rows)} submission(s)')
for r in rows:
    print(f\"  {r['submitted_at']}  {r['name']} <{r['email']}>  [{r['package']}]\")
"
```

## Security note

The fine-grained PAT is visible in the JavaScript source. It is scoped to this one repository with `Contents: Read and write` only — it cannot access any other repo or GitHub resource. The worst case is someone triggering extra workflow runs (which consume Actions minutes). For higher-traffic use, wrap the dispatch call in a Cloudflare Worker to keep the token server-side.

## File structure

```
studentroadtogermany/
├── index.html              # Main page
├── styles.css
├── script.js               # Form → GitHub repository_dispatch
├── api.py                  # Local dev API server (SQLite)
├── store_submission.py     # Workflow script — appends to submissions.csv
├── submissions.csv         # Stored submissions (git-tracked)
└── README.md
```
