# Configuration and access

Resolving the cache roots, and deciding where each resource is read from. The
rules are explained in
[Caches, classes and roots](../../explanation/caches-and-access.md); the keys
and precedence are tabulated in [Configuration](../configuration.md).

`read_settings` reads every setting at once into `Settings`, each value
with **its provenance** — because "why is my data going there?" is the
question people actually ask. A handle keeps it as its `settings`, and every
later read of a setting goes through it.

The access classes are `public` and `restricted`. Restricted data is read
from `Roots.restricted`, the restricted caches in order, and `entry_for` decides
which cache holds an entry that `link` or `materialize` makes.

## Configuration

::: ethos_data.config
    options:
      members:
        - Settings
        - read_settings
        - Roots
        - resolve_skip_unavailable
        - set_cache
        - add_restricted_cache
        - remove_restricted_cache
        - set_option
        - unset_option
        - config_path
        - account_config_path
        - load_config
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Access

::: ethos_data.access
    options:
      members:
        - locate
        - entry_for
        - restricted_entry
        - chain_for
        - Chain
        - Locator
        - linked_entry
        - Location
        - check_missing
        - unavailable
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
