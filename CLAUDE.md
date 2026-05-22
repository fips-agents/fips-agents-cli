# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**fips-agents-cli** is a Python-based CLI tool for scaffolding FIPS-compliant AI agent projects. It scaffolds MCP (Model Context Protocol) servers and AI agent projects from production-ready templates, customizes them for new projects, and prepares them for immediate development use.

**Current Status:** Scaffolding commands implemented: `create mcp-server`, `create agent`, `create agent-team`, `create gateway`, `create ui`, `create sandbox`, `create model-car`. Post-scaffolding commands: `generate` (tool, resource, prompt, middleware), `patch` (check, all + type-specific category subcommands — see below), `add` (code-executor, files, vision), `vendor`. Note: `create workflow` exists in code but is not yet working.

The `patch` command is type-aware via `template.type` in `.template-info`:
- **MCP server** projects expose `patch generators | core | docs | build | claude`.
- **Agent / workflow** projects expose `patch chart | docs | build | claude | evals`.
Running an MCP-only subcommand inside an agent project (or vice versa) exits with a clear "available categories" error. `patch check` and `patch all` work for any supported type.

## Development Commands

### Environment Setup

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e .[dev]
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=fips_agents_cli --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/test_create.py

# Run specific test
pytest tests/test_create.py::TestCreateMcpServer::test_successful_creation
```

### Code Quality

```bash
# Format code with Black (line length: 100)
black src tests

# Lint with Ruff
ruff check src tests

# Run both linters before committing
black src tests && ruff check src tests
```

### Building and Distribution

```bash
# Build distribution packages
python -m build

