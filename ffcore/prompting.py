"""Shared interactive helpers — the only input() calls inside ffcore."""


def ask_index(prompt, options):
    """Show a 0-based menu and return the chosen index, or None for empty input.

    Mirrors the legacy hand-rolled menus (config codec menu, converter tune
    menu): blank input returns None (the caller applies the default),
    out-of-range or non-numeric input re-prompts with "Неверный ввод".
    """
    while True:
        print()
        for i, option in enumerate(options):
            print(f"{i}: {option}")
        choice = input(prompt)
        if not choice:
            return None
        try:
            idx = int(choice)
        except ValueError:
            print("\nНеверный ввод")
            continue
        if idx >= len(options):
            print("\nНеверный ввод")
            continue
        return idx
