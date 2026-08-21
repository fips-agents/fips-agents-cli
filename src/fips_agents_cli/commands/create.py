"""Create command for generating new projects from templates."""

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from fips_agents_cli.commands.model_car import model_car
from fips_agents_cli.tools.filesystem import resolve_target_path, validate_target_directory
from fips_agents_cli.tools.git import (
    add_remote,
    clone_template,
    clone_template_subdir,
    init_repository,
    is_git_installed,
    push_to_remote,
)
from fips_agents_cli.tools.github import (
    check_gh_prerequisites,
    create_github_repo,
    get_github_username,
    is_gh_authenticated,
    is_gh_installed,
)
from fips_agents_cli.tools.project import (
    cleanup_template_files,
    customize_agent_project,
    customize_agent_team_project,
    customize_go_project,
    customize_provider,
    customize_sandbox_project,
    customize_workflow_project,
    to_module_name,
    update_project_name,
    validate_project_name,
    write_template_info,
)

console = Console()

# Template URLs — all repos live under github.com/fips-agents/
MCP_SERVER_TEMPLATE_URL = "https://github.com/fips-agents/mcp-server-template"

AGENT_TEMPLATE_URL = "https://github.com/fips-agents/agent-template"
AGENT_TEMPLATE_SUBDIR = "templates/agent-loop"
WORKFLOW_TEMPLATE_SUBDIR = "templates/workflow"

GATEWAY_TEMPLATE_URL = "https://github.com/fips-agents/gateway-template"
UI_TEMPLATE_URL = "https://github.com/fips-agents/ui-template"

SANDBOX_TEMPLATE_URL = "https://github.com/fips-agents/code-sandbox"
AGENT_TEAM_TEMPLATE_URL = "https://github.com/fips-agents/agent-team-template"


@click.group()
def create():
    """Create new projects from templates."""
    pass


# Register subcommands
create.add_command(model_car)


@create.command("mcp-server")
@click.argument("project_name")
@click.option(
    "--target-dir",
    "-t",
    default=None,
    help="Target directory for the project (default: current directory)",
)
@click.option(
    "--no-git",
    is_flag=True,
    default=False,
    help="Skip git repository initialization",
)
@click.option(
    "--github",
    "use_github",
    is_flag=True,
    default=False,
    help="Create GitHub repository and push code",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="Create local project only (skip GitHub)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive mode (use defaults, skip prompts)",
)
@click.option(
    "--private",
    is_flag=True,
    default=False,
    help="Make GitHub repository private (default: public)",
)
@click.option(
    "--org",
    default=None,
    help="GitHub organization to create repository in",
)
@click.option(
    "--description",
    "-d",
    "repo_description",
    default=None,
    help="GitHub repository description",
)
@click.option(
    "--remote-only",
    is_flag=True,
    default=False,
    help="Create GitHub repo only, don't clone locally",
)
def mcp_server(
    project_name: str,
    target_dir: str | None,
    no_git: bool,
    use_github: bool,
    use_local: bool,
    yes: bool,
    private: bool,
    org: str | None,
    repo_description: str | None,
    remote_only: bool,
):
    """
    Create a new MCP server project from template.

    PROJECT_NAME must start with a lowercase letter and contain only
    lowercase letters, numbers, hyphens, and underscores.

    By default, if GitHub CLI (gh) is installed and authenticated, prompts
    to create a GitHub repository. Use --local to skip this, or --github
    to require it. Use --yes for non-interactive mode (agents/CI).

    Examples:

        fips-agents create mcp-server my-mcp-server

        fips-agents create mcp-server my-mcp-server --github --private

        fips-agents create mcp-server my-mcp-server --local

        fips-agents create mcp-server my-mcp-server --yes  # Non-interactive
    """
    try:
        # Step 1: Validate options
        if use_github and use_local:
            console.print("[red]✗[/red] Cannot use --github and --local together")
            sys.exit(1)

        if remote_only and use_local:
            console.print("[red]✗[/red] Cannot use --remote-only with --local")
            sys.exit(1)

        # Step 2: Validate project name
        console.print("\n[bold cyan]Creating MCP Server Project[/bold cyan]\n")

        is_valid, error_msg = validate_project_name(project_name)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid project name: {error_msg}")
            sys.exit(1)

        console.print(f"[green]✓[/green] Project name '{project_name}' is valid")

        # Step 3: Check prerequisites (fail fast before any interactive prompts)
        if not is_git_installed():
            console.print(
                "[yellow]⚠[/yellow] Git is not installed. This is required for cloning templates."
            )
            console.print("[yellow]Hint:[/yellow] Install git from https://git-scm.com/downloads")
            sys.exit(1)

        # Step 4: Resolve and validate target directory (skip for remote-only)
        target_path = None
        if not remote_only:
            target_path = resolve_target_path(project_name, target_dir)

            is_valid, error_msg = validate_target_directory(target_path, allow_existing=False)
            if not is_valid:
                console.print(f"[red]✗[/red] {error_msg}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Choose a different name or remove the existing "
                    "directory"
                )
                sys.exit(1)

            console.print(f"[green]✓[/green] Target directory: {target_path}")

        # Step 5: Determine mode (GitHub or local) — after precondition checks
        create_github = _determine_github_mode(use_github, use_local, yes)

        if create_github:
            ready, error_msg = check_gh_prerequisites()
            if not ready:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

        # Step 6: Create GitHub repo first (if GitHub mode)
        github_repo = None
        github_url = None
        if create_github:
            success, github_url, error_msg = create_github_repo(
                name=project_name,
                private=private,
                org=org,
                description=repo_description,
            )
            if not success:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

            # Construct repo identifier
            owner = org if org else get_github_username()
            github_repo = f"{owner}/{project_name}"

        # Step 7: Handle remote-only mode
        if remote_only:
            _show_remote_only_success(project_name, github_url, github_repo)
            return

        # Step 8: Clone template repository
        template_commit = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Cloning template repository...", total=None)
            try:
                template_commit = clone_template(MCP_SERVER_TEMPLATE_URL, target_path)
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to clone template repository")
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    f"\n[yellow]Hint:[/yellow] Check your internet connection and verify "
                    f"the template URL is accessible:\n{MCP_SERVER_TEMPLATE_URL}"
                )
                sys.exit(1)

        # Step 9: Customize project
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Customizing project...", total=None)
            try:
                update_project_name(target_path, project_name)
                cleanup_template_files(target_path)
                if template_commit:
                    write_template_info(
                        target_path,
                        project_name,
                        MCP_SERVER_TEMPLATE_URL,
                        template_commit,
                        template_type="mcp-server",
                        github_repo=github_repo,
                        github_url=github_url,
                    )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to customize project")
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)

        # Step 10: Initialize git repository
        if not no_git:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Initializing git repository...", total=None)
                try:
                    init_repository(target_path, initial_commit=True)
                except Exception as e:
                    console.print("\n[yellow]⚠[/yellow] Failed to initialize git repository")
                    console.print(f"[yellow]Warning:[/yellow] {e}")
                    console.print(
                        "[yellow]You can initialize git manually later with:[/yellow] git init"
                    )

        # Step 11: Push to GitHub (if GitHub mode)
        if create_github and not no_git:
            try:
                add_remote(target_path, "origin", github_url)
                push_success = push_to_remote(target_path, "origin", "main")
                if not push_success:
                    console.print(
                        "\n[yellow]⚠[/yellow] Failed to push to GitHub. "
                        "You can push manually with: git push -u origin main"
                    )
            except Exception as e:
                console.print(f"\n[yellow]⚠[/yellow] Failed to set up GitHub remote: {e}")
                console.print("[yellow]You can add the remote manually with:[/yellow]")
                console.print(f"  git remote add origin {github_url}")
                console.print("  git push -u origin main")

        # Step 12: Success message
        _show_success_message(
            project_name=project_name,
            target_path=target_path,
            github_url=github_url,
            github_repo=github_repo,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠[/yellow] Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e!r}")
        sys.exit(1)


