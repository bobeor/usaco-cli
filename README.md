# Installation

## Prerequisites

- Python 3.13 or newer
- `uv` (recommended)

Install `uv` if you don't already have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal after installation if necessary.

## Install from Source

Clone the repository:

```bash
git clone <repository-url>
cd usaco-cli
```

Install the CLI:

```bash
uv tool install . --force
```

Verify the installation:

```bash
usaco-cli --help
```

## Updating

If you've pulled new changes:

```bash
git pull
uv tool install . --force
```

## Uninstall

```bash
uv tool uninstall usaco-cli
```


# Usage

## First-time setup

On first run, the tool creates a config file at `~/.config/usaco-cli/config.json` and prompts you for your usaco.org credentials:

```bash
usaco-cli --login
```

It asks for your username, password, and a default language (selected from an interactive menu), then writes them to the config file. The config stores `username`, `password`, and the default `language`.

## Submitting a solution

```bash
usaco-cli -f <file> -i <cpid> [-l <language>]
```

- `-f`, `--file` — path to the solution file to submit
- `-i`, `--cpid` — the problem ID (`cpid`) of the problem
- `-l`, `--language` — optional language override; defaults to the language set during setup

The tool fetches the problem title from usaco.org, submits your solution, then polls for results until judging completes.

## Supported languages

`c`, `cpp-11`, `cpp-17`, `java`, `python2`, `python3`

## Resetting credentials

Pass `--login` to re-run the setup prompt and overwrite saved credentials:

```bash
usaco-cli --login
```