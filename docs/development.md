# Development and release tooling

Run maintainer commands below from the repository root. Commit identity and
GPG signing are configured per clone in Git.

VCO1's KiCad sources are in `hardware/rev1/`. Required datasheets, evidence, and
3D models are included under `assets/`. Clone this repository normally and run
`git lfs pull` before opening `hardware/rev1/vco1_rev1.kicad_pro` in KiCad 10.
The native design works without access to the private infrastructure submodule.

Maintainers with infra access can run:

```sh
git submodule update --init infra
infra/setup.sh --apply
uv run --project infra/tools kicad10_tree release validate --project vco1_rev1 --format json
```

Setup creates ignored local skill/tool/workflow-library symlinks and an ignored
working catalog at `.hw-infra/components.sqlite3`. It preserves existing working
state. Mechanical and software sources, when added, belong in `mechanical/` and
`software/`; simulation sources belong in `sim/revN/`.

The release workflow takes a numeric hardware revision, checks out the exact
pinned infra commit with its read-only deploy key, pulls the infra-owned release image pinned to that commit,
and runs every release gate before publishing manufacturing artifacts. It never
orders manufacturing. The AI tools and release automation require infra access.

The private `hw-infra-tools` container package must grant this repository read
access under Manage Actions access. The workflow uses its own GITHUB_TOKEN for
registry access and the dedicated read-only deploy key only for the infra clone.
