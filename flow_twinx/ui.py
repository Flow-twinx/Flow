from .imports import config


def questionary_style():
    import questionary
    from questionary import Style

    def name(ansi_code):
        return config._cname(ansi_code)

    return Style(
        [
            ("qmark", f"fg:{name(config.Primary)} bold"),
            ("question", f"fg:{name(config.Primary)} bold"),
            ("answer", f"fg:{name(config.Primary)} bold"),
            ("pointer", f"fg:{name(config.Primary)} bold"),
            ("highlighted", f"fg:{name(config.Primary)} bold"),
            ("selected", f"fg:{name(config.Primary)}"),
            ("instruction", f"fg:{name(config.Tertiary)}"),
            ("text", ""),
        ]
    )


def pick(question, choices, default=0, instruction="(↑↓ navigate, Enter to select, Esc to cancel)"):
    try:
        import questionary
    except ImportError:
        return None, False

    if not _is_tty():
        return None, False

    q_choices = [
        c
        if isinstance(c, questionary.Choice)
        else questionary.Choice(title=c[0], value=c[1])
        for c in choices
    ]

    if isinstance(default, int) and not isinstance(default, bool) and 0 <= default < len(q_choices):
        default_value = q_choices[default].value
    else:
        default_value = default

    try:
        choice = questionary.select(
            question,
            choices=q_choices,
            default=default_value,
            instruction=instruction,
            style=questionary_style(),
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None, True
    return choice, True


def _is_tty():
    try:
        import sys

        return sys.stdin.isatty()
    except Exception:
        return False