@create.command("agent")
@click.argument("project_name")
@click.option(
    "--target-dir",
    "-t",
    default=None,
    help="Target directory for the project (default: current directory)",
)
@click.option(
    "--no-git",
    is_flag=True,
    default=False,
    help="Skip git repository initialization",
)
@click.option(
    "--github",
    "use_github",
    is_flag=True,
    default=False,
    help="Create GitHub repository and push code",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="Create local project only (skip GitHub)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive mode (use defaults, skip prompts)",
)
@click.option(
    "--private",
    is_flag=True,
    default=False,
    help="Make GitHub repository private (default: public)",
)
@click.option(
    "--org",
    default=None,
    help="GitHub organization to create repository in",
)
@click.option(
    "--description",
    "-d",
    "repo_description",
    default=None,
    help="GitHub repository description",
)
@click.option(
    "--remote-only",
    is_flag=True,
    default=False,
    help="Create GitHub repo only, don't clone locally",
)
@click.option(
    "--vendored",
    is_flag=True,
    default=False,
    help="Copy fipsagents source into the project instead of using PyPI dependency",
)
@click.option(
    "--provider",
    type=click.Choice(["litellm", "openai", "anthropic"], case_sensitive=False),
    default="litellm",
    help="LLM provider backend (default: litellm).",
)
def agent(
    project_name: str,
    target_dir: str | None,
    no_git: bool,
    use_github: bool,
    use_local: bool,
    yes: bool,
    private: bool,
    org: str | None,
    repo_description: str | None,
    remote_only: bool,
    vendored: bool,
    provider: str,
):
    """
    Create a new AI agent project from template.

    PROJECT_NAME must start with a lowercase letter and contain only
    lowercase letters, numbers, hyphens, and underscores.

    By default, if GitHub CLI (gh) is installed and authenticated, prompts
    to create a GitHub repository. Use --local to skip this, or --github
    to require it. Use --yes for non-interactive mode (agents/CI).

    Examples:

        fips-agents create agent my-research-agent

        fips-agents create agent my-research-agent --github --private

        fips-agents create agent my-research-agent --local

        fips-agents create agent my-research-agent --yes

        fips-agents create agent my-research-agent --vendored --local

        fips-agents create agent my-research-agent --provider anthropic
    """
    try:
        # Step 1: Validate options
        if use_github and use_local:
            console.print("[red]✗[/red] Cannot use --github and --local together")
            sys.exit(1)

        if remote_only and use_local:
            console.print("[red]✗[/red] Cannot use --remote-only with --local")
            sys.exit(1)

        # Step 2: Validate project name
        console.print("\n[bold cyan]Creating Agent Project[/bold cyan]\n")

        is_valid, error_msg = validate_project_name(project_name)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid project name: {error_msg}")
            sys.exit(1)

        console.print(f"[green]✓[/green] Project name '{project_name}' is valid")

        # Step 3: Check prerequisites
        if not is_git_installed():
            console.print(
                "[yellow]⚠[/yellow] Git is not installed. This is required for cloning templates."
            )
            console.print("[yellow]Hint:[/yellow] Install git from https://git-scm.com/downloads")
            sys.exit(1)

        # Step 4: Resolve and validate target directory (skip for remote-only)
        target_path = None
        if not remote_only:
            target_path = resolve_target_path(project_name, target_dir)

            is_valid, error_msg = validate_target_directory(target_path, allow_existing=False)
            if not is_valid:
                console.print(f"[red]✗[/red] {error_msg}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Choose a different name or remove the existing "
                    "directory"
                )
                sys.exit(1)

            console.print(f"[green]✓[/green] Target directory: {target_path}")

        # Step 5: Determine mode (GitHub or local)
        create_github = _determine_github_mode(use_github, use_local, yes)

        if create_github:
            ready, error_msg = check_gh_prerequisites()
            if not ready:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

        # Step 6: Create GitHub repo first (if GitHub mode)
        github_repo = None
        github_url = None
        if create_github:
            success, github_url, error_msg = create_github_repo(
                name=project_name,
                private=private,
                org=org,
                description=repo_description,
            )
            if not success:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

            owner = org if org else get_github_username()
            github_repo = f"{owner}/{project_name}"

        # Step 7: Handle remote-only mode
        if remote_only:
            _show_agent_remote_only_success(project_name, github_url, github_repo)
            return

        # Step 8: Clone template repository (subdirectory extraction)
        template_commit = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Cloning agent template...", total=None)
            try:
                post_clone = None
                if vendored:
                    from fips_agents_cli.tools.project import vendor_fipsagents_from_clone

                    post_clone = vendor_fipsagents_from_clone

                template_commit = clone_template_subdir(
                    AGENT_TEMPLATE_URL,
                    target_path,
                    AGENT_TEMPLATE_SUBDIR,
                    post_clone_fn=post_clone,
                )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to clone agent template")
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    f"\n[yellow]Hint:[/yellow] Check your internet connection and verify "
                    f"the template URL is accessible:\n{AGENT_TEMPLATE_URL}"
                )
                sys.exit(1)

        # Step 9: Customize project
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Customizing project...", total=None)
            try:
                customize_agent_project(target_path, project_name, github_repo=github_repo)
                customize_provider(target_path, provider)
                cleanup_template_files(target_path)
                if vendored:
                    from fips_agents_cli.tools.project import rewrite_pyproject_for_vendored

                    rewrite_pyproject_for_vendored(target_path)
                if template_commit:
                    write_template_info(
                        target_path,
                        project_name,
                        AGENT_TEMPLATE_URL,
                        template_commit,
                        template_type="agent",
                        template_subdir=AGENT_TEMPLATE_SUBDIR,
                        github_repo=github_repo,
                        github_url=github_url,
                    )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to customize project")
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)

        # Step 10: Initialize git repository
        if not no_git:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Initializing git repository...", total=None)
                try:
                    init_repository(target_path, initial_commit=True)
                except Exception as e:
                    console.print("\n[yellow]⚠[/yellow] Failed to initialize git repository")
                    console.print(f"[yellow]Warning:[/yellow] {e}")
                    console.print(
                        "[yellow]You can initialize git manually later with:[/yellow] git init"
                    )

        # Step 11: Push to GitHub (if GitHub mode)
        if create_github and not no_git:
            try:
                add_remote(target_path, "origin", github_url)
                push_success = push_to_remote(target_path, "origin", "main")
                if not push_success:
                    console.print(
                        "\n[yellow]⚠[/yellow] Failed to push to GitHub. "
                        "You can push manually with: git push -u origin main"
                    )
            except Exception as e:
                console.print(f"\n[yellow]⚠[/yellow] Failed to set up GitHub remote: {e}")
                console.print("[yellow]You can add the remote manually with:[/yellow]")
                console.print(f"  git remote add origin {github_url}")
                console.print("  git push -u origin main")

        # Step 12: Success message
        _show_agent_success_message(
            project_name=project_name,
            target_path=target_path,
            github_url=github_url,
            github_repo=github_repo,
        )
        if vendored:
            console.print("[cyan]  Framework source vendored in src/fipsagents/[/cyan]")

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠[/yellow] Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e!r}")
        sys.exit(1)


