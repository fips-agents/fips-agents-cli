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
    oc_apply_manifest,
    oc_get_imagestream_registry_path,
    oc_get_route_url,
    oc_new_build,
    oc_rollout_status,
    oc_set_image,
    oc_start_build,
    parse_manifest_resource_names,
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
@click.option(
    "--set",
    "set_values",
    multiple=True,
    help="Set Helm values (key=value), can be specified multiple times",
)
@click.option(
    "--route/--no-route", default=True, help="Enable route for external access (default: enabled)"
)
def deploy(namespace, dry_run, context, set_values, route):
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
        _deploy_agent(
            project_root, project_name, target_namespace, context, dry_run, set_values, route
        )


def _deploy_mcp_server(
    project_root: Path, project_name: str, namespace: str, oc_context: str | None, dry_run: bool
):
    if is_mac_platform():
        console.print(
            "[yellow]⚠[/yellow] Building on macOS: ensure BuildConfig uses linux/amd64 platform\n"
        )

    # Determine resource names from openshift.yaml or fall back to project name
    manifest_path = project_root / "openshift.yaml"
    if manifest_path.exists():
        resource_names = parse_manifest_resource_names(manifest_path)
        build_name = resource_names.get("BuildConfig", f"{project_name}-build")
        deployment_name = resource_names.get("Deployment", project_name)
        route_name = resource_names.get("Route", deployment_name)
        has_manifest = True
    else:
        build_name = f"{project_name}-build"
        deployment_name = project_name
        route_name = project_name
        has_manifest = False

    if dry_run:
        console.print("[bold]Deployment plan:[/bold]")
        step = 1
        if has_manifest:
            console.print(f"  {step}. Apply manifest: {manifest_path.name}")
            step += 1
        console.print(f"  {step}. Create build context from {project_root}")
        step += 1
        console.print(f"  {step}. Start build: {build_name}")
        step += 1
        console.print(
            f"  {step}. Resolve ImageStream and update deployment image: {deployment_name}"
        )
        step += 1
        console.print(f"  {step}. Wait for rollout status")
        step += 1
        console.print(f"  {step}. Get route URL for {route_name}")
        return

    context_dir = None
    try:
        # Apply manifest if present
        if has_manifest:
            console.print(f"[cyan]Applying manifest: {manifest_path.name}[/cyan]")
            success, message = oc_apply_manifest(manifest_path, namespace, oc_context)
            if not success:
                console.print(f"[red]✗[/red] Failed to apply manifest: {message}")
                sys.exit(1)
            console.print("[green]✓[/green] Manifest applied\n")

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

        # Resolve ImageStream to get the full internal registry path, then
        # update the deployment image.  A plain `rollout restart` would
        # re-use the bare image name from openshift.yaml (e.g.
        # "mcp-server:latest") which can't be pulled — it needs the full
        # registry path that the ImageStream provides.
        imagestream_name = resource_names.get("ImageStream", build_name) if has_manifest else None
        if imagestream_name:
            console.print(f"[cyan]Resolving ImageStream: {imagestream_name}[/cyan]")
            found, resolved = oc_get_imagestream_registry_path(
                imagestream_name, namespace, oc_context
            )
            if found:
                full_image = f"{resolved}:latest"
                console.print(f"[green]✓[/green] Resolved image: {full_image}")
                console.print(f"[cyan]Updating deployment image: {deployment_name}[/cyan]")
                success, message = oc_set_image(
                    deployment_name, deployment_name, full_image, namespace, oc_context
                )
                if not success:
                    console.print(f"[red]✗[/red] Failed to update image: {message}")
                    sys.exit(1)
                console.print("[green]✓[/green] Deployment image updated\n")
            else:
                console.print(f"[yellow]⚠[/yellow] Could not resolve ImageStream: {resolved}")
                console.print("[yellow]⚠[/yellow] Skipping deployment update")
        else:
            console.print("[yellow]⚠[/yellow] No ImageStream found, skipping image update")

        console.print("[cyan]Waiting for rollout status...[/cyan]")
        success, message = oc_rollout_status(deployment_name, namespace, oc_context)
        if not success:
            console.print(f"[yellow]⚠[/yellow] Rollout status check: {message}")
        else:
            console.print("[green]✓[/green] Rollout complete\n")

        success, url_or_error = oc_get_route_url(route_name, namespace, oc_context)
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
    project_root: Path,
    project_name: str,
    namespace: str,
    oc_context: str | None,
    dry_run: bool,
    set_values: tuple[str, ...],
    route: bool,
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

    if is_mac_platform():
        console.print(
            "[yellow]⚠[/yellow] Building on macOS: ensure BuildConfig uses linux/amd64 platform\n"
        )

    values = read_helm_values(chart_dir)
    if values is None:
        console.print("[yellow]⚠[/yellow] Could not read values.yaml, using defaults")
        image_repo = None
    else:
        image_config = values.get("image", {})
        image_repo = image_config.get("repository")

    # Build the list of --set values to pass to Helm
    helm_set_values = list(set_values)

    # Bug fix: if any --set targets a key under a null YAML map (e.g.
    # ``config: # only comments``  which parses as ``config: null``),
    # Helm's --set will fail with "interface conversion: interface {} is
    # nil, not map[interface {}]".  Pre-initialise those top-level keys
    # to empty maps so --set can drill into them.
    if values is not None:
        _ensure_nonempty_maps_for_set_values(chart_dir, values, helm_set_values)

    build_name = project_name

    if dry_run:
        console.print("[bold]Deployment plan:[/bold]")
        step = 1
        console.print(f"  {step}. Create binary BuildConfig: {build_name}")
        step += 1
        console.print(f"  {step}. Create build context from {project_root}")
        step += 1
        console.print(f"  {step}. Start build: {build_name}")
        step += 1
        console.print(f"  {step}. Resolve ImageStream: {build_name}")
        step += 1
        helm_cmd = (
            f"  {step}. helm upgrade --install {project_name} {chart_dir} "
            f"--namespace {namespace}"
        )
        console.print(helm_cmd)
        for sv in helm_set_values:
            console.print(f"      --set {sv}")
        step += 1
        if route:
            console.print(f"  {step}. Get route URL for {project_name}")
        if oc_context:
            console.print(f"  (using context: {oc_context})")
        return

    context_dir = None
    try:
        # --- Build pipeline (mirrors _deploy_mcp_server) ---
        console.print(f"[cyan]Creating BuildConfig: {build_name}[/cyan]")
        success, message = oc_new_build(build_name, namespace, oc_context)
        if not success:
            console.print(f"[red]✗[/red] Failed to create BuildConfig: {message}")
            sys.exit(1)
        console.print(f"[green]✓[/green] BuildConfig ready: {build_name}\n")

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

        # Resolve ImageStream to get the full internal registry path
        console.print(f"[cyan]Resolving ImageStream: {build_name}[/cyan]")
        found, resolved = oc_get_imagestream_registry_path(build_name, namespace, oc_context)
        if found:
            full_image = f"{resolved}:latest"
            console.print(f"[green]✓[/green] Resolved image: {full_image}")
            helm_set_values.append(f"image.repository={resolved}")
            helm_set_values.append("image.tag=latest")
        else:
            console.print(f"[yellow]⚠[/yellow] Could not resolve ImageStream: {resolved}")
            if image_repo:
                console.print(f"[yellow]⚠[/yellow] Falling back to values.yaml image: {image_repo}")

        # --- Helm deploy ---
        # Enable route by default
        if route:
            helm_set_values.append("route.enabled=true")

        values_file = chart_dir / "values.yaml" if (chart_dir / "values.yaml").exists() else None

        console.print("[cyan]Deploying with Helm...[/cyan]")
        success, message = helm_deploy(
            project_name, chart_dir, namespace, values_file, oc_context, helm_set_values or None
        )
        if not success:
            console.print(f"[red]✗[/red] Helm deployment failed: {message}")
            sys.exit(1)

        # Query route URL if route was enabled
        route_url = None
        if route:
            success, url_or_error = oc_get_route_url(project_name, namespace, oc_context)
            route_url = url_or_error if success else None

        route_line = f"\nRoute: {route_url}" if route_url else ""

        console.print(
            Panel(
                f"[bold green]Agent Deployed Successfully[/bold green]\n\n"
                f"Project: {project_name}\n"
                f"Namespace: {namespace}\n"
                f"Release: {project_name}"
                f"{route_line}\n\n"
                f"Check status: helm status {project_name} -n {namespace}",
                border_style="green",
            )
        )

    finally:
        if context_dir is not None:
            shutil.rmtree(context_dir, ignore_errors=True)


