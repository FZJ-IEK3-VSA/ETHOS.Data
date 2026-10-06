"""Every key and every closed vocabulary of the ETHOS.Data formats, spelled once.

Code that reads or writes a descriptor names a key through these constants
rather than a string literal, so a key cannot be spelled two ways and its
default cannot be written down twice. The specifications in the sibling
modules use them as their aliases.
"""

from __future__ import annotations

# -- dataset.yaml and the descriptor generated from it --------------------------

NAME = "name"
TITLE = "title"
DESCRIPTION = "description"
HOMEPAGE = "homepage"
ID = "id"
VERSION = "version"
SOURCES = "sources"
CONTRIBUTORS = "contributors"
LICENSES = "licenses"
RETRIEVED = "ethos:retrieved"
CONTACT = "ethos:contact"
ATTRIBUTION = "ethos:attribution"
COVERAGE_NOTE = "ethos:coverage_note"
UPSTREAM = "ethos:upstream"
ORIGIN = "ethos:origin"
DERIVATION = "ethos:derivation"
SOURCE_DIR = "source_dir"
REMOTE_PREFIX = "ethos:remote_prefix"
ACCESS = "ethos:access"
VISIBILITY = "ethos:visibility"
EMBARGO = "ethos:embargo"
LICENSE_STATUS = "ethos:license_status"
LICENSE_NOTE = "ethos:license_note"
RESTRICTION = "ethos:restriction"
INCLUDE = "ethos:include"
EXCLUDE = "ethos:exclude"
SHARD_DEPTH = "ethos:shard_depth"
#: The dataset this one replaces, with another layout and other keys.
SUPERSEDES = "ethos:supersedes"

# In use in the catalogue before the format reference named them.
PROVENANCE = "ethos:provenance"
VERIFIED = "ethos:verified"
INPUT_DATASETS = "ethos:input_datasets"
TILING = "ethos:tiling"
ADDITIONAL_VARIABLES = "ethos:additional_variables"

# Inside one ``licenses`` entry.
APPLIES_TO = "ethos:applies_to"
DOCUMENT = "ethos:document"
DOCUMENT_SHA256 = "ethos:document_sha256"

# -- written by the build only ---------------------------------------------------

SCHEMA = "$schema"
PATH = "path"
#: Of one entry in ``ethos:shards``: the directory prefix it holds.
PREFIX = "prefix"
RESOURCES = "resources"
SHARDS = "ethos:shards"
SHARD = "ethos:shard"
TOTAL_BYTES = "ethos:total_bytes"
FILE_COUNT = "ethos:file_count"
NAMESPACE = "ethos:namespace"
SIDECARS = "ethos:sidecars"
#: Of a descriptor and its index row: which revision of the dataset it
#: describes, absent for the first. Of a resource: the revision its bytes were
#: published in, absent for the first; the object is
#: ``<remote_prefix>@<revision>/<path>``.
REVISION = "ethos:revision"
#: Written by the build into a dataset another one's ``ethos:supersedes`` names.
SUPERSEDED_BY = "ethos:superseded_by"

# Inside one ``resources`` record.
BYTES = "bytes"
HASH = "hash"
MEDIATYPE = "mediatype"
#: What a record that names no media type is read as.
DEFAULT_MEDIATYPE = "application/octet-stream"
#: Set on the descriptor staging synthesises; never in a real catalogue.
STAGED = "ethos:staged"
#: The access class staging gives a dataset the catalogue does not describe;
#: never in a real catalogue either.
STAGING = "staging"

# -- catalog.yaml and datacatalog.json -------------------------------------------

DATASETS = "datasets"
PUBLICATION_URL = "ethos:publication_url"
#: Of catalog.yaml: how the maintainer commands reach the publication store.
STORE = "ethos:store"
CATALOG_ROLE = "ethos:catalog_role"
#: Of the published index: every public release, the current one included.
RELEASES = "ethos:releases"

# -- collections.yaml: its release bounds and the variants of a collection ------