@create.command("workflow")
@click.argument("project_name")
@click.option(
    "--target-dir",
    "-t",
    default=None,
    help="Target directory for the project (default: current directory)",
)
@click.option(
    "--no-git",
    is_flag=True,
    default=False,
    help="Skip git repository initialization",
)
@click.option(
    "--github",
    "use_github",
    is_flag=True,
    default=False,
    help="Create GitHub repository and push code",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="Create local project only (skip GitHub)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive mode (use defaults, skip prompts)",
)
@click.option(
    "--private",
    is_flag=True,
    default=False,
    help="Make GitHub repository private (default: public)",
)
@click.option(
    "--org",
    default=None,
    help="GitHub organization to create repository in",
)
@click.option(
    "--description",
    "-d",
    "repo_description",
    default=None,
    help="GitHub repository description",
)
@click.option(
    "--remote-only",
    is_flag=True,
    default=False,
    help="Create GitHub repo only, don't clone locally",
)
def workflow(
    project_name: str,
    target_dir: str | None,
    no_git: bool,
    use_github: bool,
    use_local: bool,
    yes: bool,
    private: bool,
    org: str | None,
    repo_description: str | None,
    remote_only: bool,
):
    """
    Create a new workflow project from template.

    Scaffolds a directed graph of nodes with typed state. Use BaseNode for
    routing and transformation, AgentNode for LLM-powered nodes.

    PROJECT_NAME must start with a lowercase letter and contain only
    lowercase letters, numbers, hyphens, and underscores.

    Examples:

        fips-agents create workflow my-research-pipeline

        fips-agents create workflow my-pipeline --github --private

        fips-agents create workflow my-pipeline --local
    """
    try:
        # Step 1: Validate options
        if use_github and use_local:
            console.print("[red]✗[/red] Cannot use --github and --local together")
            sys.exit(1)

        if remote_only and use_local:
            console.print("[red]✗[/red] Cannot use --remote-only with --local")
            sys.exit(1)

        # Step 2: Validate project name
        console.print("\n[bold cyan]Creating Workflow Project[/bold cyan]\n")

        is_valid, error_msg = validate_project_name(project_name)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid project name: {error_msg}")
            sys.exit(1)

        console.print(f"[green]✓[/green] Project name '{project_name}' is valid")

        # Step 3: Check prerequisites
        if not is_git_installed():
            console.print(
                "[yellow]⚠[/yellow] Git is not installed. This is required for cloning templates."
            )
            console.print("[yellow]Hint:[/yellow] Install git from https://git-scm.com/downloads")
            sys.exit(1)

        # Step 4: Resolve and validate target directory (skip for remote-only)
        target_path = None
        if not remote_only:
            target_path = resolve_target_path(project_name, target_dir)

            is_valid, error_msg = validate_target_directory(target_path, allow_existing=False)
            if not is_valid:
                console.print(f"[red]✗[/red] {error_msg}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Choose a different name or remove the existing "
                    "directory"
                )
                sys.exit(1)

            console.print(f"[green]✓[/green] Target directory: {target_path}")

        # Step 5: Determine mode (GitHub or local)
        create_github = _determine_github_mode(use_github, use_local, yes)

        if create_github:
            ready, error_msg = check_gh_prerequisites()
            if not ready:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

        # Step 6: Create GitHub repo first (if GitHub mode)
        github_repo = None
        github_url = None
        if create_github:
            success, github_url, error_msg = create_github_repo(
                name=project_name,
                private=private,
                org=org,
                description=repo_description,
            )
            if not success:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

            owner = org if org else get_github_username()
            github_repo = f"{owner}/{project_name}"

        # Step 7: Handle remote-only mode
        if remote_only:
            _show_workflow_remote_only_success(project_name, github_url, github_repo)
            return

        # Step 8: Clone template repository (subdirectory extraction)
        template_commit = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Cloning workflow template...", total=None)
            try:
                template_commit = clone_template_subdir(
                    AGENT_TEMPLATE_URL, target_path, WORKFLOW_TEMPLATE_SUBDIR
                )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to clone workflow template")
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    f"\n[yellow]Hint:[/yellow] Check your internet connection and verify "
                    f"the template URL is accessible:\n{AGENT_TEMPLATE_URL}"
                )
                sys.exit(1)

        # Step 9: Customize project
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Customizing project...", total=None)
            try:
                customize_workflow_project(target_path, project_name, github_repo=github_repo)
                cleanup_template_files(target_path)
                if template_commit:
                    write_template_info(
                        target_path,
                        project_name,
                        AGENT_TEMPLATE_URL,
                        template_commit,
                        template_type="workflow",
                        template_subdir=WORKFLOW_TEMPLATE_SUBDIR,
                        github_repo=github_repo,
                        github_url=github_url,
                    )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to customize project")
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)

        # Step 10: Initialize git repository
        if not no_git:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Initializing git repository...", total=None)
                try:
                    init_repository(target_path, initial_commit=True)
                except Exception as e:
                    console.print("\n[yellow]⚠[/yellow] Failed to initialize git repository")
                    console.print(f"[yellow]Warning:[/yellow] {e}")
                    console.print(
                        "[yellow]You can initialize git manually later with:[/yellow] git init"
                    )

        # Step 11: Push to GitHub (if GitHub mode)
        if create_github and not no_git:
            try:
                add_remote(target_path, "origin", github_url)
                push_success = push_to_remote(target_path, "origin", "main")
                if not push_success:
                    console.print(
                        "\n[yellow]⚠[/yellow] Failed to push to GitHub. "
                        "You can push manually with: git push -u origin main"
                    )
            except Exception as e:
                console.print(f"\n[yellow]⚠[/yellow] Failed to set up GitHub remote: {e}")
                console.print("[yellow]You can add the remote manually with:[/yellow]")
                console.print(f"  git remote add origin {github_url}")
                console.print("  git push -u origin main")

        # Step 12: Success message
        _show_workflow_success_message(
            project_name=project_name,
            target_path=target_path,
            github_url=github_url,
            github_repo=github_repo,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠[/yellow] Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e!r}")
        sys.exit(1)


