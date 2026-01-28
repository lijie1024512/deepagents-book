"""Skills middleware for loading and exposing agent skills to the system prompt.

This module implements Anthropic's agent skills pattern with progressive disclosure,
loading skills from backend storage via configurable sources.

## Architecture

Skills are loaded from one or more **sources** - paths in a backend where skills are
organized. Sources are loaded in order, with later sources overriding earlier ones
when skills have the same name (last one wins). This enables layering: base -> user
-> project -> team skills.

The middleware uses backend APIs exclusively (no direct filesystem access), making it
portable across different storage backends (filesystem, state, remote storage, etc.).

For StateBackend (ephemeral/in-memory), use a factory function:
```python
SkillsMiddleware(backend=lambda rt: StateBackend(rt), ...)
```

## Skill Structure

Each skill is a directory containing a SKILL.md file with YAML frontmatter:

```
/skills/user/web-research/
├── SKILL.md          # Required: YAML frontmatter + markdown instructions
└── helper.py         # Optional: supporting files
```

SKILL.md format:
```markdown
---
name: web-research
description: Structured approach to conducting thorough web research
license: MIT
---

# Web Research Skill

## When to Use
- User asks you to research a topic
...
```

## Skill Metadata (SkillMetadata)

Parsed from YAML frontmatter per Agent Skills specification:
- `name`: Skill identifier (max 64 chars, lowercase alphanumeric and hyphens)
- `description`: What the skill does (max 1024 chars)
- `path`: Backend path to the SKILL.md file
- Optional: `license`, `compatibility`, `metadata`, `allowed_tools`

## Sources

Sources are simply paths to skill directories in the backend. The source name is
derived from the last component of the path (e.g., "/skills/user/" -> "user").

Example sources:
```python
[
    "/skills/user/",
    "/skills/project/"
]
```

## Path Conventions

All paths use POSIX conventions (forward slashes) via `PurePosixPath`:
- Backend paths: "/skills/user/web-research/SKILL.md"
- Virtual, platform-independent
- Backends handle platform-specific conversions as needed

## Usage

```python
from deepagents.backends.state import StateBackend
from deepagents.middleware.skills import SkillsMiddleware

middleware = SkillsMiddleware(
    backend=my_backend,
    sources=[
        "/skills/base/",
        "/skills/user/",
        "/skills/project/",
    ],
)
```
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated

import yaml
from langchain.agents.middleware.types import PrivateStateAttr

if TYPE_CHECKING:
    from deepagents.backends.protocol import BACKEND_TYPES, BackendProtocol

from collections.abc import Awaitable, Callable
from typing import NotRequired, TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolRuntime
from langgraph.runtime import Runtime

from deepagents.middleware._utils import append_to_system_message

logger = logging.getLogger(__name__)

# Security: Maximum size for SKILL.md files to prevent DoS attacks (10MB)
MAX_SKILL_FILE_SIZE = 10 * 1024 * 1024

# Agent Skills specification constraints (https://agentskills.io/specification)
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024


class SkillMetadata(TypedDict):
    """Metadata for a skill per Agent Skills specification (https://agentskills.io/specification)."""

    name: str
    """Skill identifier (max 64 chars, lowercase alphanumeric and hyphens)."""

    description: str
    """What the skill does (max 1024 chars)."""

    path: str
    """Path to the SKILL.md file."""

    license: str | None
    """License name or reference to bundled license file."""

    compatibility: str | None
    """Environment requirements (max 500 chars)."""

    metadata: dict[str, str]
    """Arbitrary key-value mapping for additional metadata."""

    allowed_tools: list[str]
    """Space-delimited list of pre-approved tools. (Experimental)"""


class SkillsState(AgentState):
    """State for the skills middleware."""

    skills_metadata: NotRequired[Annotated[list[SkillMetadata], PrivateStateAttr]]
    """List of loaded skill metadata from all configured sources."""


class SkillsStateUpdate(TypedDict):
    """State update for the skills middleware."""

    skills_metadata: list[SkillMetadata]
    """List of loaded skill metadata to merge into state."""


def _validate_skill_name(name: str, directory_name: str) -> tuple[bool, str]:
    """Validate skill name per Agent Skills specification.

    Requirements per spec:
    - Max 64 characters
    - Lowercase alphanumeric and hyphens only (a-z, 0-9, -)
    - Cannot start or end with hyphen
    - No consecutive hyphens
    - Must match parent directory name

    Args:
        name: Skill name from YAML frontmatter
        directory_name: Parent directory name

    Returns:
        (is_valid, error_message) tuple. Error message is empty if valid.
    """
    if not name:
        return False, "name is required"
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return False, "name exceeds 64 characters"
    # Pattern: lowercase alphanumeric, single hyphens between segments, no start/end hyphen
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        return False, "name must be lowercase alphanumeric with single hyphens only"
    if name != directory_name:
        return False, f"name '{name}' must match directory name '{directory_name}'"
    return True, ""


def _parse_skill_metadata(
    content: str,
    skill_path: str,
    directory_name: str,
) -> SkillMetadata | None:
    """Parse YAML frontmatter from SKILL.md content.

    Extracts metadata per Agent Skills specification from YAML frontmatter delimited
    by --- markers at the start of the content.

    Args:
        content: Content of the SKILL.md file
        skill_path: Path to the SKILL.md file (for error messages and metadata)
        directory_name: Name of the parent directory containing the skill

    Returns:
        SkillMetadata if parsing succeeds, None if parsing fails or validation errors occur
    """
    if len(content) > MAX_SKILL_FILE_SIZE:
        logger.warning("Skipping %s: content too large (%d bytes)", skill_path, len(content))
        return None

    # Match YAML frontmatter between --- delimiters
    frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if not match:
        logger.warning("Skipping %s: no valid YAML frontmatter found", skill_path)
        return None

    frontmatter_str = match.group(1)

    # Parse YAML using safe_load for proper nested structure support
    try:
        frontmatter_data = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError as e:
        logger.warning("Invalid YAML in %s: %s", skill_path, e)
        return None

    if not isinstance(frontmatter_data, dict):
        logger.warning("Skipping %s: frontmatter is not a mapping", skill_path)
        return None

    # Validate required fields
    name = frontmatter_data.get("name")
    description = frontmatter_data.get("description")

    if not name or not description:
        logger.warning("Skipping %s: missing required 'name' or 'description'", skill_path)
        return None

    # Validate name format per spec (warn but continue loading for backwards compatibility)
    is_valid, error = _validate_skill_name(str(name), directory_name)
    if not is_valid:
        logger.warning(
            "Skill '%s' in %s does not follow Agent Skills specification: %s. Consider renaming for spec compliance.",
            name,
            skill_path,
            error,
        )

    # Validate description length per spec (max 1024 chars)
    description_str = str(description).strip()
    if len(description_str) > MAX_SKILL_DESCRIPTION_LENGTH:
        logger.warning(
            "Description exceeds %d characters in %s, truncating",
            MAX_SKILL_DESCRIPTION_LENGTH,
            skill_path,
        )
        description_str = description_str[:MAX_SKILL_DESCRIPTION_LENGTH]

    if frontmatter_data.get("allowed-tools"):
        allowed_tools = frontmatter_data.get("allowed-tools").split(" ")
    else:
        allowed_tools = []

    return SkillMetadata(
        name=str(name),
        description=description_str,
        path=skill_path,
        metadata=frontmatter_data.get("metadata", {}),
        license=frontmatter_data.get("license", "").strip() or None,
        compatibility=frontmatter_data.get("compatibility", "").strip() or None,
        allowed_tools=allowed_tools,
    )


def _get_skill_file_mtime(backend: BackendProtocol, skill_path: str) -> str | None:
    """Get modification time of .skill file.

    Args:
        backend: Backend instance
        skill_path: Path to .skill file

    Returns:
        ISO format timestamp string, or None if not available
    """
    try:
        parent_dir = str(PurePosixPath(skill_path).parent)
        items = backend.ls_info(parent_dir)
        for item in items:
            if item["path"] == skill_path and not item.get("is_dir", False):
                return item.get("modified_at")
    except Exception as e:
        logger.debug("Failed to get modification time for %s: %s", skill_path, e)
    return None


def _is_direct_filesystem_backend(backend: BackendProtocol) -> bool:
    """Check if backend is a FilesystemBackend that supports direct extraction.

    Args:
        backend: Backend instance to check

    Returns:
        True if backend is FilesystemBackend with a cwd attribute
    """
    return hasattr(backend, "cwd") and hasattr(backend, "_resolve_path")


def _get_filesystem_backend_for_path(backend: BackendProtocol, path: str) -> BackendProtocol | None:
    """Get the FilesystemBackend for a given path, handling CompositeBackend.

    For CompositeBackend, this resolves the route to get the actual backend.
    For FilesystemBackend, returns the backend directly.

    Args:
        backend: Backend instance (FilesystemBackend or CompositeBackend)
        path: Path to resolve the backend for

    Returns:
        FilesystemBackend instance if available, None otherwise
    """
    # Direct FilesystemBackend
    if _is_direct_filesystem_backend(backend):
        return backend

    # CompositeBackend - get the routed backend for this path
    if hasattr(backend, "_get_backend_and_key"):
        route_backend, _ = backend._get_backend_and_key(path)
        if _is_direct_filesystem_backend(route_backend):
            return route_backend

    return None


def _extract_skill_to_filesystem(
    zip_content: bytes, skill_path: str, fs_backend: BackendProtocol, target_base_path: str
) -> tuple[str, str] | None:
    """Extract .skill file directly to filesystem (for FilesystemBackend).

    This is an optimized extraction that writes directly to the filesystem
    without creating temporary files, reducing I/O operations.

    Args:
        zip_content: Binary content of the .skill ZIP file
        skill_path: Path to the .skill file (for error messages)
        fs_backend: FilesystemBackend instance (must have cwd and _resolve_path)
        target_base_path: Base path where skill files should be extracted

    Returns:
        Tuple of (skill_md_content, directory_name) if successful, None otherwise
    """
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_ref:
            # Find the root directory in the ZIP
            root_dirs = {name.split("/")[0] for name in zip_ref.namelist() if "/" in name}
            if not root_dirs:
                logger.warning("No root directory found in %s", skill_path)
                return None

            # Use the first root directory (typically there's only one)
            root_dir = list(root_dirs)[0]
            directory_name = root_dir.rstrip("/")
            skill_md_path_in_zip = f"{root_dir}/SKILL.md"

            # Check if SKILL.md exists in the ZIP
            if skill_md_path_in_zip not in zip_ref.namelist():
                logger.warning("SKILL.md not found in %s", skill_path)
                return None

            # Resolve physical target path
            # For target_base_path like "/skills/user/", we need to resolve "/" + directory_name
            target_virtual_path = "/" + directory_name
            target_physical_path = fs_backend._resolve_path(target_virtual_path)

            # Get source .skill file modification time
            # skill_path is like "/skills/user/novel-generator.skill", resolve to "/" + filename
            skill_filename = PurePosixPath(skill_path).name
            skill_virtual_path = "/" + skill_filename
            skill_physical_path = fs_backend._resolve_path(skill_virtual_path)
            skill_mtime = skill_physical_path.stat().st_mtime if skill_physical_path.exists() else 0

            # Check if already extracted and up-to-date
            skill_md_physical_path = target_physical_path / "SKILL.md"
            if skill_md_physical_path.exists():
                # Compare modification times
                extracted_mtime = skill_md_physical_path.stat().st_mtime
                if extracted_mtime >= skill_mtime:
                    # Already extracted and up-to-date, read SKILL.md content
                    skill_md_content = skill_md_physical_path.read_text(encoding="utf-8")
                    logger.debug(
                        "Using cached extracted skill from %s (up-to-date)",
                        target_physical_path,
                    )
                    return (skill_md_content, directory_name)

            # Need to extract
            logger.debug("Extracting .skill file %s to %s", skill_path, target_physical_path)

            # Create target directory if not exists
            target_physical_path.mkdir(parents=True, exist_ok=True)

            # Extract all files directly to target directory
            for zip_info in zip_ref.infolist():
                # Skip directories
                if zip_info.is_dir():
                    continue

                # Get relative path from root_dir
                if not zip_info.filename.startswith(root_dir + "/"):
                    continue

                rel_path = zip_info.filename[len(root_dir) + 1:]
                if not rel_path:
                    continue

                # Calculate target file path
                target_file_path = target_physical_path / rel_path

                # Create parent directories
                target_file_path.parent.mkdir(parents=True, exist_ok=True)

                # Extract file content and write
                content = zip_ref.read(zip_info.filename)
                target_file_path.write_bytes(content)

            # Read SKILL.md content
            skill_md_content = skill_md_physical_path.read_text(encoding="utf-8")

            logger.debug(
                "Extracted .skill file %s to %s",
                skill_path,
                target_physical_path,
            )

            return (skill_md_content, directory_name)

    except zipfile.BadZipFile:
        logger.warning("Invalid ZIP file: %s", skill_path)
        return None
    except Exception as e:
        logger.warning("Error extracting .skill file %s: %s", skill_path, e)
        return None


def _extract_skill_from_zip(
    zip_content: bytes, skill_path: str, backend: BackendProtocol, target_base_path: str
) -> tuple[str, str] | None:
    """Extract SKILL.md and all resource files from a Coze .skill ZIP file.

    Coze .skill files are ZIP archives containing a directory with SKILL.md and
    supporting files (references/, assets/, scripts/, etc.). This function:
    1. For FilesystemBackend (or CompositeBackend with FilesystemBackend route):
       Extracts directly to filesystem (optimized, no temp files)
    2. For other backends: Uses temporary files and uploads via backend

    Args:
        zip_content: Binary content of the .skill ZIP file
        skill_path: Path to the .skill file (for error messages)
        backend: Backend instance to upload extracted files to
        target_base_path: Base path in backend where skill files should be extracted

    Returns:
        Tuple of (skill_md_content, directory_name) if successful, None otherwise
    """
    # Try to get FilesystemBackend for this path (handles CompositeBackend)
    fs_backend = _get_filesystem_backend_for_path(backend, skill_path)
    if fs_backend is not None:
        # Use optimized direct extraction to filesystem
        return _extract_skill_to_filesystem(zip_content, skill_path, fs_backend, target_base_path)

    # For other backends, use the original upload-based approach
    try:
        # Get .skill file modification time for cache checking
        skill_file_modified_at = _get_skill_file_mtime(backend, skill_path)

        # Write ZIP to temporary file to inspect its contents
        with tempfile.NamedTemporaryFile(delete=False, suffix=".skill") as tmp_file:
            tmp_file.write(zip_content)
            tmp_file_path = tmp_file.name

        try:
            with zipfile.ZipFile(tmp_file_path, "r") as zip_ref:
                # Find the root directory in the ZIP
                root_dirs = {name.split("/")[0] for name in zip_ref.namelist() if "/" in name}
                if not root_dirs:
                    logger.warning("No root directory found in %s", skill_path)
                    return None

                # Use the first root directory (typically there's only one)
                root_dir = list(root_dirs)[0]
                directory_name = root_dir.rstrip("/")
                skill_md_path_in_zip = f"{root_dir}/SKILL.md"

                # Check if SKILL.md exists in the ZIP
                if skill_md_path_in_zip not in zip_ref.namelist():
                    logger.warning("SKILL.md not found in %s", skill_path)
                    return None

                # Calculate target paths
                skill_target_path = str(PurePosixPath(target_base_path) / directory_name)
                marker_file_path = str(PurePosixPath(skill_target_path) / ".skill_extracted")
                skill_md_target_path = str(PurePosixPath(skill_target_path) / "SKILL.md")

                # Check if already extracted and up-to-date
                if skill_file_modified_at:
                    try:
                        marker_responses = backend.download_files([marker_file_path])
                        if marker_responses and marker_responses[0].content and not marker_responses[0].error:
                            # Parse marker file
                            marker_data = json.loads(marker_responses[0].content.decode("utf-8"))
                            marker_source_mtime = marker_data.get("source_modified_at", "")

                            # Compare timestamps
                            if marker_source_mtime == skill_file_modified_at:
                                # File unchanged, try to read cached SKILL.md
                                skill_md_responses = backend.download_files([skill_md_target_path])
                                if (
                                    skill_md_responses
                                    and skill_md_responses[0].content
                                    and not skill_md_responses[0].error
                                ):
                                    skill_md_content = skill_md_responses[0].content.decode("utf-8")
                                    logger.debug(
                                        "Using cached extracted skill from %s (source unchanged since %s)",
                                        skill_target_path,
                                        skill_file_modified_at,
                                    )
                                    return (skill_md_content, directory_name)
                    except (json.JSONDecodeError, KeyError, Exception) as e:
                        logger.debug("Failed to check extraction cache, will re-extract: %s", e)

                # Need to extract (file not cached or source updated)
                logger.debug("Extracting .skill file %s to %s", skill_path, skill_target_path)

                # Extract and read SKILL.md
                skill_md_content = zip_ref.read(skill_md_path_in_zip).decode("utf-8")

                # Use tempfile.mkdtemp to create a temporary directory for extraction
                extract_dir = tempfile.mkdtemp(prefix="skill_extract_")
                try:
                    # Extract all files from ZIP to temporary directory
                    zip_ref.extractall(extract_dir)

                    # Upload all extracted files to backend
                    files_to_upload: list[tuple[str, bytes]] = []

                    extracted_skill_dir = os.path.join(extract_dir, root_dir)
                    for root, dirs, files in os.walk(extracted_skill_dir):
                        for file in files:
                            local_file_path = os.path.join(root, file)
                            # Calculate relative path from root_dir
                            rel_path = os.path.relpath(local_file_path, extracted_skill_dir)
                            # Convert to POSIX path format
                            rel_path_posix = rel_path.replace(os.sep, "/")
                            # Construct target path in backend
                            target_path = str(PurePosixPath(skill_target_path) / rel_path_posix)

                            # Read file content
                            with open(local_file_path, "rb") as f:
                                file_content = f.read()

                            files_to_upload.append((target_path, file_content))

                    # Upload all files to backend
                    if files_to_upload:
                        upload_responses = backend.upload_files(files_to_upload)
                        # Check for upload errors
                        for (path, _), response in zip(files_to_upload, upload_responses, strict=True):
                            if response.error:
                                logger.warning(
                                    "Failed to upload resource file %s from %s: %s",
                                    path,
                                    skill_path,
                                    response.error,
                                )

                    # Create/update extraction marker file
                    if skill_file_modified_at:
                        marker_data = {
                            "source_file": skill_path,
                            "source_modified_at": skill_file_modified_at,
                            "extracted_at": datetime.now(UTC).isoformat(),
                        }
                        marker_content = json.dumps(marker_data, indent=2).encode("utf-8")
                        marker_responses = backend.upload_files([(marker_file_path, marker_content)])
                        if marker_responses and marker_responses[0].error:
                            logger.warning(
                                "Failed to create extraction marker file %s: %s",
                                marker_file_path,
                                marker_responses[0].error,
                            )

                    logger.debug(
                        "Extracted %d files from %s to %s",
                        len(files_to_upload),
                        skill_path,
                        skill_target_path,
                    )

                    return (skill_md_content, directory_name)
                finally:
                    # Clean up temporary extraction directory
                    try:
                        shutil.rmtree(extract_dir)
                        logger.debug("Cleaned up temporary extraction directory: %s", extract_dir)
                    except OSError as e:
                        logger.warning("Failed to clean up temporary directory %s: %s", extract_dir, e)
        finally:
            # Clean up temporary ZIP file
            try:
                os.unlink(tmp_file_path)
            except OSError:
                pass

    except zipfile.BadZipFile:
        logger.warning("Invalid ZIP file: %s", skill_path)
        return None
    except Exception as e:
        logger.warning("Error extracting .skill file %s: %s", skill_path, e)
        return None


def _list_skills(backend: BackendProtocol, source_path: str) -> list[SkillMetadata]:
    """List all skills from a backend source.

    Scans backend for subdirectories containing SKILL.md files and .skill files
    (Coze format ZIP archives), downloads their content, parses YAML frontmatter,
    and returns skill metadata.

    For .skill files, checks if an extracted directory already exists. If it does
    and contains SKILL.md, uses the directory instead of re-extracting the .skill file.

    Expected structure:
        source_path/
        ├── skill-name/
        │   ├── SKILL.md        # Required
        │   └── helper.py       # Optional
        └── skill-name.skill    # Coze format (ZIP archive containing SKILL.md)

    Args:
        backend: Backend instance to use for file operations
        source_path: Path to the skills directory in the backend

    Returns:
        List of skill metadata from successfully parsed SKILL.md files
    """
    base_path = source_path

    skills: list[SkillMetadata] = []
    items = backend.ls_info(base_path)
    # Find all skill directories (directories containing SKILL.md) and .skill files
    skill_dirs = []
    skill_files = []
    skill_dir_names = set()  # Track directory names to avoid duplicates

    for item in items:
        if item.get("is_dir"):
            skill_dirs.append(item["path"])
            # Extract directory name for deduplication
            dir_name = PurePosixPath(item["path"]).name
            skill_dir_names.add(dir_name)
        elif item["path"].endswith(".skill"):
            # Coze .skill files are ZIP archives
            skill_files.append(item["path"])

    # Filter out .skill files that already have extracted directories
    # e.g., if novel-generator/ exists, skip novel-generator.skill
    skill_files_to_process = []
    for skill_file_path in skill_files:
        # Get the expected directory name (e.g., "novel-generator.skill" -> "novel-generator")
        skill_file_name = PurePosixPath(skill_file_path).name
        expected_dir_name = skill_file_name.rsplit(".", 1)[0]  # Remove .skill extension

        if expected_dir_name not in skill_dir_names:
            skill_files_to_process.append(skill_file_path)
        else:
            logger.debug(
                "Skipping .skill file %s, using existing directory %s/",
                skill_file_path,
                expected_dir_name,
            )

    skill_files = skill_files_to_process

    # Process regular skill directories
    if skill_dirs:
        # For each skill directory, check if SKILL.md exists and download it
        skill_md_paths = []
        for skill_dir_path in skill_dirs:
            # Construct SKILL.md path using PurePosixPath for safe, standardized path operations
            skill_dir = PurePosixPath(skill_dir_path)
            skill_md_path = str(skill_dir / "SKILL.md")
            skill_md_paths.append((skill_dir_path, skill_md_path))

        paths_to_download = [skill_md_path for _, skill_md_path in skill_md_paths]
        responses = backend.download_files(paths_to_download)

        # Parse each downloaded SKILL.md
        for (skill_dir_path, skill_md_path), response in zip(skill_md_paths, responses, strict=True):
            if response.error:
                # Skill doesn't have a SKILL.md, skip it
                continue

            if response.content is None:
                logger.warning("Downloaded skill file %s has no content", skill_md_path)
                continue

            try:
                content = response.content.decode("utf-8")
            except UnicodeDecodeError as e:
                logger.warning("Error decoding %s: %s", skill_md_path, e)
                continue

            # Extract directory name from path using PurePosixPath
            directory_name = PurePosixPath(skill_dir_path).name

            # Parse metadata
            skill_metadata = _parse_skill_metadata(
                content=content,
                skill_path=skill_md_path,
                directory_name=directory_name,
            )
            if skill_metadata:
                skills.append(skill_metadata)

    # Process Coze .skill files (ZIP archives)
    if skill_files:
        skill_file_responses = backend.download_files(skill_files)
        for skill_file_path, response in zip(skill_files, skill_file_responses, strict=True):
            if response.error:
                logger.warning("Failed to download .skill file %s: %s", skill_file_path, response.error)
                continue

            if response.content is None:
                logger.warning("Downloaded .skill file %s has no content", skill_file_path)
                continue

            # Extract SKILL.md and all resource files from ZIP
            # Upload extracted files to the same location as the .skill file's parent directory
            skill_file_parent = str(PurePosixPath(skill_file_path).parent)
            result = _extract_skill_from_zip(
                response.content, skill_file_path, backend, skill_file_parent
            )
            if result is None:
                continue

            content, directory_name = result

            # Parse metadata
            # Use the .skill file path as skill_path, but construct a virtual SKILL.md path
            skill_dir = PurePosixPath(skill_file_path).parent / directory_name
            skill_md_path = str(skill_dir / "SKILL.md")

            skill_metadata = _parse_skill_metadata(
                content=content,
                skill_path=skill_md_path,
                directory_name=directory_name,
            )
            if skill_metadata:
                skills.append(skill_metadata)

    return skills


async def _alist_skills(backend: BackendProtocol, source_path: str) -> list[SkillMetadata]:
    """List all skills from a backend source (async version).

    Scans backend for subdirectories containing SKILL.md files and .skill files
    (Coze format ZIP archives), downloads their content, parses YAML frontmatter,
    and returns skill metadata.

    For .skill files, checks if an extracted directory already exists. If it does
    and contains SKILL.md, uses the directory instead of re-extracting the .skill file.

    Expected structure:
        source_path/
        ├── skill-name/
        │   ├── SKILL.md        # Required
        │   └── helper.py       # Optional
        └── skill-name.skill    # Coze format (ZIP archive containing SKILL.md)

    Args:
        backend: Backend instance to use for file operations
        source_path: Path to the skills directory in the backend

    Returns:
        List of skill metadata from successfully parsed SKILL.md files
    """
    base_path = source_path

    skills: list[SkillMetadata] = []
    items = await backend.als_info(base_path)
    # Find all skill directories (directories containing SKILL.md) and .skill files
    skill_dirs = []
    skill_files = []
    skill_dir_names = set()  # Track directory names to avoid duplicates

    for item in items:
        if item.get("is_dir"):
            skill_dirs.append(item["path"])
            # Extract directory name for deduplication
            dir_name = PurePosixPath(item["path"]).name
            skill_dir_names.add(dir_name)
        elif item["path"].endswith(".skill"):
            # Coze .skill files are ZIP archives
            skill_files.append(item["path"])

    # Filter out .skill files that already have extracted directories
    # e.g., if novel-generator/ exists, skip novel-generator.skill
    skill_files_to_process = []
    for skill_file_path in skill_files:
        # Get the expected directory name (e.g., "novel-generator.skill" -> "novel-generator")
        skill_file_name = PurePosixPath(skill_file_path).name
        expected_dir_name = skill_file_name.rsplit(".", 1)[0]  # Remove .skill extension

        if expected_dir_name not in skill_dir_names:
            skill_files_to_process.append(skill_file_path)
        else:
            logger.debug(
                "Skipping .skill file %s, using existing directory %s/",
                skill_file_path,
                expected_dir_name,
            )

    skill_files = skill_files_to_process

    # Process regular skill directories
    if skill_dirs:
        # For each skill directory, check if SKILL.md exists and download it
        skill_md_paths = []
        for skill_dir_path in skill_dirs:
            # Construct SKILL.md path using PurePosixPath for safe, standardized path operations
            skill_dir = PurePosixPath(skill_dir_path)
            skill_md_path = str(skill_dir / "SKILL.md")
            skill_md_paths.append((skill_dir_path, skill_md_path))

        paths_to_download = [skill_md_path for _, skill_md_path in skill_md_paths]
        responses = await backend.adownload_files(paths_to_download)

        # Parse each downloaded SKILL.md
        for (skill_dir_path, skill_md_path), response in zip(skill_md_paths, responses, strict=True):
            if response.error:
                # Skill doesn't have a SKILL.md, skip it
                continue

            if response.content is None:
                logger.warning("Downloaded skill file %s has no content", skill_md_path)
                continue

            try:
                content = response.content.decode("utf-8")
            except UnicodeDecodeError as e:
                logger.warning("Error decoding %s: %s", skill_md_path, e)
                continue

            # Extract directory name from path using PurePosixPath
            directory_name = PurePosixPath(skill_dir_path).name

            # Parse metadata
            skill_metadata = _parse_skill_metadata(
                content=content,
                skill_path=skill_md_path,
                directory_name=directory_name,
            )
            if skill_metadata:
                skills.append(skill_metadata)

    # Process Coze .skill files (ZIP archives)
    if skill_files:
        skill_file_responses = await backend.adownload_files(skill_files)
        for skill_file_path, response in zip(skill_files, skill_file_responses, strict=True):
            if response.error:
                logger.warning("Failed to download .skill file %s: %s", skill_file_path, response.error)
                continue

            if response.content is None:
                logger.warning("Downloaded .skill file %s has no content", skill_file_path)
                continue

            # Extract SKILL.md and all resource files from ZIP
            # Upload extracted files to the same location as the .skill file's parent directory
            skill_file_parent = str(PurePosixPath(skill_file_path).parent)
            result = _extract_skill_from_zip(
                response.content, skill_file_path, backend, skill_file_parent
            )
            if result is None:
                continue

            content, directory_name = result

            # Parse metadata
            # Use the .skill file path as skill_path, but construct a virtual SKILL.md path
            skill_dir = PurePosixPath(skill_file_path).parent / directory_name
            skill_md_path = str(skill_dir / "SKILL.md")

            skill_metadata = _parse_skill_metadata(
                content=content,
                skill_path=skill_md_path,
                directory_name=directory_name,
            )
            if skill_metadata:
                skills.append(skill_metadata)

    return skills


SKILLS_SYSTEM_PROMPT = """

## Skills System

You have access to a skills library that provides specialized capabilities and domain knowledge.

{skills_locations}

**Available Skills:**

{skills_list}

**How to Use Skills (Progressive Disclosure):**

Skills follow a **progressive disclosure** pattern - you see their name and description above, but only read full instructions when needed:

1. **Recognize when a skill applies**: Check if the user's task matches a skill's description
2. **Read the skill's full instructions**: Use the path shown in the skill list above
3. **Follow the skill's instructions**: SKILL.md contains step-by-step workflows, best practices, and examples
4. **Access supporting files**: Skills may include helper scripts, configs, or reference docs - use absolute paths

**When to Use Skills:**
- User's request matches a skill's domain (e.g., "research X" -> web-research skill)
- You need specialized knowledge or structured workflows
- A skill provides proven patterns for complex tasks

**Executing Skill Scripts:**
Skills may contain Python scripts or other executable files. Always use absolute paths from the skill list.

**Example Workflow:**

User: "Can you research the latest developments in quantum computing?"

1. Check available skills -> See "web-research" skill with its path
2. Read the skill using the path shown
3. Follow the skill's research workflow (search -> organize -> synthesize)
4. Use any helper scripts with absolute paths

Remember: Skills make you more capable and consistent. When in doubt, check if a skill exists for the task!
"""


class SkillsMiddleware(AgentMiddleware):
    """Middleware for loading and exposing agent skills to the system prompt.

    Loads skills from backend sources and injects them into the system prompt
    using progressive disclosure (metadata first, full content on demand).

    Skills are loaded in source order with later sources overriding earlier ones.

    Example:
        ```python
        from deepagents.backends.filesystem import FilesystemBackend

        backend = FilesystemBackend(root_dir="/path/to/skills")
        middleware = SkillsMiddleware(
            backend=backend,
            sources=[
                "/path/to/skills/user/",
                "/path/to/skills/project/",
            ],
        )
        ```

    Args:
        backend: Backend instance for file operations
        sources: List of skill source paths. Source names are derived from the last path component.
    """

    state_schema = SkillsState

    def __init__(self, *, backend: BACKEND_TYPES, sources: list[str]) -> None:
        """Initialize the skills middleware.

        Args:
            backend: Backend instance or factory function that takes runtime and returns a backend.
                     Use a factory for StateBackend: `lambda rt: StateBackend(rt)`
            sources: List of skill source paths (e.g., ["/skills/user/", "/skills/project/"]).
        """
        self._backend = backend
        self.sources = sources
        self.system_prompt_template = SKILLS_SYSTEM_PROMPT

    def _get_backend(self, state: SkillsState, runtime: Runtime, config: RunnableConfig) -> BackendProtocol:
        """Resolve backend from instance or factory.

        Args:
            state: Current agent state.
            runtime: Runtime context for factory functions.
            config: Runnable config to pass to backend factory.

        Returns:
            Resolved backend instance
        """
        if callable(self._backend):
            # Construct an artificial tool runtime to resolve backend factory
            tool_runtime = ToolRuntime(
                state=state,
                context=runtime.context,
                stream_writer=runtime.stream_writer,
                store=runtime.store,
                config=config,
                tool_call_id=None,
            )
            backend = self._backend(tool_runtime)
            if backend is None:
                raise AssertionError("SkillsMiddleware requires a valid backend instance")
            return backend

        return self._backend

    def _format_skills_locations(self) -> str:
        """Format skills locations for display in system prompt."""
        locations = []
        for i, source_path in enumerate(self.sources):
            name = PurePosixPath(source_path.rstrip("/")).name.capitalize()
            suffix = " (higher priority)" if i == len(self.sources) - 1 else ""
            locations.append(f"**{name} Skills**: `{source_path}`{suffix}")
        return "\n".join(locations)

    def _format_skills_list(self, skills: list[SkillMetadata]) -> str:
        """Format skills metadata for display in system prompt."""
        if not skills:
            paths = [f"{source_path}" for source_path in self.sources]
            return f"(No skills available yet. You can create skills in {' or '.join(paths)})"

        lines = []
        for skill in skills:
            lines.append(f"- **{skill['name']}**: {skill['description']}")
            if skill["allowed_tools"]:
                lines.append(f"  -> Allowed tools: {', '.join(skill['allowed_tools'])}")
            lines.append(f"  -> Read `{skill['path']}` for full instructions")

        return "\n".join(lines)

    def modify_request(self, request: ModelRequest) -> ModelRequest:
        """Inject skills documentation into a model request's system message.

        Args:
            request: Model request to modify

        Returns:
            New model request with skills documentation injected into system message
        """
        skills_metadata = request.state.get("skills_metadata", [])
        skills_locations = self._format_skills_locations()
        skills_list = self._format_skills_list(skills_metadata)

        skills_section = self.system_prompt_template.format(
            skills_locations=skills_locations,
            skills_list=skills_list,
        )

        new_system_message = append_to_system_message(request.system_message, skills_section)

        return request.override(system_message=new_system_message)

    def before_agent(self, state: SkillsState, runtime: Runtime, config: RunnableConfig) -> SkillsStateUpdate | None:
        """Load skills metadata before agent execution (synchronous).

        Runs before each agent interaction to discover available skills from all
        configured sources. Re-loads on every call to capture any changes.

        Skills are loaded in source order with later sources overriding
        earlier ones if they contain skills with the same name (last one wins).

        Args:
            state: Current agent state.
            runtime: Runtime context.
            config: Runnable config.

        Returns:
            State update with `skills_metadata` populated, or `None` if already present
        """
        # Skip if skills_metadata is already present in state (even if empty)
        if "skills_metadata" in state:
            return None

        # Resolve backend (supports both direct instances and factory functions)
        backend = self._get_backend(state, runtime, config)
        all_skills: dict[str, SkillMetadata] = {}

        # Load skills from each source in order
        # Later sources override earlier ones (last one wins)
        for source_path in self.sources:
            source_skills = _list_skills(backend, source_path)
            for skill in source_skills:
                all_skills[skill["name"]] = skill

        skills = list(all_skills.values())
        return SkillsStateUpdate(skills_metadata=skills)

    async def abefore_agent(self, state: SkillsState, runtime: Runtime, config: RunnableConfig) -> SkillsStateUpdate | None:
        """Load skills metadata before agent execution (async).

        Runs before each agent interaction to discover available skills from all
        configured sources. Re-loads on every call to capture any changes.

        Skills are loaded in source order with later sources overriding
        earlier ones if they contain skills with the same name (last one wins).

        Args:
            state: Current agent state.
            runtime: Runtime context.
            config: Runnable config.

        Returns:
            State update with `skills_metadata` populated, or `None` if already present
        """
        # Skip if skills_metadata is already present in state (even if empty)
        if "skills_metadata" in state:
            return None

        # Resolve backend (supports both direct instances and factory functions)
        backend = self._get_backend(state, runtime, config)
        all_skills: dict[str, SkillMetadata] = {}

        # Load skills from each source in order
        # Later sources override earlier ones (last one wins)
        for source_path in self.sources:
            source_skills = await _alist_skills(backend, source_path)
            for skill in source_skills:
                all_skills[skill["name"]] = skill

        skills = list(all_skills.values())
        return SkillsStateUpdate(skills_metadata=skills)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject skills documentation into the system prompt.

        Args:
            request: Model request being processed
            handler: Handler function to call with modified request

        Returns:
            Model response from handler
        """
        modified_request = self.modify_request(request)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Inject skills documentation into the system prompt (async version).

        Args:
            request: Model request being processed
            handler: Async handler function to call with modified request

        Returns:
            Model response from handler
        """
        modified_request = self.modify_request(request)
        return await handler(modified_request)


__all__ = ["SkillMetadata", "SkillsMiddleware"]