MIN_VERSION = "min_version"
MAX_VERSION = "max_version"
EXACT_VERSION = "exact_version"
VARIANT_TEST = "test"
VARIANT_FULL = "full"
VARIANTS = (VARIANT_TEST, VARIANT_FULL)

# -- status.yaml, the record the catalog commands keep of each dataset -------------

STATE = "state"
COPIES = "copies"
AUTHORITY = "authority"
HISTORY = "history"

# -- closed vocabularies -----------------------------------------------------------

PUBLIC = "public"
RESTRICTED = "restricted"
ACCESS_CLASSES = (PUBLIC, RESTRICTED)

HIDDEN = "hidden"
VISIBILITIES = (PUBLIC, HIDDEN)

DOWNLOADED = "downloaded"
DERIVED = "derived"
CREATED = "created"
#: Declared, never inferred: "somebody here made this" has licensing
#: consequences, and downloaded is both the common and the conservative case.
ORIGINS = (DOWNLOADED, DERIVED, CREATED)

RESOLVED = "resolved"
UNRESOLVED = "unresolved"
UNKNOWN = "unknown"
LICENSE_STATUSES = (RESOLVED, UNRESOLVED, UNKNOWN)

AUTHOR = "author"
CONTRIBUTOR_ROLES = (AUTHOR, "contributor", "maintainer", "publisher", "wrangler")

UPSTREAM_STATUSES = (
    "available",
    "superseded",
    "withdrawn",
    "on-request",
    "no-upstream",
)

ROLE_SOURCE = "source"
ROLE_PUBLISHED = "published"
CATALOG_ROLES = (ROLE_SOURCE, ROLE_PUBLISHED)

#: A dataset's states in status.yaml, in the order a dataset passes through
#: them; ``ethos_data.model.lifecycle`` says which step leads from which.
STATE_DRAFT = "draft"
STATE_BUILT = "built"
STATE_AVAILABLE = "available"
STATE_FROZEN = "frozen"
STATE_WITHDRAWN = "withdrawn"
STATE_PURGED = "purged"
STATES = (
    STATE_DRAFT,
    STATE_BUILT,
    STATE_AVAILABLE,
    STATE_FROZEN,
    STATE_WITHDRAWN,
    STATE_PURGED,
)

#: How a copy of a dataset's bytes in status.yaml came to be where it is.
COPY_UPLOADED = "uploaded"
COPY_LINKED = "linked"
COPY_MATERIALIZED = "materialized"
COPY_KINDS = (COPY_UPLOADED, COPY_LINKED, COPY_MATERIALIZED)

#: ``until`` of an embargo whose end nobody can name yet; needs a reason.
UNSPECIFIED = "unspecified"

DATAPACKAGE_PROFILE = "https://datapackage.org/profiles/2.0/datapackage.json"
DATACATALOG_PROFILE = "https://datapackage.org/profiles/2.0/datacatalog.json"

# -- the generated catalogue files ----------------------------------------------

#: A dataset's generated descriptor, beside its dataset.yaml.
PACKAGE_FILE = "datapackage.json"
#: The catalogue's generated index, at the catalogue's root.
INDEX_FILE = "datacatalog.json"

# -- records the tools write beside data -----------------------------------------

#: In the staging root: who staged which directory under which name, and why.
STAGING_REGISTRY_FILE = ".ethos-data-staging.json"
#: In a materialised cache entry: where its bytes were copied from.
MATERIALIZED_RECORD_FILE = ".ethos-data-materialized.json"
#: Beside a dataset's datapackage.json in a source checkout: the build's
#: hashes by size and mtime. Private, never published.
HASH_CACHE_FILE = ".ethos-data-hash-cache.json"

# -- the settings file -------------------------------------------------------------

#: The settings file in the account's configuration directory.
SETTINGS_FILE = "config.yaml"
SETTING_PUBLIC_CACHE = "public_cache"
SETTING_RESTRICTED_CACHES = "restricted_caches"
SETTING_STAGING_CACHE = "staging_cache"
SETTING_CATALOG = "catalog"
SETTING_PUBLICATION_URL = "publication_url"