def _ensure_nonempty_maps_for_set_values(
    chart_dir: Path, values: dict, set_values: list[str]
) -> None:
    """Patch values.yaml in-place to replace null top-level keys with ``{}``
    when ``--set`` targets sub-keys beneath them.

    Helm's ``--set config.FOO=bar`` fails when the values file has
    ``config:`` with only comments (YAML null).  We detect which top-level
    keys are null yet targeted by a ``--set`` dotted path, and rewrite those
    entries to empty maps so Helm can merge into them.
    """
    from ruamel.yaml import YAML

    # Collect top-level keys targeted by dotted --set paths
    targeted_keys: set[str] = set()
    for sv in set_values:
        key_part = sv.split("=", 1)[0] if "=" in sv else sv
        parts = key_part.split(".")
        if len(parts) > 1:
            targeted_keys.add(parts[0])

    # Find which targeted keys are null in current values
    null_keys = {k for k in targeted_keys if k in values and values[k] is None}
    if not null_keys:
        return

    values_file = chart_dir / "values.yaml"
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(values_file) as f:
        data = yaml.load(f)

    changed = False
    for key in null_keys:
        if key in data and data[key] is None:
            data[key] = {}
            changed = True

    if changed:
        with open(values_file, "w") as f:
            yaml.dump(data, f)
