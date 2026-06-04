"""Project customization and configuration utilities."""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import tomlkit
from rich.console import Console

from fips_agents_cli.version import __version__

console = Console()


def validate_project_name(name: str) -> tuple[bool, str | None]:
    """
    Validate project name according to Python package naming conventions.

    Project names must:
    - Start with a lowercase letter
    - Contain only lowercase letters, numbers, hyphens, and underscores
    - Not be empty

    Args:
        name: The project name to validate

    Returns:
        tuple: (is_valid, error_message)
               is_valid is True if valid, False otherwise
               error_message is None if valid, otherwise contains the error description
    """
    if not name:
        return False, "Project name cannot be empty"

    if not re.match(r"^[a-z][a-z0-9\-_]*$", name):
        return False, (
            "Project name must start with a lowercase letter and contain only "
            "lowercase letters, numbers, hyphens, and underscores"
        )

    return True, None


def to_module_name(project_name: str) -> str:
    """
    Convert a project name to a valid Python module name.

    Replaces hyphens with underscores to ensure compatibility with Python imports.

    Args:
        project_name: The project name (may contain hyphens)

    Returns:
        str: A valid Python module name (hyphens replaced with underscores)
    """
    return project_name.replace("-", "_")


def update_project_name(project_path: Path, new_name: str) -> None:
    """
    Update the project name in pyproject.toml and rename the source directory.

    This function:
    1. Updates the 'name' field in pyproject.toml
    2. Updates the entry point script name if present
    3. Renames the source directory from the template name to the new module name

    Args:
        project_path: Path to the project root directory
        new_name: The new project name (with hyphens allowed)

    Raises:
        FileNotFoundError: If pyproject.toml or source directory doesn't exist
        ValueError: If pyproject.toml is malformed
    """
    try:
        console.print(f"[cyan]Customizing project for '{new_name}'...[/cyan]")

        pyproject_path = project_path / "pyproject.toml"

        if not pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

        # Read and parse pyproject.toml
        with open(pyproject_path) as f:
            pyproject = tomlkit.parse(f.read())

        # Get the old project name from pyproject.toml
        old_name = pyproject.get("project", {}).get("name", "fastmcp-unified-template")
        old_module_name = to_module_name(old_name)
        new_module_name = to_module_name(new_name)

        # Update project name
        if "project" in pyproject:
            pyproject["project"]["name"] = new_name

            # Update entry point script name if it exists
            if "scripts" in pyproject["project"]:
                # Find and update any entry points that reference the old name
                scripts = pyproject["project"]["scripts"]
                old_scripts = dict(scripts)

                for script_name, script_path in old_scripts.items():
                    # Replace old module name with new module name in the path
                    # (but only if it's actually in the path - new template uses src.main:main)
                    new_script_path = script_path.replace(old_module_name, new_module_name)

                    # Update the script name to match the new project name
                    if script_name == old_name or script_name == old_module_name:
                        del scripts[script_name]
                        scripts[new_name] = new_script_path
                    else:
                        # Keep the same script name but update the path if needed
                        scripts[script_name] = new_script_path

        # Write updated pyproject.toml
        with open(pyproject_path, "w") as f:
            f.write(tomlkit.dumps(pyproject))

        console.print("[green]✓[/green] Updated pyproject.toml")

        # Rename source directory (for templates with single-module structure)
        src_dir = project_path / "src"
        old_src_path = src_dir / old_module_name
        new_src_path = src_dir / new_module_name

        if old_src_path.exists() and old_src_path != new_src_path:
            shutil.move(str(old_src_path), str(new_src_path))
            console.print(f"[green]✓[/green] Renamed source directory to '{new_module_name}'")
        elif not old_src_path.exists():
            # Template uses multi-module structure (core/, tools/, etc.)
            console.print(
                "[dim]Note: Template uses multi-module structure, no directory rename needed[/dim]"
            )

        console.print("[green]✓[/green] Project customization complete")

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to customize project: {e}")
        raise


def _replace_in_file(path: Path, old: str, new: str) -> None:
    """Replace all occurrences of a string in a file, if the file exists."""
    if path.exists():
        text = path.read_text()
        path.write_text(text.replace(old, new))