@create.command("gateway")
@click.argument("project_name")
@click.option(
    "--target-dir",
    "-t",
    default=None,
    help="Target directory for the project (default: current directory)",
)
@click.option(
    "--no-git",
    is_flag=True,
    default=False,
    help="Skip git repository initialization",
)
@click.option(
    "--github",
    "use_github",
    is_flag=True,
    default=False,
    help="Create GitHub repository and push code",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="Create local project only (skip GitHub)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive mode (use defaults, skip prompts)",
)
@click.option(
    "--private",
    is_flag=True,
    default=False,
    help="Make GitHub repository private (default: public)",
)
@click.option(
    "--org",
    default=None,
    help="GitHub organization to create repository in",
)
@click.option(
    "--description",
    "-d",
    "repo_description",
    default=None,
    help="GitHub repository description",
)
@click.option(
    "--remote-only",
    is_flag=True,
    default=False,
    help="Create GitHub repo only, don't clone locally",
)
def gateway(
    project_name: str,
    target_dir: str | None,
    no_git: bool,
    use_github: bool,
    use_local: bool,
    yes: bool,
    private: bool,
    org: str | None,
    repo_description: str | None,
    remote_only: bool,
):
    """
    Create a new API gateway project from template.

    PROJECT_NAME must start with a lowercase letter and contain only
    lowercase letters, numbers, hyphens, and underscores.

    By default, if GitHub CLI (gh) is installed and authenticated, prompts
    to create a GitHub repository. Use --local to skip this, or --github
    to require it. Use --yes for non-interactive mode (agents/CI).

    Examples:

        fips-agents create gateway my-gateway

        fips-agents create gateway my-gateway --github --private

        fips-agents create gateway my-gateway --local

        fips-agents create gateway my-gateway --yes
    """
    try:
        # Step 1: Validate options
        if use_github and use_local:
            console.print("[red]✗[/red] Cannot use --github and --local together")
            sys.exit(1)

        if remote_only and use_local:
            console.print("[red]✗[/red] Cannot use --remote-only with --local")
            sys.exit(1)

        # Step 2: Validate project name
        console.print("\n[bold cyan]Creating Gateway Project[/bold cyan]\n")

        is_valid, error_msg = validate_project_name(project_name)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid project name: {error_msg}")
            sys.exit(1)

        console.print(f"[green]✓[/green] Project name '{project_name}' is valid")

        # Step 3: Check prerequisites
        if not is_git_installed():
            console.print(
                "[yellow]⚠[/yellow] Git is not installed. This is required for cloning templates."
            )
            console.print("[yellow]Hint:[/yellow] Install git from https://git-scm.com/downloads")
            sys.exit(1)

        # Step 4: Resolve and validate target directory (skip for remote-only)
        target_path = None
        if not remote_only:
            target_path = resolve_target_path(project_name, target_dir)

            is_valid, error_msg = validate_target_directory(target_path, allow_existing=False)
            if not is_valid:
                console.print(f"[red]✗[/red] {error_msg}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Choose a different name or remove the existing "
                    "directory"
                )
                sys.exit(1)

            console.print(f"[green]✓[/green] Target directory: {target_path}")

        # Step 5: Determine mode (GitHub or local)
        create_github = _determine_github_mode(use_github, use_local, yes)

        if create_github:
            ready, error_msg = check_gh_prerequisites()
            if not ready:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

        # Step 6: Create GitHub repo first (if GitHub mode)
        github_repo = None
        github_url = None
        if create_github:
            success, github_url, error_msg = create_github_repo(
                name=project_name,
                private=private,
                org=org,
                description=repo_description,
            )
            if not success:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

            owner = org if org else get_github_username()
            github_repo = f"{owner}/{project_name}"

        # Step 7: Handle remote-only mode
        if remote_only:
            _show_gateway_remote_only_success(project_name, github_url, github_repo)
            return

        # Step 8: Clone template repository
        template_commit = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Cloning gateway template...", total=None)
            try:
                template_commit = clone_template(GATEWAY_TEMPLATE_URL, target_path)
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to clone gateway template")
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    f"\n[yellow]Hint:[/yellow] Check your internet connection and verify "
                    f"the template URL is accessible:\n{GATEWAY_TEMPLATE_URL}"
                )
                sys.exit(1)

        # Step 9: Customize project
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Customizing project...", total=None)
            try:
                customize_go_project(target_path, project_name, "gateway-template")
                cleanup_template_files(target_path)
                if template_commit:
                    write_template_info(
                        target_path,
                        project_name,
                        GATEWAY_TEMPLATE_URL,
                        template_commit,
                        template_type="gateway",
                        github_repo=github_repo,
                        github_url=github_url,
                    )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to customize project")
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)

        # Step 10: Initialize git repository
        if not no_git:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Initializing git repository...", total=None)
                try:
                    init_repository(target_path, initial_commit=True)
                except Exception as e:
                    console.print("\n[yellow]⚠[/yellow] Failed to initialize git repository")
                    console.print(f"[yellow]Warning:[/yellow] {e}")
                    console.print(
                        "[yellow]You can initialize git manually later with:[/yellow] git init"
                    )

        # Step 11: Push to GitHub (if GitHub mode)
        if create_github and not no_git:
            try:
                add_remote(target_path, "origin", github_url)
                push_success = push_to_remote(target_path, "origin", "main")
                if not push_success:
                    console.print(
                        "\n[yellow]⚠[/yellow] Failed to push to GitHub. "
                        "You can push manually with: git push -u origin main"
                    )
            except Exception as e:
                console.print(f"\n[yellow]⚠[/yellow] Failed to set up GitHub remote: {e}")
                console.print("[yellow]You can add the remote manually with:[/yellow]")
                console.print(f"  git remote add origin {github_url}")
                console.print("  git push -u origin main")

        # Step 12: Success message
        _show_gateway_success_message(
            project_name=project_name,
            target_path=target_path,
            github_url=github_url,
            github_repo=github_repo,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠[/yellow] Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e!r}")
        sys.exit(1)


@create.command("ui")
@click.argument("project_name")
@click.option(
    "--target-dir",
    "-t",
    default=None,
    help="Target directory for the project (default: current directory)",
)
@click.option(
    "--no-git",
    is_flag=True,
    default=False,
    help="Skip git repository initialization",
)
@click.option(
    "--github",
    "use_github",
    is_flag=True,
    default=False,
    help="Create GitHub repository and push code",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="Create local project only (skip GitHub)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive mode (use defaults, skip prompts)",
)
@click.option(
    "--private",
    is_flag=True,
    default=False,
    help="Make GitHub repository private (default: public)",
)
@click.option(
    "--org",
    default=None,
    help="GitHub organization to create repository in",
)
@click.option(
    "--description",
    "-d",
    "repo_description",
    default=None,
    help="GitHub repository description",
)
@click.option(
    "--remote-only",
    is_flag=True,
    default=False,
    help="Create GitHub repo only, don't clone locally",
)
def ui(
    project_name: str,
    target_dir: str | None,
    no_git: bool,
    use_github: bool,
    use_local: bool,
    yes: bool,
    private: bool,
    org: str | None,
    repo_description: str | None,
    remote_only: bool,
):
    """
    Create a new chat UI project from template.

    PROJECT_NAME must start with a lowercase letter and contain only
    lowercase letters, numbers, hyphens, and underscores.

    By default, if GitHub CLI (gh) is installed and authenticated, prompts
    to create a GitHub repository. Use --local to skip this, or --github
    to require it. Use --yes for non-interactive mode (agents/CI).

    Examples:

        fips-agents create ui my-chat-ui

        fips-agents create ui my-chat-ui --github --private

        fips-agents create ui my-chat-ui --local

        fips-agents create ui my-chat-ui --yes
    """
    try:
        # Step 1: Validate options
        if use_github and use_local:
            console.print("[red]✗[/red] Cannot use --github and --local together")
            sys.exit(1)

        if remote_only and use_local:
            console.print("[red]✗[/red] Cannot use --remote-only with --local")
            sys.exit(1)

        # Step 2: Validate project name
        console.print("\n[bold cyan]Creating Chat UI Project[/bold cyan]\n")

        is_valid, error_msg = validate_project_name(project_name)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid project name: {error_msg}")
            sys.exit(1)

        console.print(f"[green]✓[/green] Project name '{project_name}' is valid")

        # Step 3: Check prerequisites
        if not is_git_installed():
            console.print(
                "[yellow]⚠[/yellow] Git is not installed. This is required for cloning templates."
            )
            console.print("[yellow]Hint:[/yellow] Install git from https://git-scm.com/downloads")
            sys.exit(1)

        # Step 4: Resolve and validate target directory (skip for remote-only)
        target_path = None
        if not remote_only:
            target_path = resolve_target_path(project_name, target_dir)

            is_valid, error_msg = validate_target_directory(target_path, allow_existing=False)
            if not is_valid:
                console.print(f"[red]✗[/red] {error_msg}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Choose a different name or remove the existing "
                    "directory"
                )
                sys.exit(1)

            console.print(f"[green]✓[/green] Target directory: {target_path}")

        # Step 5: Determine mode (GitHub or local)
        create_github = _determine_github_mode(use_github, use_local, yes)

        if create_github:
            ready, error_msg = check_gh_prerequisites()
            if not ready:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

        # Step 6: Create GitHub repo first (if GitHub mode)
        github_repo = None
        github_url = None
        if create_github:
            success, github_url, error_msg = create_github_repo(
                name=project_name,
                private=private,
                org=org,
                description=repo_description,
            )
            if not success:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

            owner = org if org else get_github_username()
            github_repo = f"{owner}/{project_name}"

        # Step 7: Handle remote-only mode
        if remote_only:
            _show_ui_remote_only_success(project_name, github_url, github_repo)
            return

        # Step 8: Clone template repository
        template_commit = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Cloning UI template...", total=None)
            try:
                template_commit = clone_template(UI_TEMPLATE_URL, target_path)
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to clone UI template")
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    f"\n[yellow]Hint:[/yellow] Check your internet connection and verify "
                    f"the template URL is accessible:\n{UI_TEMPLATE_URL}"
                )
                sys.exit(1)

        # Step 9: Customize project
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Customizing project...", total=None)
            try:
                customize_go_project(target_path, project_name, "ui-template")
                cleanup_template_files(target_path)
                if template_commit:
                    write_template_info(
                        target_path,
                        project_name,
                        UI_TEMPLATE_URL,
                        template_commit,
                        template_type="ui",
                        github_repo=github_repo,
                        github_url=github_url,
                    )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to customize project")
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)

        # Step 10: Initialize git repository
        if not no_git:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Initializing git repository...", total=None)
                try:
                    init_repository(target_path, initial_commit=True)
                except Exception as e:
                    console.print("\n[yellow]⚠[/yellow] Failed to initialize git repository")
                    console.print(f"[yellow]Warning:[/yellow] {e}")
                    console.print(
                        "[yellow]You can initialize git manually later with:[/yellow] git init"
                    )

        # Step 11: Push to GitHub (if GitHub mode)
        if create_github and not no_git:
            try:
                add_remote(target_path, "origin", github_url)
                push_success = push_to_remote(target_path, "origin", "main")
                if not push_success:
                    console.print(
                        "\n[yellow]⚠[/yellow] Failed to push to GitHub. "
                        "You can push manually with: git push -u origin main"
                    )
            except Exception as e:
                console.print(f"\n[yellow]⚠[/yellow] Failed to set up GitHub remote: {e}")
                console.print("[yellow]You can add the remote manually with:[/yellow]")
                console.print(f"  git remote add origin {github_url}")
                console.print("  git push -u origin main")

        # Step 12: Success message
        _show_ui_success_message(
            project_name=project_name,
            target_path=target_path,
            github_url=github_url,
            github_repo=github_repo,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠[/yellow] Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e!r}")
        sys.exit(1)


