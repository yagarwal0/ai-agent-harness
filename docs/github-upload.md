# Upload this project to GitHub

Run commands from this project folder. It has its own local Git repository on `main`, separate from the repository in the parent Windows user folder. The upload steps below are instructions; preparing the project does not publish it.

## Create an empty GitHub repository

Create a repository in your GitHub account, choose its name and visibility, and leave the README, license, and .gitignore initialization options unchecked. Copy its HTTPS URL. Choose a license separately if you want to grant reuse rights; this preparation does not select one for you.

## Review and commit locally

```powershell
git rev-parse --show-toplevel
git check-ignore api_key.txt .venv/
git status --short
git add .
git diff --cached --stat
git diff --cached --name-only
```

The repository root must be this project folder. `api_key.txt`, `.venv`, `.env` files, and local scratch/export folders must not appear in the staged filenames. The empty credential example, application files, tests, and documentation should appear. Do not force-add ignored files.

Then create the commit:

```powershell
git commit -m "Initial interview tutor project"
```

If Git asks for an author identity, set your own name and email locally with `git config user.name` and `git config user.email`, then retry. You can use the private commit email shown in your GitHub account settings.

## Connect and upload

Replace `YOUR_USERNAME` and `YOUR_REPOSITORY` with your values before running:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Authenticate through Git's credential manager or your configured SSH/HTTPS method. OpenAI and Brave API keys are unrelated to GitHub authentication. Do not put tokens inside the remote URL.

After upload, open the repository's Actions tab to check the Python tests. The workflow uses mocked providers and requires no OpenAI/Brave repository secrets. Hosted CI remains unverified until it actually runs. If you created a nonempty remote repository, reconcile its history before pushing; do not force-push as a shortcut.