def customize_agent_project(
    project_path: Path,
    new_name: str,
    github_repo: str | None = None,
) -> None:
    """
    Customize an agent project with the new project name.

    Replaces 'agent-template' with the new project name across configuration
    files, Helm templates, and deploy scripts. Unlike MCP server projects,
    agent projects don't rename source directories (base_agent is a framework
    component, not the project module).

    Args:
        project_path: Path to the project root directory
        new_name: The new project name (with hyphens allowed)
        github_repo: GitHub repo in "owner/name" format for Containerfile label

    Raises:
        FileNotFoundError: If pyproject.toml doesn't exist
    """
    try:
        console.print(f"[cyan]Customizing agent project for '{new_name}'...[/cyan]")

        # 1. Update pyproject.toml name field (use tomlkit to preserve formatting)
        pyproject_path = project_path / "pyproject.toml"
        if not pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

        with open(pyproject_path) as f:
            pyproject = tomlkit.parse(f.read())

        if "project" in pyproject:
            pyproject["project"]["name"] = new_name

        with open(pyproject_path, "w") as f:
            f.write(tomlkit.dumps(pyproject))

        console.print("[green]✓[/green] Updated pyproject.toml")

        # 2. String-replace "agent-template" in supporting files and Helm templates
        files_to_update = [
            project_path / "chart" / "Chart.yaml",
            project_path / "chart" / "values.yaml",
            project_path / "chart" / "templates" / "_helpers.tpl",
            project_path / "chart" / "templates" / "deployment.yaml",
            project_path / "chart" / "templates" / "service.yaml",
            project_path / "chart" / "templates" / "configmap.yaml",
            project_path / "chart" / "templates" / "route.yaml",
            project_path / "chart" / "templates" / "NOTES.txt",
            project_path / "AGENTS.md",
            project_path / "Containerfile",
            project_path / "Makefile",
            project_path / "deploy.sh",
            project_path / "redeploy.sh",
        ]

        for file_path in files_to_update:
            _replace_in_file(file_path, "agent-template", new_name)

        console.print("[green]✓[/green] Updated configuration files")

        # 3. Remove monorepo-specific base-agent install line from Makefile
        # Cloned projects get fipsagents from PyPI, not a local path
        makefile_path = project_path / "Makefile"
        if makefile_path.exists():
            text = makefile_path.read_text()
            # Remove the monorepo install line and its comments
            lines = text.splitlines(keepends=True)
            filtered = []
            skip_block = False
            for line in lines:
                if "In the monorepo" in line:
                    skip_block = True
                    continue
                if skip_block and ("fips-agents" in line or "scaffolding step" in line):
                    continue
                if skip_block and ("$(PIP) install -e" in line and "packages/" in line):
                    skip_block = False
                    continue
                skip_block = False
                filtered.append(line)
            makefile_path.write_text("".join(filtered))

        console.print("[green]✓[/green] Cleaned up Makefile for standalone use")

        # 4. Replace OWNER/REPO placeholder in Containerfile image source label
        repo_value = github_repo if github_repo else f"OWNER/{new_name}"
        _replace_in_file(project_path / "Containerfile", "OWNER/REPO", repo_value)

        console.print("[green]✓[/green] Agent project customization complete")

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to customize agent project: {e}")
        raise


