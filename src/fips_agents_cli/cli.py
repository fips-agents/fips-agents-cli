"""Main CLI entry point for fips-agents-cli."""

import click
from rich.console import Console

from fips_agents_cli.commands.add import add
from fips_agents_cli.commands.create import create
from fips_agents_cli.commands.deploy import deploy
from fips_agents_cli.commands.generate import generate
from fips_agents_cli.commands.patch import patch
from fips_agents_cli.commands.vendor import vendor
from fips_agents_cli.version import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="fips-agents")
@click.pass_context
def cli(ctx):
    """
    FIPS Agents CLI - A tool for creating and managing FIPS-compliant AI agent projects.

    Use 'fips-agents COMMAND --help' for more information on a specific command.
    """
    ctx.ensure_object(dict)


# Register commands
cli.add_command(add)
cli.add_command(create)
cli.add_command(deploy)
cli.add_command(generate)
cli.add_command(patch)
cli.add_command(vendor)


def main():
    """Main entry point for the CLI application."""
    cli(obj={})


if __name__ == "__main__":
    main()
