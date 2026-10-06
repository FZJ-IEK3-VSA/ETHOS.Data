## Accepted: ${name}

`${name}` is in the catalogue as of release ${release}. To finish:

1. Raise `catalog.min_version` in your collections file to `${release}`.
2. Remove the staging entries you used for it.
3. If it came from a bundle, run `bundle update` with the catalogue readable:
   it records the bundle's alignment with the release, and the warning that
   the bundle is ahead of the catalogue stops.
4. Run your workflow against the released catalogue.
