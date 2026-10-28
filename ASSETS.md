# Credits and artwork

The desktop companion was developed from the project context of
[Capri-Capricorn-The-Desktop-Construct](https://github.com/Juliowiwiwiwi/Capri-Capricorn-The-Desktop-Construct)
by Juliowiwiwiwi, inspected at upstream commit `9523828`.
This folder contains the independently added `capri.companion` desktop implementation,
not the upstream application's legacy Python modules or its Modelfile.

The active character artwork came from the supplied `capri-animation-library.zip`:
23 source clips, 137 source frames, plus a source catalog. The archive describes
existing pet artwork and newly generated activity/reaction artwork made with the
built-in image-generation tool. Additional artist names were not included.

`assets/library/source-manifest.json` retains its timing and provenance metadata.
Its source paths describe the supplied archive; runtime paths are the prepared
frames listed in `assets/companion/animations.json` and `transitions.json`.
All runtime frames share one transform from 256×256 to a 192×208 canvas:
resize to 240×240, then composite at (-24, -17). The leftward popcorn pose is mirrored.

## Licensing status

The MIT license in this repository covers original application code, scripts,
tests and documentation. **It does not license the character or artwork.**

No separate artwork license accompanied the supplied animation archive, and no
license file was present in the inspected upstream snapshot. Record the relevant
creator credits and artwork redistribution permission here before publishing the
bundled images. No permission is inferred from the source repository being public.

This is a community fan project; it is not presented as an official Cyberpunk product.
