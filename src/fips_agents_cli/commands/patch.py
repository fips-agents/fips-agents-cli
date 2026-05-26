"""Patch command for updating projects from template changes."""

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from fips_agents_cli.tools.patching import (
    PatchUnsupportedForProjectType,
    check_for_updates,
    discover_manifest_categories,
    get_available_categories,
    get_project_type,
    patch_category,
)
from fips_agents_cli.tools.validation import find_fips_project_root

console = Console()


@click.group()
def patch():
    """Update project files from template repository changes."""
    pass


@patch.command("check")
def check():
    """
    Check for available updates from the template repository.

    Shows what files have changed in the template since project creation.
    """
    console.print("\n[bold cyan]Checking for Template Updates[/bold cyan]\n")

    found = find_fips_project_root()
    if not found:
        console.print(
            "[red]✗[/red] Not in a project directory\n"
            "[yellow]Hint:[/yellow] Run this command from within a project created by fips-agents"
        )
        sys.exit(1)
    project_root, template_info = found

    console.print("[green]✓[/green] Project created from template")
    console.print(f"  Template: {template_info['template']['url']}")
    console.print(f"  Template commit: {template_info['template']['commit']}")
    console.print(f"  Created: {template_info['project']['created_at']}\n")

    # Check for updates
    try:
        updates = check_for_updates(project_root, template_info)
    except PatchUnsupportedForProjectType as e:
        console.print(f"\n[red]✗[/red] {e}")
        sys.exit(1)

    if not updates:
        console.print("[green]✓[/green] Project is up to date with latest template!")
        sys.exit(0)

    # Display available updates by category
    table = Table(title="Available Updates")
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Files Changed", style="yellow")
    table.add_column("Description", style="dim")

    for category, info in updates.items():
        table.add_row(category, str(len(info["files"])), info["description"])

    console.print(table)
    console.print("\n[dim]Run [cyan]fips-agents patch <category>[/cyan] to apply updates[/dim]")


@patch.command("generators")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
def generators(dry_run: bool):
    """
    Update code generator templates from the latest template repository.

    This includes Jinja2 templates in .fips-agents-cli/generators/
    """
    _patch_category("generators", dry_run)


@patch.command("core")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
def core(dry_run: bool):
    """
    Update core infrastructure files (loaders, server bootstrap, etc).

    Shows diffs and asks for confirmation before applying changes.
    """
    _patch_category("core", dry_run)


@patch.command("docs")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
def docs(dry_run: bool):
    """
    Update documentation files and examples.
    """
    _patch_category("docs", dry_run)


@patch.command("build")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
def build(dry_run: bool):
    """
    Update build and deployment files (Makefile, Containerfile, etc).

    Shows diffs and asks for confirmation before applying changes.
    """
    _patch_category("build", dry_run)


@patch.command("chart")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
def chart(dry_run: bool):
    """
    Update Helm chart templates (agent / workflow projects only).

    Patches files under chart/templates/ and chart/Chart.yaml.
    chart/values.yaml is never patched (user-customized).
    """
    _patch_category("chart", dry_run)


@patch.command("claude")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
def claude(dry_run: bool):
    """
    Update Claude Code slash commands and rules.

    Patches files under .claude/commands/ that ship with the template.
    For agent / workflow projects also patches .claude/rules/.
    """
    _patch_category("claude", dry_run)


@patch.command("evals")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
def evals(dry_run: bool):
    """
    Update the eval harness (agent / workflow projects only).

    Patches discovery / assertions / runner / mock_factory under evals/.
    evals/evals.yaml and evals/fixtures/ are user-authored and never
    patched.
    """
    _patch_category("evals", dry_run)


@patch.command("all")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
@click.option(
    "--skip-confirmation",
    is_flag=True,
    help="Skip confirmation prompts (use with caution)",
)
def all_categories(dry_run: bool, skip_confirmation: bool):
    """
    Update all patchable files from the template repository.

    This will interactively show diffs for files that may be customized.
    """
    console.print("\n[bold cyan]Patching All Categories[/bold cyan]\n")

    found = find_fips_project_root()
    if not found:
        console.print(
            "[red]✗[/red] Not in a project directory\n"
            "[yellow]Hint:[/yellow] Run this command from within a project created by fips-agents"
        )
        sys.exit(1)
    _, template_info = found
    project_type = get_project_type(template_info)

    # Enumerate categories for the project type. Types with built-in constants
    # (mcp-server, agent, workflow) resolve instantly. Manifest-only types
    # (agent-team) require cloning the template to read .fips-template.yaml.
    try:
        categories = get_available_categories(project_type)
    except ValueError:
        console.print(
            f"[cyan]No built-in categories for '{project_type}' — "
            "checking template manifest...[/cyan]"
        )
        categories = discover_manifest_categories(template_info)
        if categories is None:
            console.print(
                f"\n[red]✗[/red] Patching is not supported for project type "
                f"'{project_type}'. The template repo does not ship a "
                f".fips-template.yaml manifest, and no built-in category set "
                f"exists. See "
                f"https://github.com/fips-agents/fips-agents-cli/issues/45."
            )
            sys.exit(1)

    if not skip_confirmation:
        confirm = click.confirm("This will update multiple files. Continue?", default=True)
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            sys.exit(0)

    for category in categories:
        console.print(f"\n[bold]Processing category: {category}[/bold]")
        _patch_category(category, dry_run, skip_confirmation=skip_confirmation)


def _patch_category(category: str, dry_run: bool, skip_confirmation: bool = False):
    """
    Internal helper to patch a specific category.

    Args:
        category: Category name (generators, core, docs, etc.)
        dry_run: If True, only show what would be changed
        skip_confirmation: If True, don't ask for confirmation
    """
    found = find_fips_project_root()
    if not found:
        console.print(
            "[red]✗[/red] Not in a project directory\n"
            "[yellow]Hint:[/yellow] Run this command from within a project created by fips-agents"
        )
        sys.exit(1)
    project_root, template_info = found

    # Perform patch
    success, message = patch_category(
        project_root, template_info, category, dry_run, skip_confirmation
    )

    if success:
        if dry_run:
            console.print(f"\n[cyan]Dry run completed for '{category}'[/cyan]")
        else:
            console.print(Panel(message, border_style="green", padding=(1, 2)))
    else:
        console.print(f"\n[red]✗[/red] {message}")
        sys.exit(1)