@create.command("sandbox")
@click.argument("project_name")
@click.option(
    "--target-dir",
    "-t",
    default=None,
    help="Target directory for the project (default: current directory)",
)
@click.option(
    "--no-git",
    is_flag=True,
    default=False,
    help="Skip git repository initialization",
)
@click.option(
    "--github",
    "use_github",
    is_flag=True,
    default=False,
    help="Create GitHub repository and push code",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="Create local project only (skip GitHub)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive mode (use defaults, skip prompts)",
)
@click.option(
    "--private",
    is_flag=True,
    default=False,
    help="Make GitHub repository private (default: public)",
)
@click.option(
    "--org",
    default=None,
    help="GitHub organization to create repository in",
)
@click.option(
    "--description",
    "-d",
    "repo_description",
    default=None,
    help="GitHub repository description",
)
@click.option(
    "--remote-only",
    is_flag=True,
    default=False,
    help="Create GitHub repo only, don't clone locally",
)
def sandbox(
    project_name: str,
    target_dir: str | None,
    no_git: bool,
    use_github: bool,
    use_local: bool,
    yes: bool,
    private: bool,
    org: str | None,
    repo_description: str | None,
    remote_only: bool,
):
    """
    Create a new code execution sandbox project from template.

    Scaffolds a FastAPI-based code sandbox sidecar for secure code execution
    inside agent pods. Supports multiple language profiles (base, data-science).

    PROJECT_NAME must start with a lowercase letter and contain only
    lowercase letters, numbers, hyphens, and underscores.

    Examples:

        fips-agents create sandbox my-sandbox

        fips-agents create sandbox my-sandbox --github --private

        fips-agents create sandbox my-sandbox --local

        fips-agents create sandbox my-sandbox --yes
    """
    try:
        # Step 1: Validate options
        if use_github and use_local:
            console.print("[red]✗[/red] Cannot use --github and --local together")
            sys.exit(1)

        if remote_only and use_local:
            console.print("[red]✗[/red] Cannot use --remote-only with --local")
            sys.exit(1)

        # Step 2: Validate project name
        console.print("\n[bold cyan]Creating Sandbox Project[/bold cyan]\n")

        is_valid, error_msg = validate_project_name(project_name)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid project name: {error_msg}")
            sys.exit(1)

        console.print(f"[green]✓[/green] Project name '{project_name}' is valid")

        # Step 3: Check prerequisites
        if not is_git_installed():
            console.print(
                "[yellow]⚠[/yellow] Git is not installed. This is required for cloning templates."
            )
            console.print("[yellow]Hint:[/yellow] Install git from https://git-scm.com/downloads")
            sys.exit(1)

        # Step 4: Resolve and validate target directory (skip for remote-only)
        target_path = None
        if not remote_only:
            target_path = resolve_target_path(project_name, target_dir)

            is_valid, error_msg = validate_target_directory(target_path, allow_existing=False)
            if not is_valid:
                console.print(f"[red]✗[/red] {error_msg}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Choose a different name or remove the existing "
                    "directory"
                )
                sys.exit(1)

            console.print(f"[green]✓[/green] Target directory: {target_path}")

        # Step 5: Determine mode (GitHub or local)
        create_github = _determine_github_mode(use_github, use_local, yes)

        if create_github:
            ready, error_msg = check_gh_prerequisites()
            if not ready:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

        # Step 6: Create GitHub repo first (if GitHub mode)
        github_repo = None
        github_url = None
        if create_github:
            success, github_url, error_msg = create_github_repo(
                name=project_name,
                private=private,
                org=org,
                description=repo_description,
            )
            if not success:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

            owner = org if org else get_github_username()
            github_repo = f"{owner}/{project_name}"

        # Step 7: Handle remote-only mode
        if remote_only:
            _show_sandbox_remote_only_success(project_name, github_url, github_repo)
            return

        # Step 8: Clone template repository
        template_commit = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Cloning sandbox template...", total=None)
            try:
                template_commit = clone_template(SANDBOX_TEMPLATE_URL, target_path)
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to clone sandbox template")
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    f"\n[yellow]Hint:[/yellow] Check your internet connection and verify "
                    f"the template URL is accessible:\n{SANDBOX_TEMPLATE_URL}"
                )
                sys.exit(1)

        # Step 9: Customize project
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Customizing project...", total=None)
            try:
                customize_sandbox_project(target_path, project_name, github_repo=github_repo)
                cleanup_template_files(target_path)
                if template_commit:
                    write_template_info(
                        target_path,
                        project_name,
                        SANDBOX_TEMPLATE_URL,
                        template_commit,
                        template_type="sandbox",
                        github_repo=github_repo,
                        github_url=github_url,
                    )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to customize project")
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)

        # Step 10: Initialize git repository
        if not no_git:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Initializing git repository...", total=None)
                try:
                    init_repository(target_path, initial_commit=True)
                except Exception as e:
                    console.print("\n[yellow]⚠[/yellow] Failed to initialize git repository")
                    console.print(f"[yellow]Warning:[/yellow] {e}")
                    console.print(
                        "[yellow]You can initialize git manually later with:[/yellow] git init"
                    )

        # Step 11: Push to GitHub (if GitHub mode)
        if create_github and not no_git:
            try:
                add_remote(target_path, "origin", github_url)
                push_success = push_to_remote(target_path, "origin", "main")
                if not push_success:
                    console.print(
                        "\n[yellow]⚠[/yellow] Failed to push to GitHub. "
                        "You can push manually with: git push -u origin main"
                    )
            except Exception as e:
                console.print(f"\n[yellow]⚠[/yellow] Failed to set up GitHub remote: {e}")
                console.print("[yellow]You can add the remote manually with:[/yellow]")
                console.print(f"  git remote add origin {github_url}")
                console.print("  git push -u origin main")

        # Step 12: Success message
        _show_sandbox_success_message(
            project_name=project_name,
            target_path=target_path,
            github_url=github_url,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠[/yellow] Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e!r}")
        sys.exit(1)


