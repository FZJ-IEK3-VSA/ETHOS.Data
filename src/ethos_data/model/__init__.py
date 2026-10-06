"""The reader's model of a catalogue: resources, dataset names, digests.

The model layer, beside :mod:`ethos_data.formats`: plain values and the rules
about them, written once and shared by everything that reads a catalogue, a
bundle or a staging root, and by the build that writes them. Nothing here
reads settings, touches the network, prints or exits; the one input it does is
hashing a file it is handed.

- :mod:`.digest`: the SHA-256 of a file, and how a catalogue spells one.
- :mod:`.names`: dataset names, the families they form, and the relative
  paths a dataset or bundle may contain.
- :mod:`.resource`: one file of a dataset, the record a descriptor keeps for
  it, and the companions that travel with it.
"""

from __future__ import annotations

from .resource import Resource

__all__ = ["Resource"]
