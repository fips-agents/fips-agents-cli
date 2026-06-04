"""Vendor command for copying fipsagents source into an agent project."""

import sys
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

AGENT_TEMPLATE_URL = "https://github.com/fips-agents/agent-template"


@click.command("vendor")
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Update an already-vendored project with the latest fipsagents source",
)
@click.option(
    "--version",
    "tag",
    default=None,
    help="Vendor a specific version (e.g., fipsagents-v0.7.0). Default: latest main.",
)
def vendor(update: bool, tag: str | None):
    """
    Vendor fipsagents source into the current project.

    Copies the fipsagents framework source code into src/fipsagents/ so you
    have full control over the framework. Replaces the PyPI dependency with
    the individual packages that fipsagents depends on.

    Use --update to refresh an already-vendored project with the latest
    upstream source. Commit your changes first — update overwrites the
    vendored source.

    Examples:

        fips-agents vendor

        fips-agents vendor --version fipsagents-v0.7.0

        fips-agents vendor --update
    """
    try:
        project_path = Path.cwd()

        # Verify we're in a project directory
        pyproject_path = project_path / "pyproject.toml"
        if not pyproject_path.exists():
            console.print("[red]✗[/red] No pyproject.toml found. Run this from a project root.")
            sys.exit(1)

        vendored_marker = project_path / "src" / "fipsagents" / "VENDORED"
        is_already_vendored = vendored_marker.exists()

        if update and not is_already_vendored:
            console.print(
                "[red]✗[/red] Project is not vendored yet. "
                "Run 'fips-agents vendor' (without --update) first."
            )
            sys.exit(1)

        if is_already_vendored and not update:
            # Show current version and ask if they want to update
            console.print("[yellow]⚠[/yellow] fipsagents is already vendored in this project.")
            console.print(f"  Marker: {vendored_marker}")
            console.print("  Use --update to refresh from upstream.")
            sys.exit(0)

        # Warn about overwriting local changes
        if update:
            console.print(
                "\n[yellow]⚠[/yellow] This will overwrite src/fipsagents/ with " "upstream source."
            )
            console.print(
                "  Commit any local modifications first to preserve them in git history.\n"
            )

        console.print("[bold cyan]Vendoring fipsagents[/bold cyan]\n")

        # Clone the agent-template repo
        import git as gitmodule

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "repo"

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Cloning agent-template repo...", total=None)
                try:
                    repo = gitmodule.Repo.clone_from(
                        AGENT_TEMPLATE_URL,
                        str(tmp_path),
                        branch="main",
                        depth=1,
                        single_branch=True,
                    )

                    # Checkout specific tag if requested
                    if tag:
                        try:
                            repo.git.fetch("origin", f"refs/tags/{tag}:refs/tags/{tag}")
                            repo.git.checkout(tag)
                            console.print(f"[green]✓[/green] Checked out tag: {tag}")
                        except gitmodule.GitCommandError:
                            console.print(
                                f"[red]✗[/red] Tag '{tag}' not found. "
                                f"Available tags: fipsagents-v0.7.0, etc."
                            )
                            sys.exit(1)

                except gitmodule.GitCommandError as e:
                    console.print(f"[red]✗[/red] Failed to clone: {e}")
                    sys.exit(1)

            # Copy the fipsagents source
            from fips_agents_cli.tools.project import (
                rewrite_pyproject_for_vendored,
                vendor_fipsagents_from_clone,
            )

            vendor_fipsagents_from_clone(tmp_path, project_path)

            # Only rewrite pyproject.toml if not already vendored
            # (on --update, deps are already rewritten)
            if not is_already_vendored:
                rewrite_pyproject_for_vendored(project_path)

        # Read commit from VENDORED marker
        vendored_commit = "unknown"
        marker_path = project_path / "src" / "fipsagents" / "VENDORED"
        if marker_path.exists():
            for line in marker_path.read_text().splitlines():
                if line.startswith("commit_short:"):
                    vendored_commit = line.split(":", 1)[1].strip()
                    break

        # Success
        console.print(
            f"\n[bold green]Vendoring complete![/bold green] (commit {vendored_commit})\n"
        )
        console.print("Next steps:")
        console.print("  1. pip install -e .          # Reinstall with vendored source")
        console.print("  2. make test                 # Verify everything works")
        console.print("  3. git add src/fipsagents/   # Commit the vendored source")
        console.print("")
        if update:
            console.print(
                "[dim]Tip: Use 'git diff src/fipsagents/' to review upstream changes.[/dim]"
            )

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e}")
        sys.exit(1)
