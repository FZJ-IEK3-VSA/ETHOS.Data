# 0013. Treat every input as required, and say what is missing

**Status:** proposed · **Date:** 2026-10-06 · **Implemented by:** #16, #18

## Context

No workflow has an optional input. A dropped input surfaces deep in a
calculation, and a skip set once for a machine changes what every workflow on
it computes. The person who meets a refusal needs to see at once what is
missing and what to do about it; a page of description would bury that. A
handle cannot tell a mistyped name from a dataset the catalogue in use does
not publish.

## Decision

Every named path is required, and no API, command, option, setting or
environment variable leaves one out. A call returns all of them, or stops
before anything is downloaded and says what is missing. No dataset is ever
skipped. Each failure raises an error, and the command line exits with
status 2:

| Failure | Error | Message |
|---|---|---|
| The collection lacks the variant asked for | `CollectionError` | "collection 'onshore_wind' has no test variant" (or "full variant") |
| A named path is in one variant only | `CollectionError` | "collection 'onshore_wind': the named path 'gwa_200m' is in its full variant only" |
| Restricted data this account cannot read | `AccessError` | the refusal below |
| An unknown dataset name: mistyped, or not published by the catalogue in use | `UnknownDataset` | "collection 'onshore_wind': the dataset 'era5-lnd' cannot be found. Maybe it was mistyped, or it is not published." |
| An unknown key in a known dataset | `UnknownKey` | "'era5/x.nc' cannot be found in the dataset 'era5'." |

- A variant error gives no advice. Through `extends` it names both
  collections: "collection 'all' extends 'onshore_wind', whose …".
- The not-found message names the dataset and where it was asked for. Without a
  collection: "the dataset 'era5-lnd' cannot be found. Maybe it was mistyped,
  or it is not published." A mistyped and an unpublished name get the same
  message. It lists no datasets and gives no withdrawal hint: release notices
  announce withdrawals.
- Restricted data is refused before anything is downloaded, the public files
  of the same call included:

```text
error: the dataset 'gadm-3.6' is restricted.
  Obtain it: <ethos:restriction>
  Homepage: <homepage>
  Contact: <ethos:contact>
  This account lists no restricted cache.
  Once you have a copy you may use, register it:
    ethos-data config add-restricted-cache DIR
    ethos-data link gadm-3.6 DIR
```

- The "Obtain it", "Homepage" and "Contact" lines appear only where the
  catalogue records them. The reason line appears only when something other
  than a missing copy is wrong: the account lists no restricted cache, worded
  as a normal state; an entry is dangling or cannot be read, naming the
  cache; or a listed cache cannot be reached.
- The refusal prints no title, description, version, sources, licences,
  attribution or upstream status. `--meta` (`ls KEY --meta`,
  `show COLLECTION --meta`) prints the dataset's full description: every
  `user_facing` key ([0006](0006-every-file-format-specified-once.md)), the
  access class and the origin.
- `plan` and `verify` describe instead of refusing: such data is "not
  available here", with the reason. `plan`, `verify` and `report` give every
  restricted cache's state.
- A test checks that `--meta` prints every `user_facing` key.

## Alternatives considered

- **A skip for each call.** The keys of the result depend on the machine, and
  every caller has to check every named path.
- **An `optional:` flag per input in the collections file.** The same
  problem, and no workflow has an input it can do without.
- **The dataset's full description in the refusal.** What to do gets lost in
  text that `--meta` prints on request.
- **A not-found that lists the catalogue's datasets or suggests a
  withdrawal.** The list hides the one name that matters. The index leaves
  withdrawn datasets out, so the hint would follow every typo.

## Consequences

- Descriptor fields are text that users read, so catalogue maintainers write
  `ethos:restriction`, `homepage` and `ethos:contact` for the person without a
  copy.
- A package passes no skip option. A missing input stops the workflow with an
  error that says what is missing.
- See [Test and full variants of a collection](../../test-data.md#test-and-full-variants-of-a-collection)
  and [When a restricted input is missing](../../../how-to/data-users/use-data-in-a-script.md#licensed-input).

## Related

- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0014. Name workflow inputs in the collection and pair test and full variants](0014-named-inputs-and-test-full-variants.md)
- [0016. Give one link command two modes](0016-one-link-command-two-modes.md)
- [6. Runtime View](../runtime.md)
- [10. Quality Requirements](../quality-requirements.md)
