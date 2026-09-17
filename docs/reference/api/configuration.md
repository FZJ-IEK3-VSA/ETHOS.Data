# Configuration and access

Resolving the cache roots, and deciding where each resource is read from. The
rules are explained in
[Caches, classes and roots](../../explanation/caches-and-access.md); the keys
and precedence are tabulated in [Configuration](../configuration.md).

Every lookup returns a `Resolved` carrying both the value **and its
provenance** — because "why is my data going there`" is the question people
actually ask.

## Configuration

::: ethos_data.config
    options:
      members:
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
        - writable_config_path
        - config_sources
        - find_project_config
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
        - AccessError
        - borrowed_parent
        - which_cache
        - requires_local_root
        - check_missing
        - unavailable
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