@create.command("agent-team")
@click.argument("project_name")
@click.option(
    "--target-dir",
    "-t",
    default=None,
    help="Target directory for the project (default: current directory)",
)
@click.option(
    "--no-git",
    is_flag=True,
    default=False,
    help="Skip git repository initialization",
)
@click.option(
    "--github",
    "use_github",
    is_flag=True,
    default=False,
    help="Create GitHub repository and push code",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="Create local project only (skip GitHub)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive mode (use defaults, skip prompts)",
)
@click.option(
    "--private",
    is_flag=True,
    default=False,
    help="Make GitHub repository private (default: public)",
)
@click.option(
    "--org",
    default=None,
    help="GitHub organization to create repository in",
)
@click.option(
    "--description",
    "-d",
    "repo_description",
    default=None,
    help="GitHub repository description",
)
@click.option(
    "--remote-only",
    is_flag=True,
    default=False,
    help="Create GitHub repo only, don't clone locally",
)
def agent_team(
    project_name: str,
    target_dir: str | None,
    no_git: bool,
    use_github: bool,
    use_local: bool,
    yes: bool,
    private: bool,
    org: str | None,
    repo_description: str | None,
    remote_only: bool,
):
    """
    Create a new agent team project from template.

    PROJECT_NAME must start with a lowercase letter and contain only
    lowercase letters, numbers, hyphens, and underscores.

    By default, if GitHub CLI (gh) is installed and authenticated, prompts
    to create a GitHub repository. Use --local to skip this, or --github
    to require it. Use --yes for non-interactive mode (agents/CI).

    Examples:

        fips-agents create agent-team my-team

        fips-agents create agent-team my-team --github --private

        fips-agents create agent-team my-team --local

        fips-agents create agent-team my-team --yes  # Non-interactive
    """
    try:
        # Step 1: Validate options
        if use_github and use_local:
            console.print("[red]✗[/red] Cannot use --github and --local together")
            sys.exit(1)

        if remote_only and use_local:
            console.print("[red]✗[/red] Cannot use --remote-only with --local")
            sys.exit(1)

        # Step 2: Validate project name
        console.print("\n[bold cyan]Creating Agent Team Project[/bold cyan]\n")

        is_valid, error_msg = validate_project_name(project_name)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid project name: {error_msg}")
            sys.exit(1)

        console.print(f"[green]✓[/green] Project name '{project_name}' is valid")

        # Step 3: Check prerequisites (fail fast before any interactive prompts)
        if not is_git_installed():
            console.print(
                "[yellow]⚠[/yellow] Git is not installed. This is required for cloning templates."
            )
            console.print("[yellow]Hint:[/yellow] Install git from https://git-scm.com/downloads")
            sys.exit(1)

        # Step 4: Resolve and validate target directory (skip for remote-only)
        target_path = None
        if not remote_only:
            target_path = resolve_target_path(project_name, target_dir)

            is_valid, error_msg = validate_target_directory(target_path, allow_existing=False)
            if not is_valid:
                console.print(f"[red]✗[/red] {error_msg}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Choose a different name or remove the existing "
                    "directory"
                )
                sys.exit(1)

            console.print(f"[green]✓[/green] Target directory: {target_path}")

        # Step 5: Determine mode (GitHub or local) — after precondition checks
        create_github = _determine_github_mode(use_github, use_local, yes)

        if create_github:
            ready, error_msg = check_gh_prerequisites()
            if not ready:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

        # Step 6: Create GitHub repo first (if GitHub mode)
        github_repo = None
        github_url = None
        if create_github:
            success, github_url, error_msg = create_github_repo(
                name=project_name,
                private=private,
                org=org,
                description=repo_description,
            )
            if not success:
                console.print(f"[red]✗[/red] {error_msg}")
                sys.exit(1)

            # Construct repo identifier
            owner = org if org else get_github_username()
            github_repo = f"{owner}/{project_name}"

        # Step 7: Handle remote-only mode
        if remote_only:
            _show_agent_team_remote_only_success(project_name, github_url, github_repo)
            return

        # Step 8: Clone template repository
        template_commit = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Cloning agent team template...", total=None)
            try:
                template_commit = clone_template(AGENT_TEAM_TEMPLATE_URL, target_path)
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to clone agent team template")
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    f"\n[yellow]Hint:[/yellow] Check your internet connection and verify "
                    f"the template URL is accessible:\n{AGENT_TEAM_TEMPLATE_URL}"
                )
                sys.exit(1)

        # Step 9: Customize project
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="Customizing project...", total=None)
            try:
                customize_agent_team_project(target_path, project_name, github_repo=github_repo)
                cleanup_template_files(target_path)
                if template_commit:
                    write_template_info(
                        target_path,
                        project_name,
                        AGENT_TEAM_TEMPLATE_URL,
                        template_commit,
                        template_type="agent-team",
                        github_repo=github_repo,
                        github_url=github_url,
                    )
            except Exception as e:
                console.print("\n[red]✗[/red] Failed to customize project")
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)

        # Step 10: Initialize git repository
        if not no_git:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Initializing git repository...", total=None)
                try:
                    init_repository(target_path, initial_commit=True)
                except Exception as e:
                    console.print("\n[yellow]⚠[/yellow] Failed to initialize git repository")
                    console.print(f"[yellow]Warning:[/yellow] {e}")
                    console.print(
                        "[yellow]You can initialize git manually later with:[/yellow] git init"
                    )

        # Step 11: Push to GitHub (if GitHub mode)
        if create_github and not no_git:
            try:
                add_remote(target_path, "origin", github_url)
                push_success = push_to_remote(target_path, "origin", "main")
                if not push_success:
                    console.print(
                        "\n[yellow]⚠[/yellow] Failed to push to GitHub. "
                        "You can push manually with: git push -u origin main"
                    )
            except Exception as e:
                console.print(f"\n[yellow]⚠[/yellow] Failed to set up GitHub remote: {e}")
                console.print("[yellow]You can add the remote manually with:[/yellow]")
                console.print(f"  git remote add origin {github_url}")
                console.print("  git push -u origin main")

        # Step 12: Success message
        _show_agent_team_success_message(
            project_name=project_name,
            target_path=target_path,
            github_url=github_url,
            github_repo=github_repo,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠[/yellow] Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e!r}")
        sys.exit(1)


