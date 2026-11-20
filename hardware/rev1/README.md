# VCO1 Rev1

KiCad sources are in this directory; JLCPCB production files are in `manufacturing/`.
The same directory contains a four-page schematic PDF and a seven-page PCB PDF:
front silkscreen with pad apertures, mirrored back silkscreen with pad
apertures, front copper, mirrored back copper, top 3D, bottom 3D, and a
perspective corner view. Technical PCB pages are cropped to the `Edge.Cuts`
bounds. They exclude the fabrication/manufacturing-data layers and drawing-sheet
table/frame. KiCad text remains searchable in the PDFs.

Regenerate both PDFs without the KiCad GUI:

```sh
uv run --project tools release export vco1_rev1
```

Gerber, BOM, and pick-and-place generation is available through explicit flags
and is disabled by default. See the repository-level `README.md` for the shared
generator and software requirements.

The assembly BOM was audited against the JLCPCB catalog on 2026-07-14. It has
16 Basic line items, 6 Promotional Extended line items that JLC currently
exempts from feeder-loading fees for Economic assembly, and 3 fee-bearing
Extended line items. The remaining fee-bearing parts are the 10k B3950 NTC and
the positive/negative 8V regulators; no electrically safe Basic or Promotional
replacement was available. R29 changed from 14k to the Basic 15k value, a 7.1%
change that only affects PWM control scaling. Recheck Promotional status and
stock when uploading the BOM because JLCPCB catalog classifications can change.
