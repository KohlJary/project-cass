"""
Git REST API routes
Repository operations for the TUI GitPanel
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from path_policy import check_path, PathNotAllowed

router = APIRouter(prefix="/git", tags=["git"])

# Find git binary - systemd services may not have it in PATH
GIT_BINARY = shutil.which("git") or "/usr/bin/git"


# === Request Models ===

class StageRequest(BaseModel):
    """Request to stage files"""
    repo_path: str
    files: Optional[List[str]] = None  # None = stage all


class UnstageRequest(BaseModel):
    """Request to unstage files"""
    repo_path: str
    files: Optional[List[str]] = None  # None = unstage all


class CommitRequest(BaseModel):
    """Request to create a commit"""
    repo_path: str
    message: str
    author: Optional[str] = None  # e.g. "Daedalus <daedalus@cass-vessel.local>"


class DiffRequest(BaseModel):
    """Request for diff"""
    repo_path: str
    file: Optional[str] = None  # None = all changes
    staged: bool = False  # True = show staged changes


# A hung git (credential prompt, huge repo) used to block forever.
GIT_TIMEOUT_SECONDS = 30

# Never let git prompt for credentials on the server's terminal.
_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


# === Helper Functions ===

def safe_arg(value: str, what: str) -> str:
    """Reject user input that git would parse as an option (e.g. a branch
    named "--upload-pack=..." or a file "--output=...")."""
    if value is None or value == "" or value.startswith("-"):
        raise HTTPException(status_code=400, detail=f"Invalid {what}: {value!r}")
    return value


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECONDS, env=_GIT_ENV, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git command timed out")


def run_git(repo_path: str, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the specified repository"""
    # Only repos under the allowed roots (DATA_DIR, the Cass repo, project
    # working directories, CASS_FILE_ROOTS) - not any path on disk.
    try:
        path = check_path(repo_path)
    except PathNotAllowed as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {repo_path}")

    if not (path / ".git").exists() and not (path / ".git").is_file():
        # Check if it's inside a git repo
        result = _run([GIT_BINARY, "-C", str(path), "rev-parse", "--git-dir"])
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Not a git repository: {repo_path}")

    result = _run([GIT_BINARY, "-C", str(path)] + args)

    if check and result.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=f"Git command failed: {result.stderr.strip() or result.stdout.strip()}"
        )

    return result


# === Endpoints ===

@router.get("/status")
async def get_status(repo_path: str):
    """Get detailed git status for a repository"""
    # Get branch
    branch_result = run_git(repo_path, ["branch", "--show-current"], check=False)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None

    # Get ahead/behind
    ahead = behind = 0
    if branch:
        tracking_result = run_git(
            repo_path,
            ["rev-list", "--left-right", "--count", f"{branch}@{{upstream}}...HEAD"],
            check=False
        )
        if tracking_result.returncode == 0:
            parts = tracking_result.stdout.strip().split()
            if len(parts) == 2:
                behind, ahead = int(parts[0]), int(parts[1])

    # Get porcelain status
    status_result = run_git(repo_path, ["status", "--porcelain=v1"])

    staged = []
    modified = []
    untracked = []

    for line in status_result.stdout.strip().split("\n"):
        if not line:
            continue
        index_status = line[0]
        worktree_status = line[1]
        filename = line[3:]

        # Staged changes (index has changes)
        if index_status in "MADRC":
            staged.append({"file": filename, "status": index_status})

        # Working tree changes
        if worktree_status == "M":
            modified.append(filename)
        elif worktree_status == "?" or (index_status == "?" and worktree_status == "?"):
            untracked.append(filename)

    return {
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "clean": len(staged) == 0 and len(modified) == 0 and len(untracked) == 0
    }


@router.post("/stage")
async def stage_files(request: StageRequest):
    """Stage files for commit"""
    if request.files:
        # Stage specific files
        for file in request.files:
            run_git(request.repo_path, ["add", "--", safe_arg(file, "file")])
        return {"staged": request.files, "count": len(request.files)}
    else:
        # Stage all
        run_git(request.repo_path, ["add", "-A"])
        # Get list of staged files
        result = run_git(request.repo_path, ["diff", "--cached", "--name-only"])
        files = [f for f in result.stdout.strip().split("\n") if f]
        return {"staged": files, "count": len(files), "all": True}


@router.post("/unstage")
async def unstage_files(request: UnstageRequest):
    """Unstage files from the index"""
    if request.files:
        # Unstage specific files
        for file in request.files:
            run_git(request.repo_path, ["reset", "HEAD", "--", safe_arg(file, "file")], check=False)
        return {"unstaged": request.files, "count": len(request.files)}
    else:
        # Unstage all
        run_git(request.repo_path, ["reset", "HEAD"], check=False)
        return {"unstaged": "all", "count": -1, "all": True}


@router.post("/commit")
async def create_commit(request: CommitRequest):
    """Create a commit with the staged changes"""
    # Check if there are staged changes
    status_result = run_git(request.repo_path, ["diff", "--cached", "--quiet"], check=False)
    if status_result.returncode == 0:
        raise HTTPException(status_code=400, detail="No staged changes to commit")

    # Build commit command
    # "-m<msg>" / "--author=<a>" keep the value attached to its flag, so a
    # value starting with "-" can't become a separate option.
    args = ["commit", f"--message={request.message}"]
    if request.author:
        args.append(f"--author={request.author}")

    result = run_git(request.repo_path, args)

    # Get the commit hash
    hash_result = run_git(request.repo_path, ["rev-parse", "HEAD"])
    commit_hash = hash_result.stdout.strip()[:8]

    return {
        "success": True,
        "hash": commit_hash,
        "message": request.message,
        "author": request.author
    }


@router.get("/diff")
async def get_diff(repo_path: str, file: Optional[str] = None, staged: bool = False):
    """Get diff for changes"""
    args = ["diff"]
    if staged:
        args.append("--cached")
    if file:
        args.extend(["--", safe_arg(file, "file")])

    result = run_git(repo_path, args, check=False)

    return {
        "diff": result.stdout,
        "file": file,
        "staged": staged
    }


@router.get("/log")
async def get_log(repo_path: str, count: int = 10):
    """Get recent commit log"""
    result = run_git(
        repo_path,
        ["log", f"--max-count={max(1, min(int(count), 500))}", "--pretty=format:%h|%s|%an|%ar"],
        check=False
    )

    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0],
                "message": parts[1],
                "author": parts[2],
                "relative_time": parts[3]
            })

    return {"commits": commits, "count": len(commits)}


@router.post("/checkout")
async def checkout_branch(repo_path: str, branch: str, create: bool = False):
    """Switch branches or create a new branch"""
    safe_arg(branch, "branch")
    args = ["checkout"]
    if create:
        args.append("-b")
        args.append(branch)
    else:
        # Trailing "--" makes git treat `branch` as a ref, never a path.
        args.extend([branch, "--"])

    run_git(repo_path, args)

    return {"branch": branch, "created": create}


@router.get("/branches")
async def list_branches(repo_path: str):
    """List all branches"""
    result = run_git(repo_path, ["branch", "-a", "--format=%(refname:short)|%(HEAD)"])

    branches = []
    current = None
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        name = parts[0]
        is_current = len(parts) > 1 and parts[1] == "*"
        branches.append(name)
        if is_current:
            current = name

    return {"branches": branches, "current": current}
