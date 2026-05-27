from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from fips_agents_cli.tools.openshift import (
    create_build_context,
    create_namespace,
    helm_deploy,
    is_helm_installed,
    is_mac_platform,
    is_oc_authenticated,
    is_oc_installed,
    namespace_exists,
    oc_get_route_url,
    oc_rollout_restart,
    oc_rollout_status,
    oc_start_build,
    read_helm_values,
)
from fips_agents_cli.tools.patching import get_project_type
from fips_agents_cli.tools.validation import find_fips_project_root

console = Console()

SUPPORTED_DEPLOY_TYPES = {
    "mcp-server": "OpenShift binary build",
    "agent": "Helm chart deploy",
    "workflow": "Helm chart deploy",
}


@click.command("deploy")
@click.option("--namespace", "-n", default=None, help="Target namespace (default: project name)")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Show what would happen without executing"
)
@click.option("--context", default=None, help="OpenShift/Kubernetes context")
def deploy(namespace, dry_run, context):
    """Deploy fips-agents project to OpenShift."""
    console.print("\n[bold cyan]Deploying to OpenShift[/bold cyan]\n")

    result = find_fips_project_root()
    if result is None:
        console.print("[red]✗[/red] Not in a fips-agents project directory")
        console.print("[dim]Run this command from within a fips-agents project[/dim]")
        sys.exit(1)

    project_root, template_info = result

    project_name = template_info.get("project", {}).get("name", project_root.name)
    project_type = get_project_type(template_info)

    if project_type not in SUPPORTED_DEPLOY_TYPES:
        console.print(f"[red]✗[/red] Project type '{project_type}' does not support deployment")
        console.print(f"[dim]Supported types: {', '.join(SUPPORTED_DEPLOY_TYPES.keys())}[/dim]")
        sys.exit(1)

    console.print(f"[green]✓[/green] Project: [bold]{project_name}[/bold]")
    console.print(f"[green]✓[/green] Type: {project_type}")
    console.print(f"[green]✓[/green] Root: {project_root}\n")

    target_namespace = namespace or project_name

    if not is_oc_installed():
        console.print("[red]✗[/red] OpenShift CLI (oc) not found")
        console.print(
            "[dim]Install from https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html[/dim]"
        )
        sys.exit(1)

    is_authenticated, auth_message = is_oc_authenticated(context)
    if not is_authenticated:
        console.print(f"[red]✗[/red] {auth_message}")
        console.print("[dim]Run: oc login <cluster-url>[/dim]")
        sys.exit(1)

    console.print("[green]✓[/green] Authenticated to OpenShift")

    if not namespace_exists(target_namespace, context):
        if dry_run:
            console.print(f"[cyan]Would create namespace: {target_namespace}[/cyan]")
        else:
            if click.confirm(f"Namespace '{target_namespace}' does not exist. Create it?"):
                success, message = create_namespace(target_namespace, context)
                if not success:
                    console.print(f"[red]✗[/red] Failed to create namespace: {message}")
                    sys.exit(1)
                console.print(f"[green]✓[/green] Created namespace: {target_namespace}")
            else:
                console.print("[yellow]⚠[/yellow] Deployment cancelled")
                sys.exit(0)
    else:
        console.print(f"[green]✓[/green] Namespace exists: {target_namespace}\n")

    if project_type == "mcp-server":
        _deploy_mcp_server(project_root, project_name, target_namespace, context, dry_run)
    elif project_type in ("agent", "workflow"):
        _deploy_agent(project_root, project_name, target_namespace, context, dry_run)


