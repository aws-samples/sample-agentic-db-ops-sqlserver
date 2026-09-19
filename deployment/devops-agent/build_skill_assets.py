#!/usr/bin/env python3
"""Regenerate the DevOps Agent skill/agents_md Asset resources in
dbops-devops-agent.yaml from the source files under skills/ and AGENTS.md.

The skill content (methodology) has a single source of truth: the Markdown
files below. This script injects that content into the CloudFormation template
between the BEGIN/END GENERATED ASSETS markers, so you never hand-edit the
inlined copy. deploy.sh runs this automatically before packaging.

Edit the skill here, not in the template:
  - skills/sql-server-investigation/SKILL.md
  - skills/sql-server-investigation/references/tool-reference.md
  - AGENTS.md
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "dbops-devops-agent.yaml")
SKILL_MD = os.path.join(HERE, "skills/sql-server-investigation/SKILL.md")
TOOL_REF = os.path.join(HERE, "skills/sql-server-investigation/references/tool-reference.md")
AGENTS_MD = os.path.join(HERE, "AGENTS.md")

BEGIN = "  # BEGIN GENERATED ASSETS. Do not edit by hand."
BEGIN_FULL = (
    BEGIN + " Source: skills/ and AGENTS.md.\n"
    "  # Regenerate with build_skill_assets.py (run automatically by deploy.sh).\n"
)
END = "  # END GENERATED ASSETS\n"

# Asset Metadata is CloudFormation config (not the methodology), so it lives here.
SKILL_NAME = "sql-server-investigation"
SKILL_DESCRIPTION = (
    "Incident investigation procedures for Amazon RDS for SQL Server performance "
    "issues: blocking and lock contention, plan regression, slow or high-impact "
    "queries, and missing indexes."
)
SKILL_AGENT_TYPES = ["GENERIC"]
AGENTS_MD_AGENT_TYPE = "INCIDENT_RCA"


def block_scalar(text, indent):
    """Render text as a YAML literal block scalar body at the given indent."""
    pad = " " * indent
    out = []
    for line in text.split("\n"):
        out.append(pad + line if line.strip() else "")
    return "\n".join(out).rstrip("\n") + "\n"


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_assets():
    skill = read(SKILL_MD)
    toolref = read(TOOL_REF)
    agents = read(AGENTS_MD)

    at = "".join(f"        - {t}\n" for t in SKILL_AGENT_TYPES)
    parts = []
    parts.append("  SkillAsset:\n")
    parts.append("    Type: AWS::DevOpsAgent::Asset\n")
    parts.append("    Properties:\n")
    parts.append("      AgentSpaceId: !GetAtt AgentSpace.AgentSpaceId\n")
    parts.append("      AssetType: skill\n")
    parts.append("      Metadata:\n")
    parts.append(f"        name: {SKILL_NAME}\n")
    parts.append(f'        description: "{SKILL_DESCRIPTION}"\n')
    parts.append("        agent_types:\n")
    parts.append(at)
    parts.append("      Files:\n")
    parts.append("      - Path: SKILL.md\n")
    parts.append("        ContentText: |\n")
    parts.append(block_scalar(skill, 10))
    parts.append("      - Path: references/tool-reference.md\n")
    parts.append("        ContentText: |\n")
    parts.append(block_scalar(toolref, 10))
    parts.append("  AgentsMdAsset:\n")
    parts.append("    Type: AWS::DevOpsAgent::Asset\n")
    parts.append("    Properties:\n")
    parts.append("      AgentSpaceId: !GetAtt AgentSpace.AgentSpaceId\n")
    parts.append("      AssetType: agents_md\n")
    parts.append("      Metadata:\n")
    parts.append(f"        agent_type: {AGENTS_MD_AGENT_TYPE}\n")
    parts.append("      Files:\n")
    parts.append("      - Path: AGENTS.md\n")
    parts.append("        ContentText: |\n")
    parts.append(block_scalar(agents, 10))
    return "".join(parts)


def main():
    tpl = read(TEMPLATE)
    generated = BEGIN_FULL + build_assets() + END

    if BEGIN in tpl:
        pre = tpl[: tpl.index(BEGIN)]
        rest = tpl[tpl.index(END) + len(END):]
        new = pre + generated + rest
    else:
        # First run: replace the existing SkillAsset..AgentsMdAsset block,
        # which sits between "  SkillAsset:" and the top-level "Outputs:".
        i = tpl.index("  SkillAsset:")
        j = tpl.index("\nOutputs:")
        new = tpl[:i] + generated + tpl[j + 1:]

    if new != tpl:
        with open(TEMPLATE, "w", encoding="utf-8") as f:
            f.write(new)
        print("build_skill_assets: regenerated SkillAsset/AgentsMdAsset from source files")
    else:
        print("build_skill_assets: template already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
