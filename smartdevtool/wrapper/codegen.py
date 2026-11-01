"""Python SDK code generator using Jinja2 templates.

Validates all generated code via `ast.parse()` to guarantee syntactically valid Python.
"""

from __future__ import annotations

import ast
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from smartdevtool.wrapper.spec import EndpointSpec


class WrapperGenerator:
    """Generates a complete Python SDK client class from an EndpointSpec."""

    TEMPLATE_DIR = Path(__file__).parent / "templates"
    TEMPLATE_NAME = "wrapper_template.py.jinja"

    def __init__(self, spec: EndpointSpec, class_name: str | None = None) -> None:
        self.spec = spec
        clean_title = spec.title.replace(" ", "").replace("-", "_")
        if not clean_title or clean_title in ("ApiWrapper", "ApiClient"):
            clean_title = "ApiClient"
        self.class_name = class_name or clean_title

        self.env = Environment(
            loader=FileSystemLoader(str(self.TEMPLATE_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate_code(self) -> str:
        """Render the Jinja2 template and strictly validate output with ast.parse()."""
        template = self.env.get_template(self.TEMPLATE_NAME)
        rendered = template.render(
            spec=self.spec,
            class_name=self.class_name,
        )

        # Enforce AST parse validation
        try:
            ast.parse(rendered)
        except SyntaxError as exc:
            raise ValueError(f"Generated wrapper code failed ast.parse validation: {exc}\n{rendered}") from exc

        return rendered

    def write(self, output_path: Path | str) -> Path:
        """Generate code and save to disk."""
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        code = self.generate_code()
        with open(target, "w", encoding="utf-8") as f:
            f.write(code)
        return target