def _determine_github_mode(use_github: bool, use_local: bool, yes: bool) -> bool:
    """
    Determine whether to create a GitHub repository.

    Args:
        use_github: --github flag was set
        use_local: --local flag was set
        yes: --yes flag was set (non-interactive mode)

    Returns:
        bool: True if GitHub repository should be created
    """
    # Explicit flags take precedence
    if use_local:
        console.print("[dim]Mode: Local only (--local)[/dim]")
        return False

    if use_github:
        console.print("[dim]Mode: GitHub (--github)[/dim]")
        return True

    # Check if gh is available
    if not is_gh_installed():
        console.print("[dim]Mode: Local only (GitHub CLI not installed)[/dim]")
        return False

    if not is_gh_authenticated():
        console.print("[dim]Mode: Local only (GitHub CLI not authenticated)[/dim]")
        return False

    # gh is available - decide based on interactive mode
    if yes:
        # Non-interactive: default to GitHub
        console.print("[dim]Mode: GitHub (--yes with gh available)[/dim]")
        return True

    # No TTY available (CI, agent-driven shells, piped input): can't prompt.
    # Default to local; users opt in to GitHub with --github or --yes.
    if not sys.stdin.isatty():
        console.print(
            "[dim]Mode: Local only (non-interactive shell — pass --github or --yes "
            "to create a GitHub repo)[/dim]"
        )
        return False

    # Interactive: prompt user
    console.print("[cyan]GitHub CLI detected and authenticated.[/cyan]")
    try:
        return click.confirm("Create GitHub repository?", default=True)
    except click.exceptions.Abort:
        # Stdin closed mid-prompt (isatty lied, or input ended). Fall back to local.
        console.print(
            "\n[dim]Mode: Local only (no input available — pass --github or --yes "
            "to create a GitHub repo)[/dim]"
        )
        return False


def _show_success_message(
    project_name: str,
    target_path,
    github_url: str | None,
    github_repo: str | None,
) -> None:
    """Display success message with next steps."""
    module_name = to_module_name(project_name)

    # Build project details section
    details = f"""  • Name: {project_name}
  • Module: {module_name}
  • Location: {target_path}"""

    if github_url:
        details += f"\n  • GitHub: {github_url}"

    # Build next steps based on mode
    if github_url:
        next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Create and activate a virtual environment:
     [dim]python -m venv venv[/dim]
     [dim]source venv/bin/activate[/dim]  # On Windows: venv\\Scripts\\activate

  3. Install the project in editable mode:
     [dim]pip install -e .[dev][/dim]

  4. Start developing your MCP server!
     [dim]Your code is already pushed to GitHub[/dim]

  5. Run tests:
     [dim]pytest[/dim]"""
    else:
        next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Create and activate a virtual environment:
     [dim]python -m venv venv[/dim]
     [dim]source venv/bin/activate[/dim]  # On Windows: venv\\Scripts\\activate

  3. Install the project in editable mode:
     [dim]pip install -e .[dev][/dim]

  4. Start developing your MCP server!
     [dim]Edit src/ files to add your functionality[/dim]

  5. Run tests:
     [dim]pytest[/dim]"""

    success_message = f"""
[bold green]✓ Successfully created MCP server project![/bold green]

[bold cyan]Project Details:[/bold cyan]
{details}

[bold cyan]Next Steps:[/bold cyan]
{next_steps}

[bold cyan]Documentation:[/bold cyan]
  • Check the README.md in your project for detailed instructions
  • MCP Protocol docs: https://modelcontextprotocol.io/
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_remote_only_success(
    project_name: str,
    github_url: str,
    github_repo: str,
) -> None:
    """Display success message for remote-only mode."""
    success_message = f"""
[bold green]✓ Successfully created GitHub repository![/bold green]

[bold cyan]Repository Details:[/bold cyan]
  • Name: {project_name}
  • GitHub: {github_url}

[bold cyan]Next Steps:[/bold cyan]

  1. Clone the repository:
     [dim]git clone {github_url}[/dim]
     [dim]cd {project_name}[/dim]

  2. The repository contains the MCP server template.
     Customize it for your project.

[bold cyan]Note:[/bold cyan]
  The repository contains the raw template.
  You may want to customize project names and paths.
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_agent_success_message(
    project_name: str,
    target_path,
    github_url: str | None,
    github_repo: str | None,
) -> None:
    """Display success message with next steps for agent projects."""
    details = f"""  • Name: {project_name}
  • Location: {target_path}"""

    if github_url:
        details += f"\n  • GitHub: {github_url}"

    next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Install dependencies:
     [dim]make install[/dim]

  3. Plan your agent (AI-assisted):
     [dim]/plan-agent[/dim]

  4. Run the example agent locally:
     [dim]make run-local[/dim]

  5. Run tests:
     [dim]make test[/dim]

  6. Deploy to OpenShift:
     [dim]make deploy PROJECT={project_name}[/dim]"""

    success_message = f"""
[bold green]✓ Successfully created agent project![/bold green]

[bold cyan]Project Details:[/bold cyan]
{details}

[bold cyan]Next Steps:[/bold cyan]
{next_steps}

[bold cyan]Documentation:[/bold cyan]
  • See AGENTS.md for agent capabilities
  • See docs/ directory for architecture details
  • Run /plan-agent in Claude Code to design your agent
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_agent_remote_only_success(
    project_name: str,
    github_url: str,
    github_repo: str,
) -> None:
    """Display success message for agent remote-only mode."""
    success_message = f"""
[bold green]✓ Successfully created GitHub repository![/bold green]

[bold cyan]Repository Details:[/bold cyan]
  • Name: {project_name}
  • GitHub: {github_url}

[bold cyan]Next Steps:[/bold cyan]

  1. Clone the repository:
     [dim]git clone {github_url}[/dim]
     [dim]cd {project_name}[/dim]

  2. The repository contains the agent template.
     Run /plan-agent in Claude Code to design your agent.

[bold cyan]Note:[/bold cyan]
  The repository contains the raw template.
  You may want to customize project names and paths.
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_workflow_success_message(
    project_name: str,
    target_path,
    github_url: str | None,
    github_repo: str | None,
) -> None:
    """Display success message with next steps for workflow projects."""
    details = f"""  • Name: {project_name}
  • Location: {target_path}"""

    if github_url:
        details += f"\n  • GitHub: {github_url}"

    next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Install dependencies:
     [dim]make install[/dim]

  3. Plan your workflow (AI-assisted):
     [dim]/plan-agent[/dim]

  4. Run the example workflow locally:
     [dim]make run-local[/dim]

  5. Run tests:
     [dim]make test[/dim]

  6. Deploy to OpenShift:
     [dim]make deploy PROJECT={project_name}[/dim]"""

    success_message = f"""
[bold green]✓ Successfully created workflow project![/bold green]

[bold cyan]Project Details:[/bold cyan]
{details}

[bold cyan]Next Steps:[/bold cyan]
{next_steps}

[bold cyan]Documentation:[/bold cyan]
  • See CLAUDE.md for workflow framework guide
  • Use BaseNode for routing, AgentNode for LLM nodes
  • Run /plan-agent in Claude Code to design your workflow
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_workflow_remote_only_success(
    project_name: str,
    github_url: str,
    github_repo: str,
) -> None:
    """Display success message for workflow remote-only mode."""
    success_message = f"""
[bold green]✓ Successfully created GitHub repository![/bold green]