def customize_workflow_project(
    project_path: Path,
    new_name: str,
    github_repo: str | None = None,
) -> None:
    """
    Customize a workflow project with the new project name.

    Replaces 'workflow-template' with the new project name across configuration
    files, Helm templates, and deploy scripts. Also removes the monorepo-specific
    base-agent install line from the Makefile since cloned projects get fipsagents
    from PyPI.

    Args:
        project_path: Path to the project root directory
        new_name: The new project name (with hyphens allowed)
        github_repo: GitHub repo in "owner/name" format for Containerfile label

    Raises:
        FileNotFoundError: If pyproject.toml doesn't exist
    """
    try:
        console.print(f"[cyan]Customizing workflow project for '{new_name}'...[/cyan]")

        # 1. Update pyproject.toml name field (use tomlkit to preserve formatting)
        pyproject_path = project_path / "pyproject.toml"
        if not pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

        with open(pyproject_path) as f:
            pyproject = tomlkit.parse(f.read())

        if "project" in pyproject:
            pyproject["project"]["name"] = new_name

        with open(pyproject_path, "w") as f:
            f.write(tomlkit.dumps(pyproject))

        console.print("[green]✓[/green] Updated pyproject.toml")

        # 2. String-replace "workflow-template" in supporting files and Helm templates
        files_to_update = [
            project_path / "chart" / "Chart.yaml",
            project_path / "chart" / "values.yaml",
            project_path / "chart" / "templates" / "_helpers.tpl",
            project_path / "chart" / "templates" / "deployment.yaml",
            project_path / "chart" / "templates" / "service.yaml",
            project_path / "chart" / "templates" / "configmap.yaml",
            project_path / "chart" / "templates" / "route.yaml",
            project_path / "chart" / "templates" / "NOTES.txt",
            project_path / "AGENTS.md",
            project_path / "Containerfile",
            project_path / "Makefile",
            project_path / "deploy.sh",
        ]

        for file_path in files_to_update:
            _replace_in_file(file_path, "workflow-template", new_name)

        console.print("[green]✓[/green] Updated configuration files")

        # 3. Remove monorepo-specific base-agent install line from Makefile
        # Cloned projects get fipsagents from PyPI, not a local path
        makefile_path = project_path / "Makefile"
        if makefile_path.exists():
            text = makefile_path.read_text()
            # Remove the monorepo install line and its comments
            lines = text.splitlines(keepends=True)
            filtered = []
            skip_block = False
            for line in lines:
                if "In the monorepo" in line:
                    skip_block = True
                    continue
                if skip_block and ("fips-agents" in line or "scaffolding step" in line):
                    continue
                if skip_block and ("$(PIP) install -e" in line and "packages/" in line):
                    skip_block = False
                    continue
                skip_block = False
                filtered.append(line)
            makefile_path.write_text("".join(filtered))

        console.print("[green]✓[/green] Cleaned up Makefile for standalone use")

        # 4. Replace OWNER/REPO placeholder in Containerfile image source label
        repo_value = github_repo if github_repo else f"OWNER/{new_name}"
        _replace_in_file(project_path / "Containerfile", "OWNER/REPO", repo_value)

        console.print("[green]✓[/green] Workflow project customization complete")

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to customize workflow project: {e}")
        raise


def customize_sandbox_project(
    project_path: Path,
    new_name: str,
    github_repo: str | None = None,
) -> None:
    """
    Customize a sandbox project with the new project name.

    Replaces 'code-sandbox' with the new project name across configuration
    files, Helm templates, and build files. The Python package directory
    (sandbox/) is NOT renamed -- it stays as 'sandbox' regardless of
    project name.

    Args:
        project_path: Path to the project root directory
        new_name: The new project name (with hyphens allowed)
        github_repo: GitHub repo in "owner/name" format for Containerfile label

    Raises:
        FileNotFoundError: If pyproject.toml doesn't exist
    """
    try:
        console.print(f"[cyan]Customizing sandbox project for '{new_name}'...[/cyan]")

        # 1. Update pyproject.toml name field (use tomlkit to preserve formatting)
        pyproject_path = project_path / "pyproject.toml"
        if not pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

        with open(pyproject_path) as f:
            pyproject = tomlkit.parse(f.read())

        if "project" in pyproject:
            pyproject["project"]["name"] = new_name

        with open(pyproject_path, "w") as f:
            f.write(tomlkit.dumps(pyproject))

        console.print("[green]✓[/green] Updated pyproject.toml")

        # 2. String-replace "code-sandbox" in supporting files and Helm templates
        files_to_update = [
            project_path / "chart" / "Chart.yaml",
            project_path / "chart" / "values.yaml",
            project_path / "Makefile",
            project_path / "README.md",
            project_path / "CLAUDE.md",
            project_path / "Containerfile",
        ]

        # Also update all files in chart/templates/
        chart_templates_dir = project_path / "chart" / "templates"
        if chart_templates_dir.exists():
            for template_file in chart_templates_dir.iterdir():
                if template_file.is_file():
                    files_to_update.append(template_file)

        for file_path in files_to_update:
            _replace_in_file(file_path, "code-sandbox", new_name)

        console.print("[green]✓[/green] Updated configuration files")

        # 3. Replace OWNER/REPO placeholder in Containerfile image source label
        if github_repo:
            _replace_in_file(project_path / "Containerfile", "OWNER/REPO", github_repo)

        console.print("[green]✓[/green] Sandbox project customization complete")

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to customize sandbox project: {e}")
        raise


