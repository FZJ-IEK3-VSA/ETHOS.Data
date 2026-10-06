# Configuration and access

Resolving the cache roots, and deciding where each resource is read from. The
rules are explained in
[Caches, classes and roots](../../explanation/caches-and-access.md); the keys
and precedence are tabulated in [Configuration](../configuration.md).

`read_settings` reads every setting at once into `Settings`, each value
with **its provenance** — because "why is my data going there?" is the
question people actually ask. A handle keeps it as its `settings`, and every
later read of a setting goes through it.

!!! warning "Gap: the restricted cache and the `internal` class are to change"
    With [one settings file per
    account](../../explanation/architecture/decisions/0010-one-settings-file-per-account.md),
    the restricted cache becomes `restricted_caches`, an ordered list with no
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
        - Roots
        - resolve_skip_unavailable
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
        - Location
        - requires_local_root
        - check_missing
        - unavailable
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