def _deploy_mcp_server(
    project_root: Path, project_name: str, namespace: str, oc_context: str | None, dry_run: bool
):
    if is_mac_platform():
        console.print(
            "[yellow]⚠[/yellow] Building on macOS: ensure BuildConfig uses linux/amd64 platform\n"
        )

    build_name = f"{project_name}-build"

    if dry_run:
        console.print("[bold]Deployment plan:[/bold]")
        console.print(f"  1. Create build context from {project_root}")
        console.print(f"  2. Start build: {build_name}")
        console.print(f"  3. Restart deployment: {project_name}")
        console.print("  4. Wait for rollout status")
        console.print(f"  5. Get route URL for {project_name}")
        return

    context_dir = None
    try:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Creating build context...", total=None)
            success, message, context_dir = create_build_context(project_root)
            progress.update(task, completed=True)

        if not success:
            console.print(f"[red]✗[/red] Failed to create build context: {message}")
            sys.exit(1)

        console.print("[green]✓[/green] Build context created")

        console.print(f"\n[cyan]Starting build: {build_name}[/cyan]")
        success, message = oc_start_build(build_name, context_dir, namespace, oc_context)
        if not success:
            console.print(f"[red]✗[/red] Build failed: {message}")
            sys.exit(1)

        console.print("[green]✓[/green] Build completed\n")

        console.print(f"[cyan]Restarting deployment: {project_name}[/cyan]")
        success, message = oc_rollout_restart(project_name, namespace, oc_context)
        if not success:
            console.print(f"[red]✗[/red] Restart failed: {message}")
            sys.exit(1)

        console.print("[green]✓[/green] Deployment restarted\n")

        console.print("[cyan]Waiting for rollout status...[/cyan]")
        success, message = oc_rollout_status(project_name, namespace, oc_context)
        if not success:
            console.print(f"[yellow]⚠[/yellow] Rollout status check: {message}")
        else:
            console.print("[green]✓[/green] Rollout complete\n")

        success, url_or_error = oc_get_route_url(project_name, namespace, oc_context)
        route_url = url_or_error if success else "(no route found)"

        console.print(
            Panel(
                f"[bold green]MCP Server Deployed Successfully[/bold green]\n\n"
                f"Project: {project_name}\n"
                f"Namespace: {namespace}\n"
                f"Route: {route_url}",
                border_style="green",
            )
        )

    finally:
        if context_dir is not None:
            shutil.rmtree(context_dir, ignore_errors=True)


def _deploy_agent(
    project_root: Path, project_name: str, namespace: str, oc_context: str | None, dry_run: bool
):
    if not is_helm_installed():
        console.print("[red]✗[/red] Helm not found")
        console.print("[dim]Install from https://helm.sh/docs/intro/install/[/dim]")
        sys.exit(1)

    chart_dir = project_root / "chart"
    if not chart_dir.exists():
        console.print(f"[red]✗[/red] Chart directory not found: {chart_dir}")
        sys.exit(1)

    console.print(f"[green]✓[/green] Found Helm chart: {chart_dir}\n")

    values = read_helm_values(chart_dir)
    if values is None:
        console.print("[yellow]⚠[/yellow] Could not read values.yaml, using defaults")
        image_repo = None
        image_tag = "latest"
    else:
        image_config = values.get("image", {})
        image_repo = image_config.get("repository")
        image_tag = image_config.get("tag", "latest")

        if not image_repo or image_repo == "agent-template":
            console.print(
                "[yellow]⚠[/yellow] Image repository not configured or uses template default"
            )
            image_repo = click.prompt("Enter container image repository")

        if not image_tag:
            image_tag = click.prompt("Enter image tag", default="latest")

        console.print(f"[green]✓[/green] Image: {image_repo}:{image_tag}\n")

    if dry_run:
        console.print("[bold]Deployment plan:[/bold]")
        console.print(
            f"  helm upgrade --install {project_name} {chart_dir} "
            f"--namespace {namespace} --create-namespace"
        )
        if oc_context:
            console.print(f"  (using context: {oc_context})")
        return

    values_file = chart_dir / "values.yaml" if (chart_dir / "values.yaml").exists() else None

    console.print("[cyan]Deploying with Helm...[/cyan]")
    success, message = helm_deploy(project_name, chart_dir, namespace, values_file, oc_context)
    if not success:
        console.print(f"[red]✗[/red] Helm deployment failed: {message}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold green]Agent Deployed Successfully[/bold green]\n\n"
            f"Project: {project_name}\n"
            f"Namespace: {namespace}\n"
            f"Release: {project_name}\n\n"
            f"Check status: helm status {project_name} -n {namespace}",
            border_style="green",
        )
    )