def customize_agent_team_project(
    project_path: Path,
    new_name: str,
    github_repo: str | None = None,
) -> None:
    """
    Customize an agent-team project with the new project name.

    Replaces 'agent-team-template' with the new project name across configuration
    files and build scripts. Also renames the source package directory from
    agent_team_design to the new module name, and updates entry point scripts
    in pyproject.toml.

    Args:
        project_path: Path to the project root directory
        new_name: The new project name (with hyphens allowed)
        github_repo: GitHub repo in "owner/name" format for Containerfile label

    Raises:
        FileNotFoundError: If pyproject.toml doesn't exist
    """
    try:
        console.print(f"[cyan]Customizing agent-team project for '{new_name}'...[/cyan]")

        # 1. Update pyproject.toml name field (use tomlkit to preserve formatting)
        pyproject_path = project_path / "pyproject.toml"
        if not pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

        with open(pyproject_path) as f:
            pyproject = tomlkit.parse(f.read())

        if "project" in pyproject:
            pyproject["project"]["name"] = new_name

        # 2. Update entry point scripts in pyproject.toml
        old_module_name = "agent_team_design"
        new_module_name = to_module_name(new_name)

        if "project" in pyproject and "scripts" in pyproject["project"]:
            scripts = pyproject["project"]["scripts"]
            old_scripts = dict(scripts)

            for script_name, script_path in old_scripts.items():
                # Replace old module name with new module name in the path
                new_script_path = script_path.replace(old_module_name, new_module_name)

                # Update the script name to match the new project name
                if script_name in (old_module_name, "agent-team-template", "agent-team-design"):
                    del scripts[script_name]
                    scripts[new_name] = new_script_path
                else:
                    # Keep the same script name but update the path if needed
                    scripts[script_name] = new_script_path

        with open(pyproject_path, "w") as f:
            f.write(tomlkit.dumps(pyproject))

        # Replace any remaining references to the old module name in pyproject.toml
        # (e.g., packages = ["src/agent_team_design"] in [tool.hatch.build])
        _replace_in_file(pyproject_path, old_module_name, new_module_name)

        console.print("[green]✓[/green] Updated pyproject.toml")

        # 3. Rename source directory agent_team_design → new module name
        src_dir = project_path / "src"
        old_src_path = src_dir / old_module_name
        new_src_path = src_dir / new_module_name

        if old_src_path.exists() and old_src_path != new_src_path:
            shutil.move(str(old_src_path), str(new_src_path))
            console.print(f"[green]✓[/green] Renamed source directory to '{new_module_name}'")
        elif not old_src_path.exists():
            console.print("[dim]Note: agent_team_design directory not found, skipping rename[/dim]")

        # 4. Find-and-replace agent_team_design in .py files outside the renamed package
        for py_file in project_path.rglob("*.py"):
            # Skip files inside the renamed package directory
            if new_src_path in py_file.parents:
                continue
            _replace_in_file(py_file, old_module_name, new_module_name)

        console.print("[green]✓[/green] Updated Python module references")

        # 5. String-replace project name sentinels in supporting files
        files_to_update = [
            project_path / "README.md",
            project_path / "CLAUDE.md",
            project_path / "Makefile",
            project_path / "Containerfile",
            project_path / "deploy.sh",
            project_path / "redeploy.sh",
        ]

        for file_path in files_to_update:
            _replace_in_file(file_path, "agent-team-design", new_name)
            _replace_in_file(file_path, "agent-team-template", new_name)
            _replace_in_file(file_path, old_module_name, new_module_name)

        console.print("[green]✓[/green] Updated configuration files")

        # 6. Replace OWNER/REPO placeholder in Containerfile image source label
        repo_value = github_repo if github_repo else f"OWNER/{new_name}"
        _replace_in_file(project_path / "Containerfile", "OWNER/REPO", repo_value)

        console.print("[green]✓[/green] Agent-team project customization complete")

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to customize agent-team project: {e}")
        raise