# Verify package integrity
twine check dist/*

# Test local installation
pip install -e .
fips-agents --version
```

### Creating a Release

**Automated Method (Recommended):**

Use the `/create-release` slash command in Claude Code:

```
/create-release
```

This command will:
1. Ask for version number and release notes
2. Update the changelog in README.md
3. Run `scripts/release.sh` to:
   - Update version in `version.py` and `pyproject.toml`
   - Commit and push changes
   - Create and push git tag
   - Trigger GitHub Actions for automated PyPI publishing

**Manual Method:**

**IMPORTANT**: Version numbers must be updated in TWO places:
1. `src/fips_agents_cli/version.py`
2. `pyproject.toml`

```bash
# 1. Update version in both files manually or use the script:
./scripts/release.sh <version> [<summary>]

# Examples:
./scripts/release.sh 0.1.2
./scripts/release.sh 0.1.2 "Add new generator features"

# The script handles:
# - Updating version.py and pyproject.toml
# - Constructing the release commit message from the project convention
# - Committing changes (including README.md changelog)
# - Creating and pushing tag
# - Triggering GitHub Actions
```

**Release commit message convention**: `chore: Release fips-agents-cli vX.Y.Z`,
optionally followed by ` — <summary>`. The script always constructs the message
from the version argument; callers only supply the summary, never the full
message. This keeps `git log --grep "Release fips-agents-cli"` reliable.

**Note**: Always update the changelog in README.md before running the script.

See `RELEASE_CHECKLIST.md` for detailed release procedures and troubleshooting.

## Architecture

### Module Structure

The CLI follows a layered architecture:

1. **CLI Layer** (`cli.py`): Click-based command interface with Rich output
2. **Command Layer** (`commands/`): Command implementations (create, generate, etc.)
3. **Tools Layer** (`tools/`): Reusable utilities for git, filesystem, and project operations
4. **Entry Points**: `__main__.py` for `python -m fips_agents_cli`, `cli:main` for the `fips-agents` command

### Key Design Patterns

**Template Repository Pattern**: The CLI clones git repositories as templates rather than bundling templates internally. This allows:
- Independent template versioning and updates
- User customization via template forks
- Minimal CLI package size

Two cloning strategies exist:
- **Standalone repos** (`clone_template`): Used for MCP servers — clones the entire repo as the project root.
- **Monorepo subdirectory** (`clone_template_subdir`): Used for agents — clones a monorepo to a temp directory, extracts a specific subdirectory, and cleans up.

**MCP Server Customization Pipeline** (`update_project_name`):
1. Clone template repository (shallow clone, depth=1)
2. Remove template's `.git` directory
3. Update `pyproject.toml` with new project name
4. Rename source directory (`template_name` → `project_name` with underscores)
5. Update entry point scripts in `pyproject.toml`
6. Initialize fresh git repository with initial commit

**Agent Customization Pipeline** (`customize_agent_project`):
1. Clone monorepo, extract `templates/agent-loop/` subdirectory
2. Update `pyproject.toml` name field via tomlkit
3. String-replace `agent-template` → new name in Chart.yaml, values.yaml, AGENTS.md, Containerfile, Makefile
4. Source directories are NOT renamed — the agent-loop template ships with `src/agent.py` directly, not a project-named module
5. Initialize fresh git repository with initial commit

**Rich Console Output**: All user-facing output uses Rich library for:
- Colored output (green checkmarks, red errors, yellow warnings)
- Progress spinners for long operations
- Formatted panels for success messages
- Consistent visual style

### Important Implementation Details

**Project Name Handling**: Project names use hyphens (kebab-case) but module names use underscores (snake_case). The `to_module_name()` utility converts between these formats. This is critical for Python import compatibility.

**TOML Manipulation**: Uses `tomlkit` (not `toml`) to preserve formatting and comments in `pyproject.toml` files during customization.

**Git Operations**: Uses GitPython library for all git operations. Template clones are shallow (depth=1) for performance. The `.git` directory from templates is always removed before initializing a fresh repository.

**Error Handling Strategy**: Commands use Rich console for user-friendly error messages, then call `sys.exit()` with appropriate exit codes. Validation failures provide hints for correction.

## Testing Architecture

### Test Structure

Tests are organized by module:
- `test_create.py`: Create command integration tests
- `test_filesystem.py`: Filesystem utility unit tests
- `test_project.py`: Project customization unit tests

### Key Fixtures

**`cli_runner`**: Provides Click's `CliRunner` for command testing. Use `invoke()` to run commands in isolated environment.

**`temp_dir`**: Provides temporary directory that's automatically cleaned up. Use for file operations.

**`mock_template_repo`**: Creates a complete mock MCP server template structure with:
- `pyproject.toml` with placeholder project name
- `src/mcp_server_template/` module directory
- `prompts/` directory for YAML prompts
- `.fips-agents-cli/generators/` for future generator templates

### Testing Patterns

When testing commands:
```python
result = runner.invoke(cli, ["create", "mcp-server", "test-server"])
assert result.exit_code == 0
assert "Success" in result.output
```

When testing with filesystem fixtures:
```python
def test_something(temp_dir):
    project_path = temp_dir / "my-project"
    # Test filesystem operations
```

## Configuration Files

### pyproject.toml

- **Build System**: Uses Hatchling (not Poetry or setuptools)
- **Python Version**: Requires ≥3.10, supports 3.10-3.12 (dropped 3.9 in v0.1.1)
- **Line Length**: Black and Ruff both configured for 100 characters
- **Entry Point**: `fips-agents = "fips_agents_cli.cli:main"`
- **Test Configuration**: pytest runs with coverage by default
- **Version Management**: Version number must match `src/fips_agents_cli/version.py`

### CI/CD Workflows

**test.yml**: Runs on push/PR to main
- Matrix testing across Python 3.10, 3.11, 3.12 (dropped 3.9 support in v0.1.1)
- Runs pytest with coverage
- Checks Black formatting
- Runs Ruff linting
- Builds distribution and validates with twine

**workflow.yaml**: Automated release and PyPI publishing (triggered by version tags)
- Triggers on `v*.*.*` tags (e.g., `v0.1.1`)
- Verifies tag version matches both `version.py` and `pyproject.toml`
- Extracts changelog from README.md
- Creates GitHub Release automatically
- Builds wheels and source distributions
- Publishes to PyPI using trusted publishing (no API key needed)
- **Important**: This single workflow handles the complete release process - DO NOT create separate release workflows

## Common Development Patterns

### Adding a New Command

1. Create command file in `commands/` directory
2. Define Click command group or command
3. Register in `cli.py` with `cli.add_command()`
4. Use Rich console for all output
5. Add comprehensive tests in `tests/test_commandname.py`

### Adding a New Tool/Utility

1. Create utility module in `tools/` directory
2. Import Rich console: `console = Console()`
3. Provide clear docstrings with Args/Returns
4. Return meaningful values (bool, tuple, etc.) not just console output
5. Test in isolation with fixtures

### File Operations Best Practices

- Always use `pathlib.Path`, never string paths
- Use `Path.resolve()` for absolute paths in user-facing messages
- Check existence before operations: `path.exists()`
- Use `parents=True, exist_ok=True` for `mkdir()` calls
- Handle errors gracefully with try/except and user-friendly messages

### Output Conventions

- Success: `[green]✓[/green] Message`
- Error: `[red]✗[/red] Message`
- Warning: `[yellow]⚠[/yellow] Message`
- Info: `[cyan]Message[/cyan]` or `[dim]Message[/dim]`
- Use `console.print()` not `print()` or `click.echo()`

## Known Patterns and Conventions

### Template Repository Structure

**MCP Server Template** (`fips-agents/mcp-server-template` — standalone repo):
- `pyproject.toml` with project name and entry points
- `src/{module_name}/` source directory (renamed during customization)
- `.fips-agents-cli/generators/` for generate commands
- Standard Python project structure

**Agent Template** (`fips-agents/agent-template` — monorepo, `templates/agent-loop/`):
- `pyproject.toml` with project name (no entry point scripts)
- `src/agent.py` user agent subclass (lives at this path directly — no project-named module wrapper)
- `chart/` Helm chart for OpenShift deployment
- `agent.yaml` configuration (customized via `/plan-agent`, not during scaffolding)
- `.claude/commands/` with agent development slash commands

### Project Name Validation

Valid project names must:
- Start with a lowercase letter
- Contain only lowercase letters, numbers, hyphens, and underscores
- Not be empty

Examples:
- ✅ `my-server`, `test_mcp`, `server123`
- ❌ `MyServer` (uppercase), `123server` (starts with number), `my@server` (special chars)

### Module vs Project Names

- **Project name**: Uses hyphens (e.g., `my-mcp-server`)
- **Module name**: Uses underscores (e.g., `my_mcp_server`)
- Conversion: `project_name.replace("-", "_")`
- This matters for imports and directory names

## Implementation Notes

- Don't remove `.fips-agents-cli/` directories during MCP template cloning — they contain generator templates
- Agent template customization uses string replacement, NOT source directory renaming
- The agent template repo is a monorepo — `clone_template_subdir` handles the extraction

## Troubleshooting Common Issues

### Git Clone Failures

Check:
1. Internet connectivity
2. Template repository URL is accessible
3. Git is installed: `git --version`
4. Permissions on target directory

### Module Not Found After Installation

Ensure:
1. Virtual environment is activated
2. Package installed with `-e` flag: `pip install -e .`
3. Using correct Python interpreter: `which python`

### Test Failures

Common causes:
1. Forgot to activate venv
2. Dependencies not installed: `pip install -e .[dev]`
3. Git not configured globally: `git config --global user.email "test@example.com"`

## Release Process Notes

When creating a new release, always update the changelog in README.md *before* running the release script. The changelog lives in the README under the `## Changelog` heading. Each version should have its own section with the version number and date, listing new features, fixes, and breaking changes. Forgetting the changelog entry leads to patch releases (like v0.8.1) that exist solely to backfill documentation — avoid that by treating the changelog update as a required step in every release.

## Repository-Specific Notes

- The main branch is `main` (not `master`)
- MCP template URL: `https://github.com/fips-agents/mcp-server-template`
- Agent template URL: `https://github.com/fips-agents/agent-template` (monorepo, subdir `templates/agent-loop`)
- Package name on PyPI: `fips-agents-cli`
- Command name: `fips-agents` (no `-cli` suffix)
- Recommended installation: `pipx install fips-agents-cli`
