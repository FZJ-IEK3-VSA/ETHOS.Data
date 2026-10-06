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
UPLOADED = "ethos:uploaded"
FROZEN = "ethos:frozen"
ACCESS = "ethos:access"
VISIBILITY = "ethos:visibility"
EMBARGO = "ethos:embargo"
LICENSE_STATUS = "ethos:license_status"
LICENSE_NOTE = "ethos:license_note"
RESTRICTION = "ethos:restriction"
INCLUDE = "ethos:include"
EXCLUDE = "ethos:exclude"
SHARD_DEPTH = "ethos:shard_depth"

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
RESOURCES = "resources"
SHARDS = "ethos:shards"
SHARD = "ethos:shard"
TOTAL_BYTES = "ethos:total_bytes"
FILE_COUNT = "ethos:file_count"
NAMESPACE = "ethos:namespace"
SIDECARS = "ethos:sidecars"
#: Set on the descriptor staging synthesises; never in a real catalogue.
STAGED = "ethos:staged"

# -- catalog.yaml and datacatalog.json -------------------------------------------

DATASETS = "datasets"
PUBLICATION_URL = "ethos:publication_url"
CATALOG_ROLE = "ethos:catalog_role"

# -- closed vocabularies -----------------------------------------------------------

PUBLIC = "public"
INTERNAL = "internal"
RESTRICTED = "restricted"
ACCESS_CLASSES = (PUBLIC, INTERNAL, RESTRICTED)

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

#: ``until`` of an embargo whose end nobody can name yet; needs a reason.
UNSPECIFIED = "unspecified"

DATAPACKAGE_PROFILE = "https://datapackage.org/profiles/2.0/datapackage.json"
DATACATALOG_PROFILE = "https://datapackage.org/profiles/2.0/datacatalog.json"

# -- records the tools write beside data -----------------------------------------

#: In the staging root: who staged which directory under which name, and why.
STAGING_REGISTRY_FILE = ".ethos-data-staging.json"
#: In a materialised cache entry: where its bytes were copied from.
MATERIALIZED_RECORD_FILE = ".ethos-data-materialized.json"