def customize_go_project(project_path: Path, new_name: str, sentinel: str) -> None:
    """
    Customize a Go-based template project with the new project name.

    Replaces the sentinel string with the new project name across configuration
    and build files. Unlike Python projects, Go projects don't have pyproject.toml
    or source directory renaming -- customization is purely string replacement.

    Args:
        project_path: Path to the project root directory
        new_name: The new project name (with hyphens allowed)
        sentinel: The template's placeholder string to replace (e.g. "gateway-template")
    """
    try:
        console.print(f"[cyan]Customizing Go project for '{new_name}'...[/cyan]")

        # go.mod is required -- fail if missing
        go_mod = project_path / "go.mod"
        if not go_mod.exists():
            raise FileNotFoundError(f"go.mod not found at {go_mod}")

        _replace_in_file(go_mod, sentinel, new_name)
        console.print("[green]✓[/green] Updated go.mod")

        # Configuration and build files (optional -- tolerate missing)
        optional_files = [
            project_path / "chart" / "Chart.yaml",
            project_path / "chart" / "values.yaml",
            project_path / "chart" / "templates" / "_helpers.tpl",
            project_path / "Containerfile",
            project_path / "Makefile",
            project_path / "README.md",
            project_path / "CLAUDE.md",
        ]

        for file_path in optional_files:
            _replace_in_file(file_path, sentinel, new_name)

        # Go source files -- replace import paths in all .go files
        for go_file in project_path.rglob("*.go"):
            _replace_in_file(go_file, sentinel, new_name)
        console.print("[green]✓[/green] Updated Go import paths")

        # Helm chart templates -- replace helper references in all chart templates
        chart_templates = project_path / "chart" / "templates"
        if chart_templates.exists():
            for tpl_file in chart_templates.glob("*.yaml"):
                _replace_in_file(tpl_file, sentinel, new_name)

        # Check HTML files in static/ for sentinels (e.g. <title> tags in UI templates)
        static_dir = project_path / "static"
        if static_dir.exists():
            for html_file in static_dir.glob("*.html"):
                _replace_in_file(html_file, sentinel, new_name)

        console.print("[green]✓[/green] Updated configuration files")
        console.print("[green]✓[/green] Go project customization complete")

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to customize Go project: {e}")
        raise


