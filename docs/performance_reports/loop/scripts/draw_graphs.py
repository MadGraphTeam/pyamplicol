"""Draw the report's example graphs with FeynKit's native renderer.

Writes ``figures/*.svg`` for u u~ > g g g: one Born graph, a pentagon and a box
with a tree attachment. Requires the Community
HEPKit module (FeynKit) and the ``symbolica-fonts`` data bundle; set
``SYMBOLICA_DATA_DIRECTORY`` to that bundle's ``fonts`` directory when the
module is loaded from an overlay. Usage, from the report directory::

    python scripts/draw_graphs.py
"""

from __future__ import annotations

import re
from pathlib import Path

from symbolica.community import hepkit as hep

OUT = Path(__file__).resolve().parent.parent / "figures"


def svg(drawing) -> str:
    # Typst's SVG reader ignores CSS custom properties; the stroke and fill
    # attributes already carry the light-theme colours, so drop the theme CSS,
    # scripts, hidden hover carriers and hover metadata.
    text = drawing.to_svg()
    text = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S)
    text = re.sub(r'<a [^>]*style="display:none".*?</a>', "", text, flags=re.S)
    text = re.sub(r"<title>.*?</title>", "", text, flags=re.S)
    return re.sub(r' data-linnet-detail="[^"]*"', "", text)


def loop_size(diagram) -> int:
    cycles, _ = diagram.cycle_basis()
    return len(cycles[0].internal_edges)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    process = hep.Model.qcd().process(["u", "u~"], ["g", "g", "g"])
    born = sorted(process.generate_diagrams(loops=0).diagrams, key=lambda d: d.id)
    # No bridge limit, as in pyAmpliCol's own graph generation.
    loops = sorted(
        process.generate_diagrams(loops=1, maximum_bridges=None).diagrams,
        key=lambda d: d.id,
    )
    pentagon = next(d for d in loops if loop_size(d) == 5)
    box = next(d for d in loops if loop_size(d) == 4 and len(d.internal_edges) == 5)
    tree = next(d for d in born if len(d.internal_edges) == 2)
    for name, diagram in (("born", tree), ("pentagon", pentagon), ("box", box)):
        (OUT / f"{name}.svg").write_text(svg(diagram.render()))
    print(OUT)


if __name__ == "__main__":
    main()
