# FIPS Agents CLI

A command-line tool for creating and managing FIPS-compliant AI agent projects. Scaffolds MCP (Model Context Protocol) servers, AI agent projects, and ModelCar containers from production-ready templates.

## Features

- 🚀 Quick project scaffolding from templates
- 📦 MCP server, AI agent, agent team, Go gateway, chat UI, sandbox, and ModelCar project generation
- 🔧 Automatic project customization (pyproject.toml, module names, entry points)
- ⚡ Component generation (tools, resources, prompts, middleware) with Jinja2 templates
- 🎨 Beautiful CLI output with Rich
- ✅ Git repository initialization and GitHub integration
- 🧪 Comprehensive test coverage with auto-run on generated components
- 🔄 Template patching to pull upstream improvements into existing projects

## Installation

**Recommended:** Install with [pipx](https://pipx.pypa.io/) for isolated command-line tools:

```bash
pipx install fips-agents-cli
```

pipx installs the CLI in an isolated environment while making it globally available. This prevents dependency conflicts with other Python packages.

<details>
<summary><b>Alternative: Using pip</b></summary>

If you prefer pip or don't have pipx installed:

```bash
pip install fips-agents-cli
```

**Note:** Consider using a virtual environment to avoid dependency conflicts.

</details>

<details>
<summary><b>Alternative: Install from source (for development)</b></summary>

For contributing or local development:

```bash
# Clone the repository
git clone https://github.com/fips-agents/fips-agents-cli.git
cd fips-agents-cli

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e .[dev]
```

</details>

## Quick Start

### Create projects

```bash
# MCP server
fips-agents create mcp-server my-mcp-server

# AI agent
fips-agents create agent my-research-agent

# Agent team design workspace
fips-agents create agent-team my-team

# Go HTTP gateway (proxies to an agent backend)
fips-agents create gateway my-gateway

# Chat UI (connects to a gateway or agent)
fips-agents create ui my-chat-ui

# Code execution sandbox (sidecar for agents)
fips-agents create sandbox my-sandbox

# ModelCar (HuggingFace model as container)
fips-agents create model-car ibm-granite/granite-3.1-2b-instruct \
    quay.io/user/models:granite-3.1-2b-instruct
```

### Generate components in an existing MCP server project

```bash
cd my-mcp-server

fips-agents generate tool search_documents --description "Search through documents"
fips-agents generate resource config_data --description "Application configuration"
fips-agents generate prompt code_review --description "Review code for best practices"
fips-agents generate middleware auth_middleware --description "Authentication middleware"
```

### Check for template updates

```bash
cd my-mcp-server

fips-agents patch check
fips-agents patch all --dry-run
```

## Command Reference

### Help

```bash
fips-agents --version
fips-agents --help
fips-agents add --help
fips-agents create --help
fips-agents generate --help
fips-agents patch --help
fips-agents vendor --help
```

---

### Create Commands

The `create` command group scaffolds new projects from templates.

#### Shared Options (mcp-server, agent, gateway, ui)

All `create` subcommands (except `model-car`) accept the same options:

| Option | Description |
|--------|-------------|
| `--target-dir, -t PATH` | Target directory for the project (default: current directory) |
| `--no-git` | Skip git repository initialization |
| `--github` | Create GitHub repository and push code |
| `--local` | Create local project only (skip GitHub) |
| `--yes, -y` | Non-interactive mode (use defaults, skip prompts) |
| `--private` | Make GitHub repository private (default: public) |
| `--org TEXT` | GitHub organization to create repository in |
| `--description, -d TEXT` | GitHub repository description |
| `--remote-only` | Create GitHub repo only, don't clone locally |

When `gh` CLI is installed and authenticated, the tool prompts interactively about GitHub repo creation. Use `--local` to suppress this, `--github` to require it, or `--yes` for fully non-interactive operation.

#### `create mcp-server`

```bash
fips-agents create mcp-server <project-name> [OPTIONS]
```

Creates an MCP server project from the [mcp-server-template](https://github.com/fips-agents/mcp-server-template) repository. The template includes FastMCP server bootstrap, component auto-discovery, Jinja2 generator templates, Makefile, Containerfile, and tests.

**Arguments:**

- `project-name` — Name for your MCP server project

**Examples:**

```bash
# Create in current directory
fips-agents create mcp-server my-mcp-server

# Create in specific directory without git
fips-agents create mcp-server my-server -t ~/projects --no-git

# Create with private GitHub repo in an organization
fips-agents create mcp-server my-server --github --private --org my-org

# Non-interactive, local only
fips-agents create mcp-server my-server --yes --local

# Create GitHub repo without cloning locally
fips-agents create mcp-server my-server --remote-only --org my-org
```

#### `create agent`

```bash
fips-agents create agent <project-name> [OPTIONS]
```

Creates an AI agent project from the [agent-template](https://github.com/fips-agents/agent-template) monorepo (`templates/agent-loop/` subdirectory). The template includes an agent loop skeleton, Helm chart, Makefile, Containerfile, and AGENTS.md.

**Arguments:**

- `project-name` — Name for your agent project

**Options:** Same as `create mcp-server` (see shared options table above).

**Additional option:**

| Option | Description |
|--------|-------------|
| `--vendored` | Copy fipsagents source into the project instead of using PyPI dependency |

**Examples:**

```bash
# Create agent project
fips-agents create agent my-research-agent

# Create with GitHub repo in an organization
fips-agents create agent my-agent --github --org fips-agents

# Non-interactive mode
fips-agents create agent my-agent --yes --local

# Create with vendored fipsagents source
fips-agents create agent my-agent --vendored --local
```

#### `create agent-team`

```bash
fips-agents create agent-team <project-name> [OPTIONS]
```

Creates an agent team design workspace from the [agent-team-template](https://github.com/fips-agents/agent-team-template) repository. The template includes `/design-team` skill for iterative team design dialog, BPMN 2.0 parser, output generators for agent.yaml stubs and team manifests, and trust/scrutiny profiling.

**Arguments:**

- `project-name` — Name for your agent team project

**Options:** Same shared options as above.

**Examples:**

```bash
# Create agent team project
fips-agents create agent-team my-team

# Create with GitHub repo
fips-agents create agent-team my-team --github --private

# Non-interactive mode
fips-agents create agent-team my-team --yes --local
```

#### `create gateway`

```bash
fips-agents create gateway <project-name> [OPTIONS]
```

Creates a Go HTTP gateway project from the [gateway-template](https://github.com/fips-agents/gateway-template) repository. The gateway proxies OpenAI-compatible `/v1/chat/completions` requests to an agent backend, with SSE streaming support, heartbeat keepalives, health/readiness probes, and an A2A agent discovery card.

**Arguments:**

- `project-name` — Name for your gateway project

**Options:** Same shared options as above.

**Examples:**

```bash
# Create gateway project
fips-agents create gateway my-gateway

# Create with GitHub repo
fips-agents create gateway my-gateway --github --org my-org
```

#### `create ui`

```bash
fips-agents create ui <project-name> [OPTIONS]
```

Creates a chat UI project from the [ui-template](https://github.com/fips-agents/ui-template) repository. A Go server with embedded HTML/CSS/JS that provides a browser-based chat interface. Includes a built-in reverse proxy to the backend API, SSE streaming, and markdown rendering.

**Arguments:**

- `project-name` — Name for your UI project

**Options:** Same shared options as above.

**Examples:**

```bash
# Create UI project
fips-agents create ui my-chat-ui

# Create with GitHub repo
fips-agents create ui my-chat-ui --github --private
```

#### `create sandbox`

```bash
fips-agents create sandbox <project-name> [OPTIONS]
```

Creates a code execution sandbox project from the [code-sandbox](https://github.com/fips-agents/code-sandbox) repository. The sandbox provides a FastAPI-based sidecar for secure code execution inside agent pods, with multiple language profiles (base, data-science).

**Arguments:**

- `project-name` -- Name for your sandbox project

**Options:** Same shared options as above.

**Examples:**

```bash
# Create sandbox project
fips-agents create sandbox my-sandbox

# Create with GitHub repo
fips-agents create sandbox my-sandbox --github --private

# Non-interactive mode
fips-agents create sandbox my-sandbox --yes --local
```

#### `create model-car`

```bash
fips-agents create model-car <hf-repo> <quay-uri> [OPTIONS]
```

Creates a ModelCar project for packaging a HuggingFace model as a container image. Generates download scripts, Containerfile, build-and-push scripts, and project metadata.

**Arguments:**

- `hf-repo` — HuggingFace repo URL or ID (e.g., `ibm-granite/granite-3.1-2b-instruct` or the full `https://huggingface.co/...` URL)
- `quay-uri` — Container registry URI with tag (e.g., `quay.io/user/models:granite-3.1-2b-instruct`)

**Options:**

| Option | Description |
|--------|-------------|
| `--target-dir, -t PATH` | Target directory for the project (default: current directory) |

**Examples:**

```bash
# Using repo ID
fips-agents create model-car ibm-granite/granite-3.1-2b-instruct \
    quay.io/wjackson/models:granite-3.1-2b-instruct

# Using full URL with custom target directory
fips-agents create model-car https://huggingface.co/ibm-granite/granite-3.1-2b-instruct \
    quay.io/wjackson/models:granite-3.1-2b-instruct -t ~/models
```

---

### Generate Commands

The `generate` command group creates individual components (tools, resources, prompts, middleware) in existing projects.

**Run these commands from within your MCP server project directory.** The CLI locates the project root by looking for `pyproject.toml` with a `fastmcp` dependency.

Each generator:
1. Validates the component name and checks for conflicts
2. Loads Jinja2 templates from `.fips-agents-cli/generators/` in your project
3. Renders both the component file and a corresponding test file
4. Validates Python syntax on the generated code
5. Runs the generated tests automatically

Component names must be valid Python identifiers in `snake_case`. Subdirectory paths (e.g., `country-profiles/japan`) are supported for resources.

#### `generate tool`

```bash
fips-agents generate tool <name> [OPTIONS]
```

Generates a tool component with FastMCP `@mcp.tool()` decorator.

**Options:**

| Option | Description |
|--------|-------------|
| `--async/--sync` | Generate async or sync function (default: async) |
| `--with-context` | Include FastMCP Context parameter |
| `--with-auth` | Include authentication decorator |
| `--scopes TEXT` | Required OAuth scopes, comma-separated (e.g., `"read:data,write:data"`) |
| `--with-elicitation` | Include elicitation example code |
| `--description, -d TEXT` | Tool description |
| `--params PATH` | JSON file with parameter definitions |
| `--read-only` | Mark as read-only operation (default: true) |
| `--idempotent` | Mark as idempotent (default: true) |
| `--open-world` | Mark as open-world operation |
| `--return-type TEXT` | Return type annotation (default: `str`) |
| `--dry-run` | Show what would be generated without creating files |

**Examples:**

```bash
# Basic tool
fips-agents generate tool search_documents --description "Search through documents"

# Tool with context and authentication
fips-agents generate tool fetch_user_data --with-context --with-auth --scopes "read:users"

# Tool with parameters from JSON file
fips-agents generate tool advanced_search --params params.json

# Sync tool with custom return type
fips-agents generate tool process_data --sync --return-type "dict[str, Any]"

# Preview without creating files
fips-agents generate tool test_tool --description "Test" --dry-run
```

#### `generate resource`

```bash
fips-agents generate resource <name> [OPTIONS]
```

Generates a resource component with FastMCP `@mcp.resource()` decorator. Supports subdirectory paths (e.g., `country-profiles/japan` creates `src/resources/country_profiles/japan.py`). URI template parameters (e.g., `{id}`) are automatically extracted as function arguments.

**Options:**

| Option | Description |
|--------|-------------|
| `--async/--sync` | Generate async or sync function (default: async) |
| `--with-context` | Include FastMCP Context parameter |
| `--description, -d TEXT` | Resource description |
| `--uri TEXT` | Resource URI (default: `resource://<name>`) |
| `--mime-type TEXT` | MIME type (default: `text/plain`) |
| `--dry-run` | Show what would be generated without creating files |

**Examples:**

```bash
# Basic resource
fips-agents generate resource config_data --description "Application configuration"

# Resource with URI template (parameters auto-extracted as function args)
fips-agents generate resource user_profile --uri "resource://users/{id}"

# Resource in a subdirectory
fips-agents generate resource country-profiles/japan --description "Japan country profile"

# Resource with specific MIME type
fips-agents generate resource json_config --mime-type "application/json"
```

#### `generate prompt`

```bash
fips-agents generate prompt <name> [OPTIONS]
```

Generates a prompt component with FastMCP `@mcp.prompt()` decorator. Note: prompts default to **sync** (unlike tools and resources which default to async).

**Options:**

| Option | Description |
|--------|-------------|
| `--async/--sync` | Generate async or sync function (default: **sync**) |
| `--with-context` | Include FastMCP Context parameter |
| `--description, -d TEXT` | Prompt description |
| `--params PATH` | JSON file with parameter definitions |
| `--return-type [str\|Message\|list[Message]]` | Return type (default: `str`) |
| `--with-schema` | Include JSON schema example in prompt body |
| `--prompt-name TEXT` | Override decorator name (default: function name) |
| `--title TEXT` | Human-readable title for the prompt |
| `--tags TEXT` | Comma-separated tags for categorization |
| `--disabled` | Generate prompt in disabled state |
| `--meta TEXT` | JSON string of metadata (e.g., `'{"version": "1.0"}'`) |
| `--dry-run` | Show what would be generated without creating files |

**Examples:**

```bash
# Basic prompt
fips-agents generate prompt code_review --description "Review code for best practices"

# Prompt with parameters and schema
fips-agents generate prompt summarize_text --params params.json --with-schema

# Async prompt returning a Message
fips-agents generate prompt fetch_data --async --with-context --return-type Message

# Prompt with metadata and tags
fips-agents generate prompt generate_report \
    --prompt-name "report_generator" \
    --title "Report Generator" \
    --tags "reporting,analysis" \
    --meta '{"version": "2.0", "author": "data-team"}'
```

#### `generate middleware`

```bash
fips-agents generate middleware <name> [OPTIONS]
```

Generates a middleware component using FastMCP's `@mcp.middleware()` decorator (v3.x class-based pattern). Middleware wraps tool execution and receives a Context and `next_handler`.

**Options:**

| Option | Description |
|--------|-------------|
| `--async/--sync` | Generate async or sync function (default: async) |
| `--hook-type [before_tool\|after_tool\|on_error]` | Scaffold a specific hook pattern (default: general wrapper) |
| `--description, -d TEXT` | Middleware description |
| `--dry-run` | Show what would be generated without creating files |

**Examples:**

```bash
# General-purpose wrapper
fips-agents generate middleware auth_middleware --description "Authentication middleware"

# Before-tool hook
fips-agents generate middleware rate_limiter --hook-type before_tool

# Error handler (sync)
fips-agents generate middleware error_reporter --hook-type on_error --sync
```

#### Parameters JSON Schema

When using `--params` with `generate tool` or `generate prompt`, provide a JSON file defining parameter names, types, and constraints:

```json
[
  {
    "name": "query",
    "type": "str",
    "description": "Search query",
    "required": true,
    "min_length": 1,
    "max_length": 100
  },
  {
    "name": "limit",
    "type": "int",
    "description": "Maximum results to return",
    "required": false,
    "default": 10,
    "ge": 1,
    "le": 100
  }
]
```

**Supported Types:**
- `str`, `int`, `float`, `bool`
- `list[str]`, `list[int]`, `list[float]`
- `Optional[str]`, `Optional[int]`, `Optional[float]`, `Optional[bool]`

**Pydantic Field Constraints:**
- `min_length`, `max_length` (for strings)
- `ge`, `le`, `gt`, `lt` (for numbers)
- `pattern` (for regex validation on strings)
- `default` (default value when optional)

---

### Patch Commands

The `patch` command group updates files in existing projects from the upstream template repository without overwriting your custom code. It shows interactive diffs for files that may contain customizations.

Supported project types: **MCP server**, **agent**, **workflow**, **gateway**, **UI**. The available category subcommands depend on the project type — `patch` reads `template.type` from `.template-info` and surfaces a clear error if you run a category that doesn't apply (e.g. `patch generators` inside an agent project).

Templates can declare their own patch categories by shipping a `.fips-template.yaml` manifest at the repo root (or, for monorepo templates, at the comparison subdir root). The CLI prefers the manifest when present and falls back to a built-in category set otherwise. Gateway and UI projects are patchable only because their templates ship a manifest.

Run these commands from within your project directory.

#### `patch check`

```bash
fips-agents patch check
```

Check for available template updates. Shows what files have changed in the template since your project was created, organized by category. Works for any supported project type.

#### `patch all`

```bash
fips-agents patch all [--dry-run] [--skip-confirmation]
```

Update every category that applies to the current project type. Prompts for confirmation before starting unless `--skip-confirmation` is passed.

#### MCP server categories

| Subcommand           | Patches                                                                  |
|----------------------|--------------------------------------------------------------------------|
| `patch generators`   | Jinja2 templates in `.fips-agents-cli/generators/`                       |
| `patch core`         | Core infrastructure (`src/main.py`, `src/core/server.py`, package inits) |
| `patch docs`         | `CLAUDE.md`, `AGENTS.md`, `ARCHITECTURE.md`, `TESTING.md`, `docs/**`     |
| `patch build`        | `Makefile`, `Containerfile`, `.dockerignore`, `.gitignore`               |
| `patch claude`       | Claude Code slash commands (`.claude/commands/**`)                       |

#### Agent / workflow categories

| Subcommand     | Patches                                                                       |
|----------------|-------------------------------------------------------------------------------|
| `patch chart`  | Helm chart templates (`chart/templates/**`, `chart/Chart.yaml`)                |
| `patch docs`   | `CLAUDE.md`, `AGENTS.md`, `docs/**`                                            |
| `patch build`  | `Makefile`, `Containerfile`, `deploy.sh`, `redeploy.sh`                        |
| `patch claude` | Claude Code slash commands and rules (`.claude/commands/**`, `.claude/rules/**`) |
| `patch evals`  | Eval harness (`evals/discovery.py`, `evals/assertions.py`, `evals/run_evals.py`) |

#### Gateway / UI categories

| Subcommand     | Patches                                                              |
|----------------|----------------------------------------------------------------------|
| `patch chart`  | Helm chart templates (`chart/templates/**`, `chart/Chart.yaml`)       |
| `patch docs`   | `CLAUDE.md`, `llms.txt`, `docs/**`                                    |
| `patch build`  | `Makefile`, `Containerfile`, `.containerignore`, `.gitignore`         |

User-customized files are never patched: for MCP this means `src/tools/`, `src/resources/`, `src/prompts/`, `src/middleware/`, `pyproject.toml`, etc. For agent/workflow it means `src/agent.py`, `agent.yaml`, `chart/values.yaml`, `src/fipsagents/**` (managed by `fips-agents vendor`), `tools/**`, `examples/**`, `prompts/**`, `rules/**`, `skills/**`, `evals/evals.yaml`, `evals/fixtures/**`, and `pyproject.toml`. For gateway/UI it means `cmd/**`, `internal/**`, `go.mod`, `go.sum`, `chart/values.yaml`, `static/**` (UI only), `bin/**`, and `LICENSE`.

All patch subcommands (except `check`) accept `--dry-run` to preview changes without modifying files.

---

### Add Commands

The `add` command group wires optional capabilities into existing agent projects created with `fips-agents create agent`.

**Run these commands from within your agent project directory.** The CLI locates the project root by looking for `.template-info` (or `agent.yaml` for legacy projects).

#### `add files`

```bash
fips-agents add files
```

Enables file upload + attachment support. Flips `server.files.enabled` in `agent.yaml` and `files.enabled` in `chart/values.yaml`. The agent template already ships the rest of the files surface (storage backends, optional S3 bytes backend, ClamAV virus-scanner sidecar, Docling PDF/text extraction, pgvector chunking) — this command only wires up the toggles.

**What it does:**

1. Sets `server.files.enabled: true` in `agent.yaml`
2. Sets `files.enabled: true` in `chart/values.yaml`
3. Prints next steps for installing the `[files]` extra, choosing a backend (`sqlite` / `postgres`), enabling ClamAV, and enabling persistence

**Example:**

```bash
cd my-research-agent
fips-agents add files
pip install -e '.[files]'
export FILES_BACKEND=sqlite
```

#### `add code-executor`

```bash
fips-agents add code-executor
```

Adds the `code_executor` tool to your agent's `tools/` directory and enables the sandbox sidecar in `chart/values.yaml`. The tool sends Python code to a sandbox container for isolated execution.

**What it does:**

1. Writes `tools/code_executor.py` with the sandbox client tool
2. Sets `sandbox.enabled: true` in `chart/values.yaml` (if the section exists)
3. Prints deployment guidance for sidecar and remote service modes

**Deployment modes:**

- **Sidecar** (default): The sandbox runs as a container in the same pod. The tool connects to `http://localhost:8000`.
- **Remote service**: The sandbox runs as a separate deployment. Set `SANDBOX_URL` to point to it.

**Example:**

```bash
cd my-research-agent
fips-agents add code-executor
```

#### `add vision`

```bash
fips-agents add vision
```

Wires multimodal (image input) example client code into your project. Drops `examples/vision_client.py` showing the three `image_url` URL forms the agent runtime accepts: inline `data:` URIs, remote `https://` URLs, and the internal `file_id:<id>` scheme that the agent rewrites to a `data:` URI server-side.

Image input flows through the agent's existing `model.endpoint` — there is no separate vision endpoint split. Set `MODEL_ENDPOINT` and `MODEL_NAME` to a vision-capable model (e.g. Granite Vision 3.2-2B, LLaVA, Phi-4-Multimodal) before running the agent.

**Prerequisite:** `fips-agents add files` must have been run first. The `file_id:<id>` URL scheme resolves bytes via the agent's `BytesStore`, which only exists when files is enabled. The command refuses to apply if `server.files.enabled` is not `true` in `agent.yaml`.

**Requires:** `fipsagents>=0.20.0` in the project's dependencies (content-block support landed in 0.20.0).

**What it does:**

1. Verifies `server.files.enabled: true` in `agent.yaml` (precondition)
2. Writes `examples/vision_client.py` with runnable snippets for all three URL forms

**Example:**

```bash
cd my-research-agent
fips-agents add files     # prerequisite
fips-agents add vision
export MODEL_ENDPOINT=https://granite-vision-3-2-2b-...:443/v1
export MODEL_NAME=ibm-granite/granite-vision-3.2-2b
make run-local
python examples/vision_client.py path/to/image.png
```

---

### Vendor Commands

The `vendor` command copies the fipsagents source into your agent project, replacing the PyPI dependency. This gives you full control over the fipsagents code.

#### `vendor`

```bash
fips-agents vendor [OPTIONS]
```

Copies fipsagents source into `src/fipsagents/` and rewrites `pyproject.toml` to use individual dependencies instead of the fipsagents package.

**Options:**

| Option | Description |
|--------|-------------|
| `--update` | Update an already-vendored project with the latest upstream source |
| `--version TEXT` | Vendor a specific version tag (e.g., `fipsagents-v0.7.0`). Default: latest main |

**Examples:**

```bash
# Vendor into current project
fips-agents vendor

# Vendor a specific version
fips-agents vendor --version fipsagents-v0.7.0

# Update vendored source from upstream
fips-agents vendor --update
```

**When to use vendored vs. PyPI:**

- **PyPI dependency** (default): Best for teams running multiple agents that share the same fipsagents version. Centralized updates.
- **Vendored source**: Best for agents that need custom BaseAgent modifications, environments with no PyPI access, or when you want to read and debug the fipsagents source locally.

## Project Name Requirements

Project names must follow these rules:
- Start with a lowercase letter
- Contain only lowercase letters, numbers, hyphens (`-`), and underscores (`_`)
- Not be empty

**Valid examples:** `my-server`, `test_mcp`, `server123`, `my-awesome-mcp-server`

**Invalid examples:** `MyServer` (uppercase), `123server` (starts with number), `my@server` (special characters)

## After Creating a Project

### MCP Server

```bash
cd my-mcp-server
python -m venv venv
source venv/bin/activate
pip install -e .[dev]
pytest
# Start developing in src/my_mcp_server/
```

### AI Agent

```bash
cd my-research-agent
make install         # Create venv, install dependencies
make run-local       # Start HTTP server on port 8080
make test            # Run tests
# See AGENTS.md for the /plan-agent slash command workflow
```

### Gateway

```bash
cd my-gateway
make build           # Build the Go binary
make run             # Run locally (set BACKEND_URL to your agent)
make build-openshift PROJECT=my-gateway  # Build on OpenShift
make deploy PROJECT=my-gateway           # Deploy via Helm
```

### Chat UI

```bash
cd my-chat-ui
make build           # Build the Go binary
make run             # Run locally (set API_URL to your gateway/agent)
make build-openshift PROJECT=my-chat-ui  # Build on OpenShift
make deploy PROJECT=my-chat-ui           # Deploy via Helm
```

### Sandbox

```bash
cd my-sandbox
make install             # Install dependencies
make test                # Run tests
make build               # Build container
make build PROFILE=data-science  # Build with profile
```

### ModelCar

```bash
cd granite-3.1-2b-instruct
./download.sh        # Download model weights
./build-and-push.sh  # Build container and push to registry
```

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/fips-agents/fips-agents-cli.git
cd fips-agents-cli

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e .[dev]
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=fips_agents_cli --cov-report=html

# Run specific test file
pytest tests/test_create.py

# Run specific test
pytest tests/test_create.py::TestCreateMcpServer::test_successful_creation
```

### Code Quality

```bash
# Format code with Black
black src tests

# Lint with Ruff
ruff check src tests

# Type checking (if using mypy)
mypy src
```

### Project Structure

```
fips-agents-cli/
├── pyproject.toml          # Project configuration
├── README.md               # This file
├── CLAUDE.md               # Claude Code developer instructions
├── RELEASE_CHECKLIST.md    # Release procedures
├── docs/                   # User-facing documentation
├── planning/               # Design and implementation plans
├── research/               # Technology evaluations
├── retrospectives/         # Post-effort retrospectives
├── scripts/                # Automation scripts
├── src/
│   └── fips_agents_cli/
│       ├── __init__.py
│       ├── __main__.py     # Entry point for python -m
│       ├── cli.py          # Main CLI application
│       ├── version.py      # Version information
│       ├── commands/       # CLI command implementations
│       │   ├── add.py      # add files / code-executor (wire capabilities)
│       │   ├── create.py   # create mcp-server, agent, gateway, ui
│       │   ├── generate.py # generate tool/resource/prompt/middleware
│       │   ├── model_car.py # create model-car
│       │   ├── patch.py    # patch command
│       │   └── vendor.py   # vendor fipsagents source
│       └── tools/          # Utility modules
│           ├── filesystem.py
│           ├── git.py
│           ├── github.py
│           ├── project.py
│           └── validation.py
└── tests/
    ├── conftest.py         # Pytest fixtures
    ├── test_create.py      # Create command tests
    ├── test_project.py     # Project utilities tests
    └── ...
```

## Documentation

- **[docs/](docs/)** — User-facing reference: publishing guides, release procedures
- **[planning/](planning/)** — Design documents and implementation plans for upcoming features
- **[research/](research/)** — Technology evaluations and architectural analysis
- **[retrospectives/](retrospectives/)** — Post-effort retrospectives

See [docs/README.md](docs/README.md) for a full index.

## Requirements

- Python 3.10 or higher
- Git (for cloning templates and initializing repositories)

## Dependencies

- **click** (>=8.1.0): Command-line interface creation
- **rich** (>=13.0.0): Terminal output formatting
- **gitpython** (>=3.1.0): Git operations
- **tomlkit** (>=0.12.0): TOML file manipulation
- **jinja2** (>=3.1.2): Template rendering for component generation

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Format code (`black src tests`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Troubleshooting

### Git not found

If you see "Git is not installed" error:
- **macOS**: `brew install git`
- **Linux**: `sudo apt-get install git` or `sudo yum install git`
- **Windows**: Download from https://git-scm.com/downloads

### Directory already exists

If you see "Directory already exists" error:
- Choose a different project name
- Remove the existing directory: `rm -rf project-name`
- Use a different target directory with `--target-dir`

### Template clone fails

If template cloning fails:
- Check your internet connection
- Verify the template repository is accessible: https://github.com/fips-agents/mcp-server-template
- Try again later if GitHub is experiencing issues

### Agent template clone fails

If cloning the agent template fails:
- The agent template is in a monorepo at https://github.com/fips-agents/agent-template
- Verify the repository is accessible and the `templates/agent-loop/` subdirectory exists
- Check that you have access to the organization's repositories

### ModelCar validation errors

- **Invalid HuggingFace repo**: Use either a full URL (`https://huggingface.co/org/model`) or a short ID (`org/model`)
- **Invalid Quay URI**: Must include a tag (e.g., `quay.io/user/repo:tag`), not just `quay.io/user/repo`
- **Registry login**: The CLI checks for `podman login` status; run `podman login quay.io` if prompted

### "Not in an MCP server project directory"

When using `generate` or `patch` commands:
- Ensure you're running the command from within an MCP server project
- Check that `pyproject.toml` exists with `fastmcp` dependency
- If the project wasn't created with `fips-agents create mcp-server`, generator templates may be missing

### "Component already exists"

If you see this error:
- Choose a different component name
- Manually remove the existing component file from `src/<component-type>/`
- Check the component type directory for existing files

### Invalid component name

Component names must:
- Be valid Python identifiers (snake_case)
- Not be Python keywords (`for`, `class`, etc.)
- Start with a letter or underscore
- Contain only letters, numbers, and underscores

## License

MIT License - see LICENSE file for details

## Links

- **Repository**: https://github.com/fips-agents/fips-agents-cli
- **Issues**: https://github.com/fips-agents/fips-agents-cli/issues
- **MCP Protocol**: https://modelcontextprotocol.io/

## Changelog

### Version 0.13.1

- Fix: `create agent-team` now correctly matches the template's actual sentinels (`agent-team-design` script key, `agent_team_design` module name in non-Python files, `packages` path in pyproject.toml). Previously the script key wasn't renamed and supporting `.md` files kept stale module references

### Version 0.13.0

- Feature: New `fips-agents create agent-team` subcommand scaffolds agent team design workspaces from the [agent-team-template](https://github.com/fips-agents/agent-team-template) repository (#52). Follows the standalone-repo pattern: clones the template, renames `src/agent_team_design/` to the new module name, updates pyproject.toml entry points, and replaces sentinel strings in supporting files. Success message directs users to the `/design-team` skill in Claude Code for iterative team design

### Version 0.12.1

- Fix: `fips-agents patch check`, `patch <category>`, and `patch all` now produce a single-line ✗ error instead of a Python traceback when run against a project whose template type is not in the built-in category set AND ships no `.fips-template.yaml` manifest. Today this hits sandbox projects (whose template repo has not yet shipped a manifest); the message names the project type, points at the manifest filename, and links to issue #45 for the schema (#50, #51)
- Tests: 9 new tests in `tests/test_patch.py` — 4 unit cases on the new `PatchUnsupportedForProjectType` exception, 4 integration cases exercising the three CLI entry points against a fake sandbox project, and a future-proofing test confirming that once a sandbox manifest exists, `patch check` works without further CLI changes

### Version 0.12.0

- Feature: `fips-agents patch` now reads `.fips-template.yaml` from cloned templates and uses it as the source of truth for patch categories and never-patch lists, falling back to the hardcoded constants when the file is absent or malformed (#45, #48). Each template repo can declare what is template-managed vs user-authored without a CLI release. Companion manifests landed in `agent-template`, `mcp-server-template`, `gateway-template`, and `ui-template` — gateway/ui projects, which previously raised `ValueError` from `patch check`, now opt in to patching via their manifest
- Feature: New `evals` category for agent / workflow projects covers the eval harness (`evals/discovery.py`, `evals/assertions.py`, `evals/mock_factory.py`, `evals/run_evals.py`, `evals/__init__.py`, `evals/README.md`) (#44, #46). User-authored `evals/evals.yaml` and `evals/fixtures/` stay in `AGENT_NEVER_PATCH`
- Feature: New `claude` category for MCP server projects covers `.claude/commands/**/*` (#42, #43). Agent `claude` category extended to also include `.claude/rules/**/*`
- Fix: The MCP `core` patterns had a literal-space typo (`src/*/__ init__.py`) that matched nothing — package `__init__.py` files were silently unreachable via `patch core`. Pattern fixed and `src/main.py` (the entry point) added to the category (#42, #43)
- Fix: `_should_never_patch` switched from `Path.match` to `fnmatch.fnmatchcase` so a bare `"README.md"` entry no longer locks out nested READMEs like `evals/README.md` (#47, #49). Other patterns behave identically; over-matching `**` patterns is strictly safer for never-patch
- Fix: Several pre-existing pattern gaps filled — MCP `docs` now lists `AGENTS.md`, `CONTRIBUTING.md`, `DEVELOPMENT_PROCESS.md`, `OPENSHIFT_DEPLOYMENT.md`; MCP `build` now lists `.dockerignore`, `.gitignore`, `.gitleaks.toml`; `AGENT_NEVER_PATCH` extended with `tools/**`, `examples/**`, `prompts/**`, `rules/**`, `skills/**`, `.memoryhub.yaml` (#42, #43)
- Tests: 48 new tests in `tests/test_patch.py` covering the manifest loader, schema validation, fallback paths, the new categories, the matcher fix, and an integration test that exercises `patch check` end-to-end against a fake template that ships its own manifest

### Version 0.11.1

- Fix: `fips-agents create` no longer hangs on the `Create GitHub repository?` prompt in non-interactive shells (CI, agent-driven, piped input). All six `create` subcommands share a single `_determine_github_mode` helper, so `gateway`, `ui`, `mcp-server`, `agent`, `workflow`, and `sandbox` are fixed together. Non-TTY stdin now falls through to local mode with a one-line hint pointing to `--github` / `--yes`; the prompt is also wrapped in `try/except click.exceptions.Abort` as defense in depth (#40, #41)
- Fix: Six `Unexpected error: {e}` sites now use `{e!r}` so a swallowed empty-message exception (the original symptom of #40, where `click.Abort` rendered as a blank message) surfaces its type instead of going silent
- Tests: 8 new cases in `TestDetermineGithubMode` covering flag short-circuits, gh-missing/unauthenticated, `--yes`, and the new TTY / non-TTY / aborted-confirm paths

### Version 0.11.0

- Feature: New `fips-agents add vision` command wires multimodal (image input) example client code into existing agent projects (#20, #39). Drops `examples/vision_client.py` showing the three `image_url` URL forms the agent runtime accepts: inline `data:` URIs, remote `https://` URLs, and the internal `file_id:<id>` scheme that the agent rewrites to a `data:` URI server-side via the configured `BytesStore`. Image input flows through the agent's existing `model.endpoint` — no separate vision endpoint split. Set `MODEL_ENDPOINT` and `MODEL_NAME` to a vision-capable model (Granite Vision 3.2-2B, LLaVA, Phi-4-Multimodal) before running the agent
- Behavior: `add vision` enforces a precondition — `server.files.enabled` must be `true` in `agent.yaml`. The `file_id:<id>` URL scheme resolves bytes via the `BytesStore`, which only exists when files is enabled. The command refuses to apply with an actionable hint pointing the user to `fips-agents add files` first
- Compat: Pairs with `fipsagents>=0.20.0` (content-block support landed runtime-side in agent-template #151 / fipsagents 0.20.0)
- Tests: 4 new tests in `tests/test_modality.py` covering vision spec shape, end-to-end first-run + idempotency, the files-not-enabled precondition failure, and the not-in-agent-project error path

### Version 0.10.0

- Feature: New `tools/modality.py` helper exposing `ModalitySpec` + `apply_modality()` — declarative API for composable `add` subcommands that toggle agent.yaml / chart/values.yaml fields, drop in source files, and register pyproject.toml extras. Uses ruamel.yaml round-trip to preserve comments and `${VAR:-default}` substitutions; tomlkit for TOML edits. Idempotent, with a `precondition` hook for cross-modality dependency checks (#37)
- Feature: New `fips-agents add files` command enables file upload + attachment support in existing agent projects. Flips `server.files.enabled` (agent.yaml) and `files.enabled` (chart/values.yaml); the agent template already ships the rest of the surface — storage backends, optional S3 bytes backend, ClamAV virus-scanner sidecar, Docling text extraction, pgvector chunking — so the command only owns the toggles (#19, #38)
- Improvement: `add code-executor` refactored onto the new `ModalitySpec` helper. Brittle string-replace on `enabled: false` is replaced with structured ruamel.yaml round-trip; behavior preserved
- Improvement: `_find_agent_project_root()` promoted from `commands/add.py` to `tools/project.py` as public `find_agent_project_root()`. Now recognizes both `.template-info` (`template.type=="agent"`) and legacy `agent.yaml` presence
- Chore: Pin dev tools to `black>=26,<27` and `ruff>=0.11,<0.12` so local environments cannot silently drift past CI's formatter/linter major versions (#36)
- Chore: New runtime dependency `ruamel.yaml>=0.18,<0.19` (used by the modality helper for comment-preserving YAML edits)
- Chore: Descope governance issues #23 (cost tracking), #24 (HITL approval), #25 (compliance audit logging) — OGX (the new name for LlamaStack) handles these well; fips-agents-cli will not duplicate that surface
- Tests: 29 new tests in `tests/test_modality.py` covering yaml toggles (top-level + nested), idempotency, missing-section warnings, source-file drops, pyproject extra add/merge, preconditions, and end-to-end runs of `add code-executor` and `add files`. New committed `tests/fixtures/agent_project/` provides an offline structural snapshot of the agent-template layout (precedent: `tests/fixtures/middleware_template/`)

### Version 0.9.1

- Chore: Realign `tests/` formatting with black 26.3.1 to match CI (v0.9.0's release pipeline failed because local black 24.x produced different output than CI's 26.x; no functional change)

### Version 0.9.0

- Feature: `fips-agents patch` now supports agent and workflow projects in addition to MCP servers (#12)
- Feature: New `patch chart` and `patch claude` subcommands for agent/workflow projects (#15)
- Feature: `.template-info` now records `template.type` and (for monorepo templates) `template.subdir` so post-scaffolding commands can route by project type (#13)
- Feature: New `find_fips_project_root()` walks up to `.template-info`, replacing the MCP-only fastmcp-dependency probe in patch commands (#14)
- Improvement: `_clone_template_for_patch()` resolves the monorepo subdir during patching, so glob/compare runs against `templates/agent-loop/` instead of the monorepo root (#16)
- Improvement: Running an MCP-only subcommand inside an agent project (or vice versa) now exits with a clear "available categories" error
- Improvement: `patch all` enumerates the project's actual category set instead of assuming MCP layout
- Backwards compat: Projects scaffolded before `template.type` existed default to `mcp-server`; no migration required
- Tests: 20 new tests in `tests/test_patch.py` covering the type-aware patch flow end-to-end against a fake-scaffolded agent project

### Version 0.8.2

- Test: New `TestGenerateMiddlewareRealTemplate` integration test renders the real v3.x middleware Jinja2 template against each `--hook-type` and the no-flag case, with templates committed under `tests/fixtures/middleware_template/` so the suite runs offline (#3)
- Chore: `scripts/release.sh` now constructs the release commit message from the version argument using the project convention (`chore: Release fips-agents-cli vX.Y.Z` with optional ` — <summary>`); convention documented in CLAUDE.md (#4)
- Docs: Drop broken `See Also` links from `.fips-agents-cli/README.md` in scaffolded MCP projects (#5, fixed in `fips-agents/mcp-server-template`)
- Docs: Updated CLAUDE.md release section to reflect the new release-script signature

### Version 0.8.1

- Docs: Updated CLAUDE.md current-status line and added release-process notes
- Chore: Repository hardening — added CODEOWNERS and enabled main branch protection
- Chore: Black formatting drift cleanup; removed remaining "framework" language from docs in favor of "toolkit"
- Chore: `.venv/` and `NEXT_SESSION.md` gitignored

### Version 0.8.0

- Feature: New `--vendored` flag on `create agent` copies fipsagents source instead of PyPI dependency
- Feature: New `fips-agents vendor` command for post-scaffold vendoring of existing projects
- Feature: `fips-agents vendor --update` refreshes vendored source from upstream
- Feature: `fips-agents vendor --version` pins to a specific fipsagents release tag
- Fix: `customize_agent_project` now removes monorepo Makefile install line (matching workflow template behavior)
- Fix: Added `redeploy.sh` to agent project customization file list

### Version 0.7.0

- Feature: New `add` command group for composable agent capabilities
- Feature: `fips-agents add code-executor` wires sandbox code execution into existing agent projects (tool + Helm chart sidecar config)
- Improvement: Updated `generate` group description to reflect broader scope beyond MCP

### Version 0.6.2

- Fix: Go project scaffolding now updates import paths in all `.go` source files
- Fix: Go project scaffolding now updates Helm template references (`chart/templates/*.yaml`)

### Version 0.6.1

- Chore: Updated all project URLs from `rdwj/` to `fips-agents/` org
- Chore: Post-transfer PyPI publishing verification release

### Version 0.6.0

- Feature: Added `create sandbox` command for scaffolding code execution sandbox projects from fips-agents/code-sandbox template
- Feature: All template URLs consolidated under `github.com/fips-agents/` organization

### Version 0.5.1

- Fix: SSE streaming tool call ID tracking by `call_id` not array index

### Version 0.5.0

- Feature: Added `create gateway` command for scaffolding Go HTTP gateway projects from the gateway-template
- Feature: Added `create ui` command for scaffolding chat UI projects from the ui-template
- Feature: Go project customization pipeline (`customize_go_project`) handles go.mod, Helm charts, Containerfile, Makefile, and static HTML
- Fix: Agent scaffolding now replaces `agent-template` in all Helm chart templates, preventing resource name collisions
- Fix: Agent scaffolding now replaces `OWNER/REPO` placeholder in Containerfile with actual GitHub repo

### Version 0.4.0

- Feature: Added `create agent` command for scaffolding AI agent projects from the agent-loop template
- Feature: New `clone_template_subdir()` utility for extracting templates from monorepos
- Feature: Agent project customization across pyproject.toml, Helm chart, Makefile, Containerfile, and AGENTS.md
- Improvement: Reorganized documentation into docs/, planning/, and research/ directories

### Version 0.3.0

- Feature: Added `--hook-type` option to middleware generator with `before_tool`, `after_tool`, and `on_error` choices for v3.x template scaffolding
- Fix: Fixed brittle test mocking for GitHub CLI detection in create command tests

### Version 0.2.1

- Fix: Update CLI for FastMCP 3.x template compatibility (auth.py replaces loaders.py, updated prompt return types)
- Fix: Reorder `create mcp-server` precondition checks to run before interactive GitHub prompt, so errors like missing git or existing directories fail fast without prompting first

### Version 0.2.0

- Feature: GitHub integration for `create mcp-server` command
- Feature: New `--github` flag to create GitHub repository and push code
- Feature: New `--local` flag to skip GitHub and create local-only project
- Feature: Non-interactive mode (`--yes`) for agent/CI workflows
- Feature: New `--private` flag to create private GitHub repositories
- Feature: New `--org` option to create repositories in GitHub organizations
- Feature: New `--description` option for GitHub repository descriptions
- Feature: New `--remote-only` flag to create GitHub repo without local clone
- Feature: Added missing `patch build` subcommand for updating build/deployment files
- Feature: GitHub metadata tracking in `.template-info` file
- Feature: New git utilities for remote management (`add_remote`, `push_to_remote`)
- Improvement: Auto-detects `gh` CLI and prompts user when available
- Improvement: Clean git history - customizes project before initial push

### Version 0.1.9

- Feature: Added `.fips-agents-cli` directory to ModelCar projects with generation metadata
- Feature: ModelCar projects now include `info.json` with source, destination, and generator info
- Feature: ModelCar projects now include `CLAUDE.md` with project-specific Claude Code instructions
- Improvement: Consistent project metadata structure between MCP server and ModelCar projects

### Version 0.1.8

- Feature: Added GitHub Copilot agent template support
- Feature: Added `model-car` command for creating model car projects
- Fix: Subdirectory names now convert hyphens to underscores for valid Python package names
- Fix: Added `module_path` template variable for proper import paths in subdirectory components
- Fix: Script generator improvements
- Improvement: Removed download filter for cleaner template handling
- Improvement: Added info file tracking for generated projects

### Version 0.1.7

- **Critical Fix**: Resource generator now automatically extracts URI template parameters (e.g., `{country_code}`, `{id}`) and adds them to function signature
- **Critical Fix**: Generated resources now comply with FastMCP requirement that URI parameters must match function arguments
- Fix: Updated test templates to use `.fn` attribute pattern for testing FastMCP decorated functions
- Fix: Improved `component_exists()` to properly handle subdirectory paths
- Fix: Removed obsolete `_preview_prompt_utility.py` from template (YAML-based prompts removed)
- Improvement: Generated resource tests now pass out of the box
- Improvement: Resource function signatures now include proper type hints and docstring Args sections

### Version 0.1.6

- Feature: Added `fips-agents patch` command for selective template updates without losing custom code
- Feature: Resource subdirectory support - organize resources in hierarchies (e.g., `country-profiles/japan`)
- Feature: `generate resource` now supports subdirectory paths for better organization
- Improvement: Recursive resource loading from subdirectories with automatic discovery
- Improvement: Patch command shows interactive diffs for files that may be customized
- Improvement: Template version tracking enables smart updates via `.template-info` file
- Enhancement: Cleaned up redundant auto-discovery code from template `__init__.py` files

### Version 0.1.5

- Feature: Added `.template-info` file to track CLI version and template commit hash in generated projects
- Improvement: Implemented auto-discovery for tools/resources/prompts/middleware components, eliminating manual registration in `__init__.py` files
- Improvement: Template components can now be added or removed by simply creating/deleting files—no registry updates required

### Version 0.1.4

- Fix: Fixed Containerfile in template to remove incorrect prompts/ copy line
- Fix: Fixed CLI to correctly update entry point script names for new projects
- Fix: Updated CLI to handle new multi-module template structure (core/, tools/, etc.)
- Fix: Updated fallback project name to match current template (fastmcp-unified-template)
- Improvement: Improved messaging when template uses multi-module structure

### Version 0.1.3

- Improvement: Enhanced prompt creation to comply with FastMCP 2.9+ requirements

### Version 0.1.2

- Documentation: Updated documentation and improved release management guidance
- Automation: Added `/create-release` slash command for automated release workflow
- Automation: Created `scripts/release.sh` for streamlined version management and tagging
- Documentation: Added `RELEASE_CHECKLIST.md` with comprehensive release procedures

### Version 0.1.1

- Added `fips-agents generate` command group
- Component generation: tools, resources, prompts, middleware
- Jinja2-based template rendering
- Parameter validation and JSON schema support
- Auto-run pytest on generated components
- Dry-run mode for previewing changes
- Comprehensive error handling and validation

### Version 0.1.0 (MVP)

- Initial release
- `fips-agents create mcp-server` command
- Template cloning and customization
- Git repository initialization
- Comprehensive test suite
- Beautiful CLI output with Rich