def find_agent_project_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` to locate an agent project root.

    Recognizes a directory as an agent project root when either is true:
      - It carries a ``.template-info`` file whose ``template.type`` is
        ``"agent"`` (preferred — this is what ``fips-agents create agent``
        writes since v0.8.x).
      - It contains an ``agent.yaml`` (legacy projects scaffolded before
        ``.template-info`` carried ``template.type``, plus hand-rolled
        agent projects that follow the template layout).

    The dual check matches the contract of the existing ``add code-executor``
    command (which only looked for ``agent.yaml``) while letting newer
    callers prefer the explicit ``.template-info`` signal.

    Args:
        start: Directory to begin walking from. Defaults to ``Path.cwd()``.

    Returns:
        Path to the agent project root, or ``None`` if no agent project is
        found in ``start`` or any of its parents.
    """
    cwd = start or Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        info_file = parent / ".template-info"
        if info_file.exists():
            try:
                with open(info_file) as f:
                    template_info = json.load(f)
                ptype = template_info.get("template", {}).get("type", "mcp-server")
                if ptype == "agent":
                    return parent
                # Wrong project type at this level — keep walking. A user could
                # be inside a subdir (e.g. examples/) of a non-agent project
                # that itself contains an agent project elsewhere upstream.
                continue
            except Exception:
                # Fall through to the agent.yaml legacy check below.
                pass
        if (parent / "agent.yaml").exists():
            return parent
    return None


def cleanup_template_files(project_path: Path) -> None:
    """
    Remove template-specific files that shouldn't be in the new project.

    Args:
        project_path: Path to the project root directory
    """
    # Files to remove (commonly found in templates)
    files_to_remove = [
        ".github/workflows/template-cleanup.yml",  # Template-specific workflows
    ]

    for file_path in files_to_remove:
        full_path = project_path / file_path
        if full_path.exists():
            try:
                full_path.unlink()
                console.print(f"[green]✓[/green] Removed template file: {file_path}")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not remove {file_path}: {e}")


def write_template_info(
    project_path: Path,
    project_name: str,
    template_url: str,
    template_commit: str,
    template_type: str,
    template_subdir: str | None = None,
    github_repo: str | None = None,
    github_url: str | None = None,
) -> None:
    """
    Write template generation metadata to .template-info file.

    Args:
        project_path: Path to the project root directory
        project_name: Name of the generated project
        template_url: URL of the template repository
        template_commit: Git commit hash of the template
        template_type: Project type ('mcp-server', 'agent', 'workflow',
            'gateway', 'ui', 'sandbox'). Read by `patch` to select the
            right file categories and exclusions.
        template_subdir: Subdirectory within the repo for monorepo templates
            (e.g. 'templates/agent-loop'). Omit for standalone repos.
        github_repo: GitHub repository in "owner/name" format (optional)
        github_url: Full URL to the GitHub repository (optional)
    """
    try:
        template_block = {
            "url": template_url,
            "type": template_type,
            "commit": template_commit[:12],  # Short hash
            "full_commit": template_commit,
        }
        if template_subdir:
            template_block["subdir"] = template_subdir

        template_info = {
            "generator": {"tool": "fips-agents-cli", "version": __version__},
            "template": template_block,
            "project": {
                "name": project_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # Add GitHub metadata if provided
        if github_repo or github_url:
            template_info["github"] = {}
            if github_repo:
                template_info["github"]["repo"] = github_repo
            if github_url:
                template_info["github"]["url"] = github_url

        info_file = project_path / ".template-info"
        with open(info_file, "w") as f:
            json.dump(template_info, f, indent=2)
            f.write("\n")  # Add trailing newline

        console.print("[green]✓[/green] Created template metadata file")

    except Exception as e:
        # Don't fail the entire operation if this fails
        console.print(f"[yellow]⚠[/yellow] Could not write template info: {e}")


def vendor_fipsagents_from_clone(
    clone_path: Path,
    project_path: Path,
) -> None:
    """
    Copy fipsagents package source from a monorepo clone into the project.

    Called as a post_clone_fn callback during clone_template_subdir() when
    --vendored is used, or directly by 'fips-agents vendor' for post-scaffold
    vendoring.

    Args:
        clone_path: Root of the cloned agent-template monorepo
        project_path: Root of the target project
    """
    pkg_src = clone_path / "packages" / "fipsagents" / "src" / "fipsagents"
    if not pkg_src.is_dir():
        console.print("[red]✗[/red] fipsagents package not found in template repo")
        raise FileNotFoundError(f"Expected fipsagents source at {pkg_src}")

    dest = project_path / "src" / "fipsagents"

    # Remove existing vendored source if present (for --update)
    if dest.exists():
        shutil.rmtree(dest)

    shutil.copytree(pkg_src, dest)
    console.print("[green]✓[/green] Copied fipsagents source to src/fipsagents/")

    # Copy upstream pyproject.toml as provenance record
    upstream_toml = clone_path / "packages" / "fipsagents" / "pyproject.toml"
    if upstream_toml.exists():
        shutil.copy2(upstream_toml, dest / "UPSTREAM.toml")

    # Read version from the vendored package
    version = "unknown"
    init_file = dest / "baseagent" / "__init__.py"
    if init_file.exists():
        for line in init_file.read_text().splitlines():
            if line.startswith("__version__"):
                version = line.split("=")[1].strip().strip('"').strip("'")
                break

    # Read HEAD commit from clone
    import git as gitmodule

    commit_full = "unknown"
    commit_short = "unknown"
    try:
        repo = gitmodule.Repo(str(clone_path))
        commit_full = repo.head.commit.hexsha
        commit_short = commit_full[:7]
    except Exception:
        pass

    # Write VENDORED marker
    marker = dest / "VENDORED"
    marker.write_text(
        f"version: {version}\n"
        f"vendored: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"source: https://github.com/fips-agents/agent-template\n"
        f"commit: {commit_full}\n"
        f"commit_short: {commit_short}\n"
        f"\n"
        f"This fipsagents source is vendored into the project.\n"
        f"To update: fips-agents vendor --update\n"
    )
    console.print(
        f"[green]✓[/green] Wrote VENDORED marker (version {version}, commit {commit_short})"
    )


def rewrite_pyproject_for_vendored(project_path: Path) -> None:
    """
    Rewrite pyproject.toml to replace fipsagents pip dependency with
    the individual dependencies that fipsagents itself declares.

    Args:
        project_path: Root of the target project
    """
    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.exists():
        return

    with open(pyproject_path) as f:
        pyproject = tomlkit.parse(f.read())

    # Replace fipsagents[server] with its individual dependencies
    vendored_deps = [
        "litellm>=1.83.0",
        "fastmcp>=3.0.0",
        "pydantic>=2.0",
        "pyyaml",
        "httpx",
        "python-frontmatter",
        "fastapi>=0.110",
        "uvicorn[standard]>=0.27",
    ]

    if "project" in pyproject and "dependencies" in pyproject["project"]:
        old_deps = list(pyproject["project"]["dependencies"])
        new_deps = [d for d in old_deps if "fipsagents" not in d.lower()]
        new_deps.extend(vendored_deps)
        pyproject["project"]["dependencies"] = new_deps

    # Fix optional memory dependency too
    if "project" in pyproject:
        opt_deps = pyproject["project"].get("optional-dependencies", {})
        if "memory" in opt_deps:
            old_memory = list(opt_deps["memory"])
            new_memory = [d for d in old_memory if "fipsagents" not in d.lower()]
            new_memory.append("memoryhub")
            opt_deps["memory"] = new_memory

    with open(pyproject_path, "w") as f:
        f.write(tomlkit.dumps(pyproject))

    console.print("[green]✓[/green] Updated pyproject.toml (vendored dependencies)")
