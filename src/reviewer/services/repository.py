
import os
import re
import shutil
import stat
from pathlib import Path
from urllib.parse import urlparse

from git import Repo


def _remove_readonly(func, path, _):
    """Clear read-only attribute and retry deletion (needed for Windows .git packfiles)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


class RepositoryService:
    def __init__(self, workspace_root: str = ".workspace"):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_repository_url(repository_url: str) -> None:
        parsed = urlparse(repository_url)

        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(
                r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",
                parsed.path,
            )
        ):
            raise ValueError("Only public HTTPS GitHub repository URLs are allowed.")

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
            raise ValueError("Invalid job ID.")
        
    def prepare_repository(
        self,
        repository_url: str,
        commit_sha: str,
        job_id: str,
    ) -> Path:
        self._validate_repository_url(repository_url)
        self._validate_job_id(job_id)
        workspace = self.workspace_root / job_id

        if workspace.exists():
            raise FileExistsError(
                f"Workspace already exists: {workspace}"
            )

        try:
            Repo.clone_from(
              repository_url,
              workspace,
              multi_options=["--depth=1", "--no-recurse-submodules"],
            )
            repo = Repo(workspace)
            repo.git.fetch("origin", commit_sha)
            repo.git.checkout(commit_sha)

            return workspace

        except Exception:
            self.cleanup_workspace(workspace)
            raise

    def cleanup_workspace(self, workspace: Path) -> None:
        """Safely remove a repository workspace directory."""
        if workspace.exists():
            shutil.rmtree(workspace, onerror=_remove_readonly)

