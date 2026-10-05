# 0013. Treat every input as required, and describe what is missing

**Status:** proposed · **Date:** 2026-10-02 · **Implemented by:** #16, #18

## Context

No workflow has an optional input. A dropped input surfaces deep in a
calculation, and a skip set once for a machine changes what every workflow on
it computes. The person who meets a refusal needs to know what the dataset is
and how to get a copy.

## Decision

- No API, command, setting or environment variable leaves an input out. A
  call returns every named path the collection names, or raises.
- A restricted dataset this machine cannot read is refused before anything is
  downloaded, the public files of the same call included. That covers four
  cases: no restricted cache, no entry, a dangling entry and an unreadable
  entry.
- The refusal is the dataset's description, built from the keys the
  specifications mark `user_facing`
  ([0006](0006-every-file-format-specified-once.md)): title, description,
  version, homepage, sources, licences, attribution, `ethos:restriction`,
  upstream status and note, and contact. It ends with the two commands that
  register a copy: `ethos-data config set-restricted-cache DIR` and
  `ethos-data link <dataset> <dir>`.
- `--meta` (`ls KEY --meta`, `show COLLECTION --meta`) prints the same text,
  plus the access class and the origin.
- `plan` and `verify` describe instead of refusing: such data is "not
  available here", with the reason.
- A test checks that every `user_facing` key is printed.

## Alternatives considered

- **A skip for each call.** The keys of the result depend on the machine, and
  every caller has to check every named path.
- **An `optional:` flag per input in the collections file.** The same
  problem, and no workflow has an input it can do without.

## Consequences

- Descriptor fields are text that users read, so catalogue maintainers write
  `ethos:restriction`, `homepage` and `sources` for the person without a copy.
- A package passes no skip option. A missing input stops the workflow with
  the dataset's description.
- Internal data that the shared cache does not hold is refused at the
  download, with a pointer to the shared cache
  ([0012](0012-one-lookup-chain.md), [0028](0028-read-only-shared-cache.md)).
- See [When a licensed input is missing](../../../how-to/data-users/use-data-in-a-script.md#licensed-input).

## Related

- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0014. Name workflow inputs in the collection and pair test and full variants](0014-named-inputs-and-test-full-variants.md)
- [0028. Serve shared data on the cluster from a read-only shared cache](0028-read-only-shared-cache.md)
- [6. Runtime View](../runtime.md)
- [10. Quality Requirements](../quality-requirements.md)
