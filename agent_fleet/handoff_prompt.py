"""AI-agent checklist text and bordered output shared by ``init`` and ``preview``."""


INIT_AI_AGENT_PROMPT = """Configure AgentFleet for this repository.

1. Create or update agentfleet.toml.
2. Keep the default fleet at 2 Codex agents and 2 Claude agents unless this repo needs something else.
3. Inspect the project and add [[preview.services]] for the local services needed to preview work.
4. For each preview service set name, dir, port_base, command using {port}, and env values if needed.
5. Mark the browser-facing service with primary = true.
6. Run `agentfleet doctor` and explain any failures.
7. If this is frontend-only, backend-only, Docker-only, mobile, or multi-service, configure the closest useful setup and explain the tradeoff."""


def print_prompt_box(body: str) -> None:
    """Surround plain multi-line text with unicode box chars (narrow layout, no ansi in ``body``)."""

    gray = "\033[38;5;245m"
    reset = "\033[0m"
    lines = body.strip().split("\n")
    w = max(len(line) for line in lines)
    rule = "─" * (w + 2)
    print(f"{gray}┌{rule}┐{reset}")
    for line in lines:
        print(f"{gray}│{reset} {line.ljust(w)} {gray}│{reset}")
    print(f"{gray}└{rule}┘{reset}")
