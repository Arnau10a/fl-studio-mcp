"""Validate and package the fl-studio-producer Agent Skill for marketplace upload."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT_DIR / "skills" / "fl-studio-producer"
DIST_DIR = ROOT_DIR / "dist"

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract top-level YAML frontmatter fields and markdown body from SKILL.md."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter delimiter '---'")

    end_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ValueError("SKILL.md is missing closing YAML frontmatter delimiter '---'")

    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :]).strip()
    fields: dict[str, str] = {}

    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip() or line.startswith(" "):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, raw_val = line.split(":", 1)
        key = key.strip()
        val = raw_val.strip()

        if val in (">-", ">", "|", "|-"):
            folded: list[str] = []
            i += 1
            while i < len(fm_lines) and (fm_lines[i].startswith("  ") or not fm_lines[i].strip()):
                if fm_lines[i].strip():
                    folded.append(fm_lines[i].strip())
                i += 1
            fields[key] = " ".join(folded)
            continue

        fields[key] = val.strip('"').strip("'")
        i += 1

    return fields, body


def validate_skill(skill_dir: Path = SKILL_DIR) -> dict[str, str]:
    """Validate Agent Skills spec rules and return parsed frontmatter fields."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"Missing SKILL.md in {skill_dir}")

    text = skill_md.read_text(encoding="utf-8")
    fields, body = parse_frontmatter(text)

    name = fields.get("name", "")
    if not name or len(name) > 64 or not NAME_RE.match(name):
        raise ValueError(
            f"Invalid skill name {name!r}: must be 1-64 lowercase alphanumeric/hyphen chars"
        )
    if name != skill_dir.name:
        raise ValueError(f"Skill name {name!r} must match directory name {skill_dir.name!r}")

    description = fields.get("description", "")
    if not description or len(description) > 1024:
        raise ValueError("Skill description is required and must be <= 1024 characters")

    compatibility = fields.get("compatibility", "")
    if len(compatibility) > 500:
        raise ValueError("Skill compatibility must be <= 500 characters")

    if not body:
        raise ValueError("SKILL.md markdown body cannot be empty")

    # Verify all relative markdown links inside SKILL.md and references/ resolve.
    md_files = [skill_md, *sorted((skill_dir / "references").glob("*.md"))]
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        for target in MD_LINK_RE.findall(content):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target_path = (md_file.parent / target.split("#", 1)[0]).resolve()
            if not target_path.exists():
                raise FileNotFoundError(
                    f"Broken relative link {target!r} in {md_file.relative_to(skill_dir)}"
                )

    return fields


def package_skill(skill_dir: Path = SKILL_DIR, out_dir: Path = DIST_DIR) -> Path:
    """Validate and bundle the skill directory into a clean zip archive."""
    fields = validate_skill(skill_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{fields['name']}.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts or path.name.startswith("."):
                continue
            arcname = path.relative_to(skill_dir)
            zf.write(path, arcname.as_posix())

    return zip_path


def main() -> None:
    zip_path = package_skill()
    print(f"Packaged skill successfully: {zip_path}")


if __name__ == "__main__":
    main()
