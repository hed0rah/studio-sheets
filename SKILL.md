---
name: studio-sheets
description: Prints a home studio's routing as a PDF from one JSON file - a signal-flow map on a millimetre dot grid (devices, ports, audio and CV cables, write-in boxes on free ports), a session sheet to fill in by hand, and optional numbered rule cards, in five palettes. Use when someone wants to map their studio's routing, print a patch or session sheet, or document how their mixer, interface, synths and modular connect.
---

# studio sheets

Turns a description of a studio into a PDF you print and keep beside the desk:

1. **the map**: every device as a box on a dot grid, ports on its edges, cables between
   them. Audio is solid, CV/gate/clock dashed, parked gear tinted, and every free port can
   carry a dashed write-in box for whatever gets patched there next. The dots are true
   millimetres, so the printout doubles as graph paper for the next change.
2. **the session sheet**: header fields (date, project, tempo, tape speed...), a row per
   mixer channel with tick boxes and knob outlines to draw on, each chosen device's ports
   with the map's cables as faint hints, a changes table, clock and MIDI, and a dot-grid
   notes area. It is also written on its own as `<name>-session.pdf`, to print a stack of.
3. **the cards** (optional): short numbered rules for the room. The numbers match orange
   badges placed on the map.

Letter or A4, landscape. The one accent colour only ever repeats something a number or a
word already says, so the white-paper palettes survive a mono laser.

## Palettes

Set `"palette"` in the JSON, or preview any of them with `--palette=<name>`. `"accent"`
overrides just the accent colour.

| palette | from | paper |
|---|---|---|
| `rally` (default) | ink and rally orange | white: prints anywhere |
| `teal` | ink and a teal deep enough to read as text | white |
| `riso` | two riso inks: Riso Blue for everything, fluorescent pink for the accent | white |
| `violet` | black ink on lavender stock with a blue second colour, after riso-printed design journals | lavender, fills the page |
| `blueprint` | cyanotype: pale lines on Prussian blue, amber accent | dark blue, fills the page |

The last two fill the whole page: use them on screen, or print them on a colour printer
you are happy to spend ink on. For a stack of session sheets, use a white one.

## Build

    python build.py studio.json          # studio.pdf and studio-session.pdf beside the json
    python build.py studio.json --png    # also studio_p1.png ... for checking
    python build.py studio.json --palette=riso   # try a palette without editing the json

Needs `reportlab`; `--png` needs `pymupdf`. Fonts: IBM Plex Mono and Source Serif 4 if
their TTFs are in `fonts/` beside build.py (IBMPlexMono-Regular/Bold/Italic.ttf,
SourceSerif4-Semibold.ttf, both free under the SIL Open Font License), otherwise the PDF
core fonts (Courier, Times).

`example/studio.json` is a complete generic studio (a 4-track, an interface, a drum
machine, a synth, a mic, a turntable, a reverb loop, a small modular rack). Copy it and
edit; it exercises every feature.

## What to give your model

The sheet is only as right as the description of the room, and only you can walk the
cables. Hand your model:

1. **The gear, with model numbers**: every box that has a jack on it.
2. **The manuals, or photos of the back panels**: the port names on the sheet should be
   the names printed on the hardware.
3. **The cables, one at a time**: from which jack on what, to which jack on what. A
   photo of a busy patch is a starting point; walking it out loud is the real list.
4. **The switches you care about**, and which ones you have not checked. Those print as `??`.

It drafts the JSON and shows you the PNG; you correct it until it is the room. Keep the
JSON beside the PDF: next time something moves, you change one line and print again.

## Workflow

1. **Ask, do not guess.** Get the actual gear and the actual cables from the person: what
   plugs into what, on which jack. A switch position or a connection nobody confirmed goes
   on the sheet marked `??`, never filled in from what is typical. Manuals are the source
   for port names; use the names printed on the panel.
2. **Place the hub first.** The mixer or interface everything meets at goes in the middle
   with `"hub": true` (it gets the accent title strip; one per page). Sources on the left,
   outputs and the computer on the right, modular across the bottom.
3. **Line ports up.** A port's `pos` is its distance in dots from the top (left/right
   sides) or from the left (top/bottom). Give both ends of a cable the same grid row or
   column and the cable is a straight line; otherwise the router adds one or two elbows.
   For anything awkward, give the cable a `via` list of grid points.
4. **Build with `--png` and read the warnings.** The builder reports overlapping boxes,
   boxes off the grid, names wider than their box, port labels that run into a title,
   session tables wider than their column, and a notes area squeezed under an inch. Fix
   every warning, then look at the PNGs: labels on wires, crossings, cramped boxes.
5. **Print at 100%**, not "fit to page", or the dots stop being millimetres.

## Schema

Coordinates are grid units: one per dot (`grid_mm`, default 5), origin at the bottom-left
of the map area. US Letter landscape gives about 51 x 36 dots, A4 about 55 x 33.

    {
      "title", "subtitle", "doc", "rev", "footer_note",   header and footer text
      "paper": "letter" | "a4",  "grid_mm": 5,
      "palette": "rally",  "accent": "#FF4D00",   accent is optional, over the palette's

      "devices": [{
        "id": "desk",                       used by cables as "desk.<port id>"
        "name", "sub",                      title and subtitle
        "at": [x, y], "size": [w, h],       bottom-left corner and size, in dots
        "hub": true,                        accent title strip (one device)
        "muted": true,                      tinted: parked or unconfirmed
        "badge": 1,                         orange number, matching a card
        "notes": ["...", "..."],            small lines on the box's floor
        "ports": [{
          "id", "label",                    label drawn inside the box; "" for none
          "short",                          label on the session sheet (default: label)
          "side": "left|right|top|bottom",
          "pos": 3,                         dots from the top (left/right) or the left
          "unused": true                    greyed, and "free" on the session sheet
        }]
      }],

      "cables": [{
        "from": "drums.out", "to": "desk.ch1",
        "kind": "audio" | "cv",             cv is dashed
        "label": "stereo",                  at the middle of the longest straight run
        "via": [[x, y], ...],               explicit route, in dots
        "both": true,                       arrowheads at both ends (USB, MIDI thru)
        "badge": 2
      }],

      "inserts": [{"at": "desk.phones", "w": 4}],   dashed write-in box off a port

      "session": {
        "fields": [                         the header row; wraps as needed
          {"label": "DATE", "w": 62, "hint": "..."},
          {"label": "SPEED", "ticks": ["HIGH", "NORMAL"]},
          {"label": "PITCH", "dial": ["-", "+"]}
        ],
        "left_width": 440,                  the left column, in points
        "tables": [{
          "title": "MIXER", "rows": ["1", "2", "3", "4"],
          "columns": [
            {"name": "SOURCE", "type": "blank", "w": 80, "hints": ["..."]},
            {"name": "INPUT", "type": "ticks", "options": ["MIC", "LINE"]},
            {"name": "PAN", "type": "dial", "marks": ["L", "R"]}
          ]
        }],
        "clock": {"options": ["DAW", "none"], "slots": 8},
        "port_lists": ["iface"],            devices whose ports get a line each
        "changes": 6                        rows in the changes table
      },

      "cards_title": "Rules for this room",
      "cards": [{"n": 1, "title": "...", "lines": ["paragraph", "paragraph"]}]
    }

## Writing the words

Terse and specific: the panel's own names in capitals (`MONITOR OUT`, `CH 1`), what a
thing does rather than what it is. A card is a rule the room has taught you, one or two
short paragraphs; if it needs a third it is two cards. Keep personal details out of
anything shared: device names are fine, a person's name, address or network is not.
