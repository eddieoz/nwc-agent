# Repo Documentation Redesign — Design Document

**Date:** 2026-05-08
**Status:** Validated
**Reference:** Inspired by obra/superpowers repository documentation structure

## Motivation

The nwc-agent README is comprehensive but dense — crypto stack tables, supply
chain timelines, architecture comparisons all in one file. This is valuable
content but makes the README hard to scan. The repo also lacks an AGENTS.md
for AI agent interpretation and has no docs/ directory for deep technical
content.

obra/superpowers demonstrates a clean pattern: a ~230-line README with clear
sections, AGENTS.md/CLAUDE.md for agent rules, and docs/ for detailed specs.

## Design

### New File Structure

```
eddieoz/nwc-agent/
├── README.md              ← ~200 lines, scannable
├── AGENTS.md              ← Agent operating manual (new)
├── SKILL.md               ← Existing
├── docs/                  ← New directory
│   ├── architecture.md    ← Crypto stack, supply chain, arch tables
│   ├── l402-protocol.md   ← L402/X402/MPP details
│   ├── testing.md         ← Test approach
│   └── plans/             ← Design documents (this file)
├── scripts/               ← Existing (8 Python files)
├── .github/
│   └── PULL_REQUEST_TEMPLATE.md  ← New
├── requirements.txt
├── .env.example
└── LICENSE
```

### README.md Sections (Top → Bottom)

1. **Title + tagline** — One-line identity
2. **Quickstart** — 30 seconds to first balance check
3. **How it Works** — Narrative (3-4 paragraphs), no tables
4. **Sponsorship** — GitHub Sponsors link
5. **Installation** — Prerequisites, from source, future PyPI
6. **Basic Workflow** — Table of 4 core operations
7. **The Library** — Table of all 8 scripts with one-liners
8. **Philosophy** — 4 bullet principles
9. **Contributing** — Brief, points to AGENTS.md and docs/
10. **License** — MIT, one line
11. **Community** — GitHub Issues + optional links

Deep technical content moved to docs/architecture.md.

### AGENTS.md Sections

1. **If You're an AI Agent Using This Library** — Rules for tool invocation
2. **Codebase Map** — File tour
3. **Build & Test** — Commands
4. **If You're Contributing** — Brief rules
5. **Architecture Rules (Non-Negotiable)** — Dependency and portability constraints

### docs/ Files

- **architecture.md** — Crypto stack, supply chain timeline, attack surface tables, platform support matrix
- **l402-protocol.md** — L402/X402 flows, MPP, credential reuse, examples
- **testing.md** — Test runner, env vars, mock mode, RISC-V hardware testing

### .github/PULL_REQUEST_TEMPLATE.md

Standard template with environment table, test results, and problem description.

## Implementation Plan

1. Create branch: `docs/redesign-superpowers-style`
2. Write AGENTS.md
3. Create docs/architecture.md from current README deep content
4. Create docs/l402-protocol.md
5. Create docs/testing.md
6. Create .github/PULL_REQUEST_TEMPLATE.md
7. Rewrite README.md (concise, sections as above)
8. Verify all links between files work
9. Review rendered README on GitHub
10. Merge to master
