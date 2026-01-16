"""Smart Reply Template Engine - Pillow-based image compositing for replies.

This module handles loading, rendering, and hot-reloading of Smart Reply templates.
Templates consist of a PNG base image + JSON metadata describing text fields.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from PIL import Image, ImageColor, ImageDraw, ImageFont


@dataclass
class TemplateField:
    """Definition of a text field in a template."""

    id: str
    label: str
    x: int
    y: int
    font_size: int
    color: str
    font_family: str = "Arial"
    alignment: str = "left"
    format: Optional[str] = None


@dataclass
class TemplateMetadata:
    """Metadata for a Smart Reply template."""

    name: str
    base_image: str
    default_mode: str
    fields: List[TemplateField]
    template_id: str = ""

    def __post_init__(self):
        """Convert dict fields to TemplateField objects."""
        if self.fields and isinstance(self.fields[0], dict):
            self.fields = [TemplateField(**f) for f in self.fields]


class TemplateEngine:
    """Manages Smart Reply templates and rendering."""

    def __init__(self, bundled_dir: Optional[Path] = None, user_dir: Optional[Path] = None):
        """Initialize the template engine.

        Args:
            bundled_dir: Path to bundled templates (defaults to sstv_core/templates/smart_reply/)
            user_dir: Path to user templates (defaults to ~/.ssteve/templates/)
        """
        if bundled_dir is None:
            # Default to package templates directory
            pkg_root = Path(__file__).parent.parent.parent.parent
            bundled_dir = pkg_root / "templates" / "smart_reply"

        if user_dir is None:
            user_dir = Path.home() / ".ssteve" / "templates"

        self.bundled_dir = Path(bundled_dir)
        self.user_dir = Path(user_dir)

        # Create user directory if it doesn't exist
        self.user_dir.mkdir(parents=True, exist_ok=True)

        self.templates: Dict[str, TemplateMetadata] = {}
        self._load_templates()

    def _load_templates(self):
        """Load all templates from bundled and user directories."""
        self.templates.clear()

        # Load bundled templates
        if self.bundled_dir.exists():
            self._load_templates_from_dir(self.bundled_dir)

        # Load user templates (overrides bundled if same ID)
        if self.user_dir.exists():
            self._load_templates_from_dir(self.user_dir)

    def _load_templates_from_dir(self, directory: Path):
        """Load all templates from a directory.

        Args:
            directory: Path to directory containing template JSON files
        """
        for json_file in directory.glob("*.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)

                template = TemplateMetadata(**data)

                # Generate template ID from filename if not specified
                if not template.template_id:
                    template.template_id = json_file.stem

                # Resolve base_image path relative to JSON file
                if not os.path.isabs(template.base_image):
                    template.base_image = str(directory / template.base_image)

                # Verify base image exists
                if not os.path.exists(template.base_image):
                    print(f"Warning: Base image not found for template {template.name}: {template.base_image}")
                    continue

                self.templates[template.template_id] = template

            except Exception as e:
                print(f"Error loading template {json_file}: {e}")

    def reload_templates(self):
        """Hot-reload all templates (useful for runtime updates)."""
        self._load_templates()

    def get_template(self, template_id: str) -> Optional[TemplateMetadata]:
        """Get template by ID.

        Args:
            template_id: Template identifier

        Returns:
            TemplateMetadata or None if not found
        """
        return self.templates.get(template_id)

    def list_templates(self) -> List[TemplateMetadata]:
        """Get list of all available templates.

        Returns:
            List of TemplateMetadata objects
        """
        return list(self.templates.values())

    def render_template(
        self,
        template_id: str,
        field_values: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> str:
        """Render a template with populated field values.

        Args:
            template_id: Template to render
            field_values: Dictionary of field_id -> value
            output_path: Optional output path (defaults to temp file)

        Returns:
            Path to rendered image

        Raises:
            ValueError: If template not found or base image missing
        """
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Load base image
        try:
            base = Image.open(template.base_image).convert("RGBA")
        except Exception as e:
            raise ValueError(f"Failed to load base image: {e}")

        # Create drawing context
        draw = ImageDraw.Draw(base)

        # Render each field
        for field in template.fields:
            value = field_values.get(field.id)
            if value is None:
                continue

            # Apply format string if specified
            if field.format:
                try:
                    text = field.format.format(value=value)
                except Exception as e:
                    print(f"Warning: Format error for field {field.id}: {e}")
                    text = str(value)
            else:
                text = str(value)

            # Load font
            try:
                # Try to load TrueType font
                font = ImageFont.truetype(field.font_family, field.font_size)
            except Exception:
                # Fallback to default font
                try:
                    font = ImageFont.truetype("Arial.ttf", field.font_size)
                except Exception:
                    # Last resort: use default PIL font
                    font = ImageFont.load_default()

            # Parse color
            try:
                color = ImageColor.getrgb(field.color)
            except Exception:
                color = (255, 255, 255)  # Default to white

            # Determine anchor based on alignment
            anchor_map = {
                "left": "la",
                "center": "ma",
                "right": "ra"
            }
            anchor = anchor_map.get(field.alignment, "la")

            # Draw text
            draw.text(
                (field.x, field.y),
                text,
                font=font,
                fill=color,
                anchor=anchor
            )

        # Generate output path if not provided
        if output_path is None:
            temp_dir = Path("/tmp/ssteve_previews")
            temp_dir.mkdir(exist_ok=True)
            output_path = str(temp_dir / f"smart_reply_{uuid4()}.png")

        # Convert to RGB before saving (remove alpha channel)
        final = Image.new("RGB", base.size, (0, 0, 0))
        final.paste(base, mask=base.split()[3] if base.mode == "RGBA" else None)

        # Save rendered image
        final.save(output_path, "PNG")

        return output_path


def render_smart_reply_template(
    template_id: str,
    field_values: Dict[str, Any],
    template_engine: Optional[TemplateEngine] = None
) -> str:
    """Convenience function to render a Smart Reply template.

    Args:
        template_id: Template to render
        field_values: Dictionary of field_id -> value
        template_engine: Optional TemplateEngine instance (creates new if None)

    Returns:
        Path to rendered preview image
    """
    if template_engine is None:
        template_engine = TemplateEngine()

    return template_engine.render_template(template_id, field_values)
