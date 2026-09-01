HUMAN_INTERVENTION = True


def human_intervention_enabled() -> bool:
    return HUMAN_INTERVENTION


def request_approval(prompt: str) -> bool:
    if not HUMAN_INTERVENTION:
        print("Human intervention is disabled; proceeding automatically.")
        return True
    return input(prompt).strip().lower() == "yes"


def agent_intervention_instruction() -> str:
    if HUMAN_INTERVENTION:
        return (
            "Human intervention is enabled. Ask the human only when approval is "
            "required or you are genuinely blocked."
        )
    return (
        "Human intervention is disabled for this run. Do not ask for human input or approval. "
        "Proceed using the authorized files and rules; if required information is unavailable, "
        "return a clear failure instead of requesting input."
    )
