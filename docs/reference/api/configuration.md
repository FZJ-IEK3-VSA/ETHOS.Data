# Configuration and access

Resolving the cache roots, and deciding where each resource is read from. The
rules are explained in
[Caches, classes and roots](../../explanation/caches-and-access.md); the keys
and precedence are tabulated in [Configuration](../configuration.md).

Every lookup returns a `Resolved` carrying both the value **and its
provenance** — because "why is my data going there?" is the question people
actually ask. `Settings` is every setting at once, read once: what a handle
keeps as its `settings`.

!!! warning "Gap: per-dataset roots and the `internal` class are to be removed"
    With [one settings file per
    account](../../explanation/architecture/decisions/0010-one-settings-file-per-account.md),
    `dataset_roots`, `set_dataset_root` and `unset_dataset_root` go, and the
    restricted cache becomes `restricted_caches`, an ordered list with no
    default. With [decision
    0011](../../explanation/architecture/decisions/0011-access-class-picks-the-root.md),
    the access classes are `public` and `restricted`. To be implemented
    separately.

## Configuration

::: ethos_data.config
    options:
      members:
        - Settings
        - read_settings
        - Resolved
        - Roots
        - resolve_roots
        - resolve_public_cache
        - resolve_restricted_cache
        - resolve_staging_cache
        - resolve_cache_dir
        - resolve_skip_unavailable
        - resolve_catalog
        - resolve_collections
        - resolve_publication_url
        - dataset_roots
        - set_dataset_root
        - unset_dataset_root
        - set_option
        - unset_option
        - config_path
        - account_config_path
        - ignored_config_files
        - load_config
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Access

::: ethos_data.access
    options:
      members:
        - locate
        - Location
        - requires_local_root
        - check_missing
        - unavailable
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
