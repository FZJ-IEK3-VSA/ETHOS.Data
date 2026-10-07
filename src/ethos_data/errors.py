"""Every refusal ethos_data raises on purpose, in one place.

Library code raises these and never exits the process: a script that asks for
data, a test that checks a rule and the ``ethos-data`` command all receive the
same exception and decide for themselves what to do with it. The command line
prints one as ``error: <message>`` and exits with its :attr:`~EthosDataError.exit_code`.

Each class also derives from the standard exception that describes it, so an
``except KeyError`` catches an unknown name and an ``except OSError`` an
unreadable catalogue. Import them from here, or from :mod:`ethos_data`.

Two groups, by what the command line returns:

``2``  the request could not be served: an unknown name, an unreadable
       catalogue, data this machine cannot read, an invalid collection,
       bundle or setting, a refused staging entry;
``1``  a maintenance command refused its input: a descriptor the build
       rejects, a checkout that is not a source catalogue, an upload or a
       publication that cannot go ahead.
"""

from __future__ import annotations

__all__ = [
    "AccessError",
    "BundleError",
    "CatalogUnavailable",
    "CatalogVersionError",
    "CatalogueRootError",
    "CollectionError",
    "ConfigurationError",
    "DescriptorError",
    "DownloadError",
    "EthosDataError",
    "IncompleteCatalog",
    "LinkError",
    "MaintenanceError",
    "NotFetched",
    "PublishError",
    "StagingError",
    "TransitionError",
    "UnknownCollection",
    "UnknownDataset",
    "UnknownKey",
    "UploadError",
]


class EthosDataError(Exception):
    """Base of every refusal ethos_data raises on purpose."""

    #: What the command line exits with when this reaches it.
    exit_code = 2

    @property
    def message(self) -> str:
        """The sentence to print, without the quoting ``KeyError`` adds to ``str()``."""
        return str(self.args[0]) if self.args else type(self).__name__


# -- reading a catalogue -----------------------------------------------------


class UnknownDataset(EthosDataError, KeyError):
    """A collection or key names a dataset this catalogue does not describe.

    Either the name is mistyped, or the catalogue in use does not publish the
    dataset. Both get the same plain message.
    """


class UnknownKey(EthosDataError, KeyError):
    """A key names a dataset the catalogue has, but no file or folder in it."""


class CatalogUnavailable(EthosDataError, OSError):
    """The catalogue index itself could not be read.

    Either there is no index, or another version of ETHOS.Data wrote it and a
    dataset's row lacks a key this version reads from it. Distinct from
    :class:`IncompleteCatalog`, which is about a dataset the index promised.
    The message names the location and says how to point at another catalogue.
    """


class CatalogVersionError(EthosDataError, LookupError):
    """The catalogue is not a release the collections file accepts.

    The message names both: the release the catalogue records, or that it
    records none, and the bounds the file sets.
    """


class IncompleteCatalog(EthosDataError, FileNotFoundError):
    """The index lists a dataset whose descriptor or shard is not where it says.

    Loading is lazy, so this surfaces long after the index was read, on the
    first fetch that touches the dataset. It happens when a tree is deployed
    piecemeal, or an index from one revision sits beside descriptors from
    another.
    """


# -- collections, bundles, access ---------------------------------------------


class UnknownCollection(EthosDataError, KeyError):
    """A name the collections file does not define."""


class CollectionError(EthosDataError, ValueError):
    """A collection is defined in a way that cannot be resolved.

    A maintainer's mistake in ``collections.yaml``: a variant that does not
    exist, selection keys both inside and outside the variants, a ``paths``
    handle naming a file the collection does not include, or two variants that
    disagree about which handles they offer.
    """


class BundleError(EthosDataError, ValueError):
    """A bundle is incomplete, invalid, or differs from its own ``bundle.json``."""


class AccessError(EthosDataError, RuntimeError):
    """A dataset cannot be reached under the current configuration."""


class NotFetched(AccessError):
    """A file ``fetch=False`` would have had to download: it is not on this machine.

    The message names each file and the path it belongs at, which is where the
    same call with ``fetch=True`` puts it.
    """


class DownloadError(AccessError):
    """A file could not be downloaded, or what arrived does not match its hash.

    The message names the URL, so a missing object, an unreachable store and
    a damaged transfer each say where to look.
    """


class LinkError(EthosDataError, RuntimeError):
    """A cache entry cannot be created or removed, and why."""


class StagingError(EthosDataError):
    """A staging entry cannot be added or removed as asked."""


class ConfigurationError(EthosDataError, ValueError):
    """A setting, settings file or environment variable that cannot be used."""


# -- maintaining a catalogue ---------------------------------------------------


class MaintenanceError(EthosDataError):
    """A catalogue maintenance command refused its input."""

    exit_code = 1


class CatalogueRootError(MaintenanceError):
    """The directory is not a source catalogue a maintenance command can act on."""


class DescriptorError(MaintenanceError, ValueError):
    """A ``dataset.yaml``, ``catalog.yaml`` or inventory the build cannot accept."""


class UploadError(MaintenanceError):
    """An upload that cannot go ahead: a dataset not eligible, or no credentials."""


class PublishError(MaintenanceError):
    """The public catalogue cannot be generated as asked."""


class TransitionError(MaintenanceError):
    """A step the dataset's state does not allow, and what it needs first."""
