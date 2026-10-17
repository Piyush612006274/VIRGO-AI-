"""Minimal local website and stdlib Python creation workflows."""

from html import escape

from virgo.contracts.models import (
    CreationAction,
    CreationOperation,
    GeneratedFileProposal,
    ToolRiskLevel,
)


def static_landing_page_proposals(
    *, heading: str = "Hello, I create useful things."
) -> tuple[GeneratedFileProposal, ...]:
    operations = (
        CreationOperation(
            action=CreationAction.CREATE,
            target="index.html",
            summary="Create the approved static landing page",
            risk_level=ToolRiskLevel.REVERSIBLE_WRITE,
            tool_name="create_text_file",
            reversible=True,
            requires_permission=True,
        ),
        CreationOperation(
            action=CreationAction.CREATE,
            target="script.js",
            summary="Create the approved local interaction",
            risk_level=ToolRiskLevel.REVERSIBLE_WRITE,
            tool_name="create_text_file",
            reversible=True,
            requires_permission=True,
        ),
        CreationOperation(
            action=CreationAction.CREATE,
            target="styles.css",
            summary="Create the approved landing page styles",
            risk_level=ToolRiskLevel.REVERSIBLE_WRITE,
            tool_name="create_text_file",
            reversible=True,
            requires_permission=True,
        ),
    )
    return (
        GeneratedFileProposal(
            operation=operations[0],
            proposed_content=(
                '<!doctype html>\n<html lang="en">\n<head>\n'
                '  <meta charset="utf-8">\n'
                '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
                '  <meta name="description" content="A personal portfolio of useful work.">\n'
                "  <title>Personal Portfolio</title>\n"
                '  <link rel="stylesheet" href="styles.css">\n'
                f"</head>\n<body>\n  <main>\n    <h1>{escape(heading)}</h1>\n"
                "    <p>Welcome to my personal portfolio.</p>\n"
                '    <section id="about"><h2>About</h2><p>I build thoughtful digital experiences.</p></section>\n'
                '    <section id="projects"><h2>Projects</h2><article><h3>Selected work</h3><p>Useful, accessible products.</p></article></section>\n'
                '    <section id="contact"><h2>Contact</h2><button id="contact-button">Show contact</button><p id="contact-note" hidden>hello@example.test</p></section>\n'
                '  </main>\n  <script src="script.js"></script>\n</body>\n</html>\n'
            ),
            provider_name="deterministic-local",
            model_name="template-v1",
            validated=False,
        ),
        GeneratedFileProposal(
            operation=operations[1],
            proposed_content=(
                "body { max-width: 48rem; margin: 4rem auto; padding: 0 1rem; "
                "font-family: system-ui, sans-serif; line-height: 1.6; }\n"
                "h1 { color: #315c78; }\n"
            ),
            provider_name="deterministic-local",
            model_name="template-v1",
            validated=False,
        ),
        GeneratedFileProposal(
            operation=operations[2],
            proposed_content=(
                'const button = document.querySelector("#contact-button");\n'
                'const note = document.querySelector("#contact-note");\n'
                'button?.addEventListener("click", () => { note.hidden = !note.hidden; });\n'
            ),
            provider_name="deterministic-local",
            model_name="template-v1",
            validated=False,
        ),
    )


def stdlib_python_module_proposal() -> GeneratedFileProposal:
    operation = CreationOperation(
        action=CreationAction.CREATE,
        target="hello.py",
        summary="Create a small approved standard-library Python module",
        risk_level=ToolRiskLevel.REVERSIBLE_WRITE,
        tool_name="create_text_file",
        reversible=True,
        requires_permission=True,
    )
    return GeneratedFileProposal(
        operation=operation,
        proposed_content=(
            '"""Small generated example."""\n\n\n'
            "def greeting(name: str) -> str:\n"
            '    return f"Hello, {name}!"\n'
        ),
        provider_name="deterministic-local",
        model_name="template-v1",
        validated=False,
    )
