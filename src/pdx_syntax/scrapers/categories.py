"""Categorization functions for EU5 script items."""


def categorize_item(name: str) -> str:
    """Categorize an effect or trigger by its name pattern."""
    if name.startswith("any_"):
        return "iterator_trigger"
    elif name.startswith("every_"):
        return "iterator_effect"
    elif name.startswith("random_"):
        return "iterator_random"
    elif name.startswith("ordered_"):
        return "iterator_ordered"
    elif name.startswith("add_"):
        return "add"
    elif name.startswith("remove_"):
        return "remove"
    elif name.startswith("set_"):
        return "set"
    elif name.startswith("change_"):
        return "change"
    elif name.startswith("create_"):
        return "create"
    elif name.startswith("destroy_"):
        return "destroy"
    elif name.startswith("has_"):
        return "check"
    elif name.startswith("is_"):
        return "check"
    elif name.startswith("can_"):
        return "check"
    elif name in ("and", "or", "not", "nand", "nor", "if", "else", "else_if", "while", "switch"):
        return "flow"
    else:
        return "other"


def categorize_modifier(name: str) -> str:
    """Categorize a modifier by its name pattern."""
    if "army" in name or "military" in name or "discipline" in name or "morale" in name:
        return "military"
    elif "navy" in name or "naval" in name or "ship" in name or "sailor" in name:
        return "naval"
    elif "tax" in name or "trade" in name or "production" in name or "income" in name:
        return "economy"
    elif "diplomatic" in name or "relation" in name or "opinion" in name:
        return "diplomacy"
    elif "stability" in name or "legitimacy" in name or "government" in name:
        return "government"
    elif "technology" in name or "idea" in name or "research" in name:
        return "technology"
    elif "population" in name or "pop_" in name or "growth" in name:
        return "population"
    elif "local_" in name:
        return "province"
    elif "global_" in name:
        return "global"
    elif "allow" in name or "can_" in name or "block" in name:
        return "permission"
    elif "estate" in name:
        return "estate"
    else:
        return "other"


def categorize_on_action(name: str) -> str:
    """Categorize an on_action by its name pattern."""
    if "pulse" in name:
        return "pulse"
    elif "war" in name or "battle" in name or "siege" in name:
        return "war"
    elif "character" in name or "ruler" in name or "heir" in name or "death" in name:
        return "character"
    elif "province" in name or "capital" in name or "location" in name:
        return "province"
    elif "diplomacy" in name or "alliance" in name or "annex" in name:
        return "diplomacy"
    elif "election" in name or "government" in name:
        return "government"
    else:
        return "other"