[bold cyan]Repository Details:[/bold cyan]
  • Name: {project_name}
  • GitHub: {github_url}

[bold cyan]Next Steps:[/bold cyan]

  1. Clone the repository:
     [dim]git clone {github_url}[/dim]
     [dim]cd {project_name}[/dim]

  2. The repository contains the workflow template.
     Run /plan-agent in Claude Code to design your workflow.

[bold cyan]Note:[/bold cyan]
  The repository contains the raw template.
  You may want to customize project names and paths.
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_gateway_success_message(
    project_name: str,
    target_path,
    github_url: str | None,
    github_repo: str | None,
) -> None:
    """Display success message with next steps for gateway projects."""
    details = f"""  • Name: {project_name}
  • Location: {target_path}"""

    if github_url:
        details += f"\n  • GitHub: {github_url}"

    next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Build the server:
     [dim]go build ./cmd/server[/dim]

  3. Run the server:
     [dim]BACKEND_URL=http://localhost:8080 ./bin/server[/dim]

  4. Run tests:
     [dim]make test[/dim]

  5. Deploy to OpenShift:
     [dim]make deploy PROJECT={project_name}[/dim]"""

    success_message = f"""
[bold green]✓ Successfully created gateway project![/bold green]

[bold cyan]Project Details:[/bold cyan]
{details}

[bold cyan]Next Steps:[/bold cyan]
{next_steps}

[bold cyan]Documentation:[/bold cyan]
  • See {target_path.name}/CLAUDE.md for development guide
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_gateway_remote_only_success(
    project_name: str,
    github_url: str,
    github_repo: str,
) -> None:
    """Display success message for gateway remote-only mode."""
    success_message = f"""
[bold green]✓ Successfully created GitHub repository![/bold green]

[bold cyan]Repository Details:[/bold cyan]
  • Name: {project_name}
  • GitHub: {github_url}

[bold cyan]Next Steps:[/bold cyan]

  1. Clone the repository:
     [dim]git clone {github_url}[/dim]
     [dim]cd {project_name}[/dim]

  2. The repository contains the gateway template.
     See CLAUDE.md for development instructions.

[bold cyan]Note:[/bold cyan]
  The repository contains the raw template.
  You may want to customize project names and paths.
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_ui_success_message(
    project_name: str,
    target_path,
    github_url: str | None,
    github_repo: str | None,
) -> None:
    """Display success message with next steps for UI projects."""
    details = f"""  • Name: {project_name}
  • Location: {target_path}"""

    if github_url:
        details += f"\n  • GitHub: {github_url}"

    next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Build the server:
     [dim]go build -o bin/server ./cmd/server[/dim]

  3. Run the server:
     [dim]API_URL=http://localhost:8080 ./bin/server[/dim]

  4. Open in your browser:
     [dim]http://localhost:3000[/dim]

  5. Deploy to OpenShift:
     [dim]make deploy PROJECT={project_name}[/dim]"""

    success_message = f"""
[bold green]✓ Successfully created chat UI project![/bold green]

[bold cyan]Project Details:[/bold cyan]
{details}

[bold cyan]Next Steps:[/bold cyan]
{next_steps}

[bold cyan]Documentation:[/bold cyan]
  • See {target_path.name}/CLAUDE.md for development guide
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_ui_remote_only_success(
    project_name: str,
    github_url: str,
    github_repo: str,
) -> None:
    """Display success message for UI remote-only mode."""
    success_message = f"""
[bold green]✓ Successfully created GitHub repository![/bold green]

[bold cyan]Repository Details:[/bold cyan]
  • Name: {project_name}
  • GitHub: {github_url}

[bold cyan]Next Steps:[/bold cyan]

  1. Clone the repository:
     [dim]git clone {github_url}[/dim]
     [dim]cd {project_name}[/dim]

  2. The repository contains the chat UI template.
     See CLAUDE.md for development instructions.

[bold cyan]Note:[/bold cyan]
  The repository contains the raw template.
  You may want to customize project names and paths.
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_sandbox_success_message(
    project_name: str,
    target_path,
    github_url: str | None,
) -> None:
    """Display success message with next steps for sandbox projects."""
    details = f"""  • Name: {project_name}
  • Location: {target_path}"""

    if github_url:
        details += f"\n  • GitHub: {github_url}"

    next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Install dependencies:
     [dim]make install[/dim]

  3. Run tests:
     [dim]make test[/dim]

  4. Build container:
     [dim]make build[/dim]

  5. Build with profile:
     [dim]make build PROFILE=data-science[/dim]"""

    success_message = f"""
[bold green]✓ Successfully created sandbox project![/bold green]

[bold cyan]Project Details:[/bold cyan]
{details}

[bold cyan]Next Steps:[/bold cyan]
{next_steps}

[bold cyan]Documentation:[/bold cyan]
  • See CLAUDE.md for development guide
  • File issues: https://github.com/fips-agents/code-sandbox/issues
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_sandbox_remote_only_success(
    project_name: str,
    github_url: str,
    github_repo: str,
) -> None:
    """Display success message for sandbox remote-only mode."""
    success_message = f"""
[bold green]✓ Successfully created GitHub repository![/bold green]

[bold cyan]Repository Details:[/bold cyan]
  • Name: {project_name}
  • GitHub: {github_url}

[bold cyan]Next Steps:[/bold cyan]

  1. Clone the repository:
     [dim]git clone {github_url}[/dim]
     [dim]cd {project_name}[/dim]

  2. The repository contains the code sandbox template.
     See CLAUDE.md for development instructions.

[bold cyan]Note:[/bold cyan]
  The repository contains the raw template.
  You may want to customize project names and paths.
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_agent_team_success_message(
    project_name: str,
    target_path,
    github_url: str | None,
    github_repo: str | None,
) -> None:
    """Display success message with next steps for agent team projects."""
    details = f"""  • Name: {project_name}
  • Location: {target_path}"""

    if github_url:
        details += f"\n  • GitHub: {github_url}"

    next_steps = f"""
  1. Navigate to your project:
     [dim]cd {target_path.name}[/dim]

  2. Create and activate a virtual environment:
     [dim]python -m venv venv[/dim]
     [dim]source venv/bin/activate[/dim]

  3. Install the project:
     [dim]pip install -e .[dev][/dim]

  4. Design your agent team:
     [dim]# Run /design-team in Claude Code to start designing your agent team[/dim]

  5. Run tests:
     [dim]pytest[/dim]"""

    success_message = f"""
[bold green]✓ Successfully created agent team project![/bold green]

[bold cyan]Project Details:[/bold cyan]
{details}

[bold cyan]Next Steps:[/bold cyan]
{next_steps}

[bold cyan]Documentation:[/bold cyan]
  • Check the README.md in your project for detailed instructions
  • MCP Protocol docs: https://modelcontextprotocol.io/
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))


def _show_agent_team_remote_only_success(
    project_name: str,
    github_url: str,
    github_repo: str,
) -> None:
    """Display success message for agent team remote-only mode."""
    success_message = f"""
[bold green]✓ Successfully created GitHub repository![/bold green]

[bold cyan]Repository Details:[/bold cyan]
  • Name: {project_name}
  • GitHub: {github_url}

[bold cyan]Next Steps:[/bold cyan]

  1. Clone the repository:
     [dim]git clone {github_url}[/dim]
     [dim]cd {project_name}[/dim]

  2. The repository contains the agent team template.
     Customize it for your project.

[bold cyan]Note:[/bold cyan]
  The repository contains the raw template.
  You may want to customize project names and paths.
"""

    console.print(Panel(success_message, border_style="green", padding=(1, 2)))
