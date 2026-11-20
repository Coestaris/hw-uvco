# Repository agent guidance

## Debug state

- The repository is currently in debug state: skills and all tools are under test.
- Agents may fix or extend skills, tools, tests, and supporting infrastructure as needed without
  requesting approval, while preserving evidence requirements, validation gates, and safety rules.

## Project-agnostic tooling

- Skills and tools must remain project agnostic. Do not add project names, references, part numbers,
  or footprint identifiers as special cases in skill instructions or tool logic. Derive behavior from
  structured project data, explicit review records, and general validation rules instead.

## Skill and implementation mismatch

- If a skill differs from the actual tool implementation, or lacks clear instructions for a requested
  operation, stop that operation and ask the user for skill modification instructions. State the
  specific mismatch or missing steps and the implementation behavior observed. Do not guess a
  command or continue the affected operation until the user responds.
- If the user has already given instructions to update that skill for the mismatch, follow those
  instructions and continue the authorized work.

## Shell scripts

- Always use ShellCheck when reading, reviewing, creating, or modifying shell scripts.
- Run `shellcheck` on every relevant shell script after changes, fix actionable findings, and
  report any intentionally suppressed or unresolved diagnostics.

## Native KiCad files

- Never read or edit native KiCad files by hand or with text, regex, line-oriented, or ad-hoc
  parsing tools. This includes `.kicad_sch`, `.kicad_pcb`, `.kicad_sym`, `.kicad_mod`,
  `.kicad_dru`, `.kicad_jobset`, `.kicad_pro`, and library tables.
- Use `kicad10_tree ... --format json` for semantic reads and its dry-run-first structured
  mutation commands for writes. `kicad-cli` is the native validator/exporter, not the parser.
