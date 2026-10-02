## Accepted: ${name}

`${name}` is in the catalogue as of release ${release}. To finish:

1. Raise `catalog.min_version` in your collections file to `${release}`.
2. Remove the staging entries and dataset-root overrides you used for it.
3. If it came from a bundle, run `bundle update`, which records the release
   in the bundle, and the warning about an unpublished version stops.
4. Run your workflow against the released catalogue.
