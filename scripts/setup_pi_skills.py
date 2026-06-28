#!/usr/bin/env python3
"""Create project .pi/skills symlink pointing to .agents/skills.

Run this after cloning to ensure pi picks up project skills (Agent Skills spec).
"""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
agents_skills = root / ".agents" / "skills"
pi_dir = root / ".pi"
pi_skills = pi_dir / "skills"

if not agents_skills.exists():
    print(f"Source skills directory not found: {agents_skills}")
    sys.exit(1)

pi_dir.mkdir(parents=True, exist_ok=True)
# Create or replace symlink
try:
    if pi_skills.exists() or pi_skills.is_symlink():
        pi_skills.unlink()
    pi_skills.symlink_to(Path("..") / ".agents" / "skills")
    print(f"Created symlink: {pi_skills} -> ../.agents/skills")
except Exception as e:
    print(f"Failed to create symlink: {e}")
    sys.exit(2)

print("Done.")
