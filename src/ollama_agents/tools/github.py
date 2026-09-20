"""GitHub Automated Workflow tools — clone repositories, create branches, commit code, push changes, and manage GitHub Pull Requests.

Tools:
    github_clone_repo          Clone a remote GitHub repository into the local workspace.
    github_create_branch       Create and checkout a new Git feature branch.
    github_commit_and_push     Stage, commit, and push modified code to GitHub.
    github_create_pull_request Create a GitHub Pull Request via gh CLI.
    github_status              Check git status and current branch details.

Safe workspace root: ~/ollama_workspace/
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional
from ollama_agents.tool import Tool

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path.home() / "ollama_workspace"


def _safe_git_path(repo_dir: Optional[str] = None) -> Path:
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    if repo_dir:
        resolved = (WORKSPACE_ROOT / repo_dir).resolve()
    else:
        resolved = WORKSPACE_ROOT.resolve()
    return resolved


def github_clone_repo(repo_url: str, dest_dir: Optional[str] = None) -> str:
    """Clone a GitHub repository into the local workspace.

    Args:
        repo_url: HTTPS or SSH URL of the repository (e.g. 'https://github.com/user/repo.git' or 'owner/repo').
        dest_dir: Optional custom destination folder name inside ~/ollama_workspace/.
    """
    try:
        url = repo_url.strip()
        if not url.startswith("http") and not url.startswith("git@"):
            if "/" in url and not url.endswith(".git"):
                url = f"https://github.com/{url}.git"

        target_name = dest_dir or url.rstrip("/").split("/")[-1].replace(".git", "")
        target_path = WORKSPACE_ROOT / target_name

        if target_path.exists() and any(target_path.iterdir()):
            return f"Directory '{target_path.name}' already exists in workspace. Use github_status or github_create_branch."

        cmd = ["git", "clone", url, str(target_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if res.returncode == 0:
            return f"Successfully cloned '{url}' into ~/ollama_workspace/{target_name}!\nOutput:\n{res.stdout or res.stderr}"
        else:
            return f"Failed to clone repository '{url}'. Error:\n{res.stderr}"
    except Exception as e:
        return f"Failed to execute git clone: {e}"


def github_create_branch(branch_name: str, repo_dir: Optional[str] = None) -> str:
    """Create and checkout a new Git feature branch in a cloned repository.

    Args:
        branch_name: Name of the feature branch to create (e.g. 'feature/add-dark-mode').
        repo_dir: Optional name of the cloned repository subfolder inside ~/ollama_workspace/.
    """
    try:
        path = _safe_git_path(repo_dir)
        if not (path / ".git").exists():
            return f"Directory '{path}' is not a valid git repository."

        cmd = ["git", "checkout", "-b", branch_name.strip()]
        res = subprocess.run(cmd, cwd=str(path), capture_output=True, text=True, timeout=30)

        if res.returncode != 0 and "already exists" in res.stderr:
            cmd_checkout = ["git", "checkout", branch_name.strip()]
            res = subprocess.run(cmd_checkout, cwd=str(path), capture_output=True, text=True, timeout=30)

        if res.returncode == 0:
            return f"Switched to branch '{branch_name}' in repository '{path.name}'."
        return f"Failed to create/checkout branch '{branch_name}':\n{res.stderr}"
    except Exception as e:
        return f"Git branch operation failed: {e}"


def github_commit_and_push(
    commit_message: str,
    branch_name: Optional[str] = None,
    repo_dir: Optional[str] = None,
) -> str:
    """Stage all file changes, commit with a message, and push the branch to GitHub.

    Args:
        commit_message: Commit summary message (e.g. 'feat: implement fibonacci calculator').
        branch_name: Optional target branch name to push to. If omitted, pushes current HEAD branch.
        repo_dir: Optional name of the repository subfolder inside ~/ollama_workspace/.
    """
    try:
        path = _safe_git_path(repo_dir)
        if not (path / ".git").exists():
            return f"Directory '{path}' is not a valid git repository."

        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)

        # Commit
        res_commit = subprocess.run(
            ["git", "commit", "-m", commit_message.strip()],
            cwd=str(path),
            capture_output=True,
            text=True,
        )

        if "nothing to commit" in res_commit.stdout or "nothing to commit" in res_commit.stderr:
            commit_info = "Nothing to commit, working tree clean."
        else:
            commit_info = f"Committed: {res_commit.stdout.strip()}"

        # Get current branch if not supplied
        if not branch_name:
            res_b = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(path),
                capture_output=True,
                text=True,
            )
            branch_name = res_b.stdout.strip() or "main"

        # Push to remote
        res_push = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if res_push.returncode == 0:
            return (
                f"Successfully committed and pushed branch '{branch_name}' to GitHub!\n"
                f"{commit_info}\nPush Output:\n{res_push.stderr or res_push.stdout}"
            )
        else:
            return (
                f"Commit succeeded ({commit_info}), but push failed.\n"
                f"Ensure GitHub credentials/SSH or gh auth are configured.\nError:\n{res_push.stderr}"
            )
    except Exception as e:
        return f"Failed to commit and push: {e}"


def github_create_pull_request(
    title: str,
    body: str,
    base_branch: str = "main",
    repo_dir: Optional[str] = None,
) -> str:
    """Create a GitHub Pull Request for the active branch using GitHub CLI (gh).

    Args:
        title: Pull Request title.
        body: Description of changes made in the PR.
        base_branch: Base branch to merge into (default 'main').
        repo_dir: Optional repository subfolder inside ~/ollama_workspace/.
    """
    try:
        path = _safe_git_path(repo_dir)
        if not (path / ".git").exists():
            return f"Directory '{path}' is not a valid git repository."

        cmd = [
            "gh", "pr", "create",
            "--title", title.strip(),
            "--body", body.strip(),
            "--base", base_branch.strip(),
        ]
        res = subprocess.run(cmd, cwd=str(path), capture_output=True, text=True, timeout=45)

        if res.returncode == 0:
            return f"Successfully created GitHub Pull Request!\n{res.stdout.strip()}"

        return (
            f"GitHub CLI `gh` output: {res.stderr.strip()}\n"
            f"If `gh` is not authenticated, complete the PR manually with title: '{title}' and base branch '{base_branch}'."
        )
    except Exception as e:
        return f"Failed to create Pull Request: {e}"


def github_status(repo_dir: Optional[str] = None) -> str:
    """Check git status, current branch, and recent commits in a workspace repository.

    Args:
        repo_dir: Optional repository subfolder inside ~/ollama_workspace/.
    """
    try:
        path = _safe_git_path(repo_dir)
        if not (path / ".git").exists():
            return f"Directory '{path}' is not a valid git repository."

        res_status = subprocess.run(["git", "status"], cwd=str(path), capture_output=True, text=True)
        res_log = subprocess.run(["git", "log", "-n", "3", "--oneline"], cwd=str(path), capture_output=True, text=True)

        return (
            f"Repository Path: {path}\n"
            f"=== Git Status ===\n{res_status.stdout.strip()}\n\n"
            f"=== Recent Commits ===\n{res_log.stdout.strip()}"
        )
    except Exception as e:
        return f"Failed to fetch git status: {e}"


# Tool objects exported for agent registration
github_clone_repo = Tool(github_clone_repo)
github_create_branch = Tool(github_create_branch)
github_commit_and_push = Tool(github_commit_and_push)
github_create_pull_request = Tool(github_create_pull_request)
github_status = Tool(github_status)
