"""Install a converted skill into a harness skills folder."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .convert import ConvertReport, convert_tree
from .errors import ToolError
from .findings import Finding
from .profiles import Profile
from .verify import verify_skill


def default_root(profile: Profile) -> Path:
    """Return the conventional global skills root for a profile."""
    home = Path.home()
    if profile.id == "claude":
        return home / ".claude" / "skills"
    if profile.id == "opencode":
        return home / ".config" / "opencode" / "skills"
    return home / ".openclaw" / "workspace" / "skills"


def install_skill(
    source_dir: os.PathLike,
    profile: Profile,
    root: Optional[os.PathLike] = None,
    force: bool = False,
) -> Tuple[Path, ConvertReport, List[Finding]]:
    """Convert to a temp dir, copy into the target root, then verify."""
    source = Path(source_dir).expanduser().resolve()
    target_root = Path(root).expanduser().resolve() if root else default_root(profile).resolve()
    if not (source / "SKILL.md").is_file():
        raise ToolError("no SKILL.md in %s" % source)

    with tempfile.TemporaryDirectory(prefix="skill-port-") as temp:
        staged = Path(temp) / "staged"
        converted, report, _ = convert_tree(
            source, staged, profile, force=False, write_report=False
        )
        name = converted.get("name") or source.name
        folder_name = str(name) if profile.id in ("openclaw", "portable") else source.name
        destination = target_root / folder_name
        if destination.exists() and not force:
            raise ToolError(
                "destination already exists: %s (use --force to replace)" % destination
            )
        if destination.exists():
            shutil.rmtree(str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(staged), str(destination))
        report.copied_files = [
            item for item in report.copied_files if item != "PORT_REPORT.md"
        ]

    findings = verify_skill(destination, profile)
    return destination, report, findings
