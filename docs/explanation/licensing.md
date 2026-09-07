# Licensing and immutability

Two rules in `ice2-data` exist to stop a particular kind of quiet mistake: data
that is used in a way nobody actually checked was permitted, and data that
changes underneath a result that has already been published.

## An absent licence is a question, not a default

A dataset whose redistribution terms nobody has read yet is marked:

```yaml
ice2:license_status: unresolved
ice2:license_note: "Terms unclear; enquiry sent to <contact> 2026-08-14."
```

Every `fetch()` of it emits a `UserWarning` naming the dataset and repeating the
note. That is deliberate friction. The alternative — treating silence as
permission — produces a catalogue where nobody can tell the datasets somebody
cleared from the datasets nobody looked at, and the distinction only becomes
visible when it is a problem.

The status is promoted into the catalogue **index**, so warning about licensing
does not require loading every dataset descriptor. `ice2-data list` stays cheap.

Resolving it means someone actually reads the upstream terms and adds a
`licenses:` block with an
[Open Definition licence id](http://licenses.opendefinition.org/):

```yaml
licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
```

`ice2:license_note` is stripped from the published catalogue — an internal note
about an unresolved legal question is not something to publish.

## Whose data is it

An absent licence is one question; *whose rights are these anyway* is a
different one, and for a long time nothing in a descriptor answered it. Most of
the catalogue is mirrored data — somebody else made it, we hold a copy, the
upstream terms are the terms. Some of it is not: the GeoTIFF conversions sitting
beside the netCDF originals in `landcover`, the whole of
`geothermal-resource`. That distinction had to be read out of prose in
`ice2:attribution`, one dataset at a time.

`ice2:origin` states it:

| | Means | Licensing consequence |
|---|---|---|
| `downloaded` | mirrored as obtained | the upstream terms are the terms |
| `derived` | computed from other data | ours, but downstream of somebody else's obligations |
| `created` | produced here from scratch | ICE-2 holds the rights |

It is **declared, never inferred** — the same rule as `ice2:catalog_role`.
Deducing "created here" from the presence of an author contributor would make an
authorship claim true by accident, and an authorship claim is exactly the kind of
thing that should require somebody to type it.

The default is `downloaded`, which is both the common case and the conservative
one: claiming less authorship than is true is safe, claiming more is not.

Claiming more than `downloaded` obliges you to say who — an `author` in
`contributors` — and, for `derived`, both what it came from (`sources`) and how
(`ice2:derivation`). Derived data inherits obligations from its inputs; a
derivation with no named input cannot be checked against them, and one with no
method is only half a claim.

## One dataset, several licences

`licenses` is a Frictionless list, and datasets really are under more than one
set of terms: a product whose documentation is CC-BY while the data is bespoke,
or upstream originals beside conversions we licence ourselves.

The awkward case is the second, because the terms differ *per file*. Splitting
the dataset in two to record two licences would be the tail wagging the dog —
they are one dataset by every other measure, and a consumer wanting the
authoritative bytes alongside the converted ones would then have to know about
both. Frictionless already solves it: a **resource** may carry its own
`licenses`, which override the package's. `ice2:applies_to` on a licence entry
is how a maintainer expresses that against a generated inventory.

Every licence still appears at package level, `ice2:applies_to` and all. A
reader that only looks at the package then sees the complete set — conservative
and true — while one that looks at a resource gets the exact answer. The
alternative, moving narrowed licences out of the package array, produces a
dataset whose licence list omits most of its licences.

A narrowing pattern that matches nothing **fails the build**, for the same
reason an `ice2:include` pattern that matches nothing does: silently licensing
no files is how a dataset ends up published under terms nobody applied.

## Restricted data is never copied

`ice2:access: restricted` means the licence forbids redistribution. The tooling
enforces that structurally rather than by convention:

- it is never downloaded, under any configuration;
- it is never written into the public cache;
- the [staging root](../how-to/stage-unpublished-data.md) never shadows it —
  licence terms are not a development concern;
- `ice2-data catalog upload` refuses it outright;
- `ice2-data materialize` refuses it.

It is read in place from a root somebody deliberately configured, or asking for
it fails with an explanation. See
[Work with restricted data](../how-to/restricted-data.md).

## Access and visibility are two questions

They are separate keys because they are separate decisions:

| | Asks | Values |
|---|---|---|
| `ice2:access` | who may read the bytes | `public` · `internal` · `restricted` |
| `ice2:visibility` | is the dataset listed in the public catalogue | `public` · `hidden` |

A dataset can be perfectly redistributable and still not ready to publish —
pending a paper, say. That is `access: internal, visibility: hidden`, and it
requires an embargo block:

```yaml
ice2:embargo:
  until: "2027-06-30"          # or "unspecified", with a reason
  reason: "Pending publication of the accompanying paper"
  becomes: public
```

The block is **required** so that nothing stays hidden by accident. Hiding
something is easy; remembering to un-hide it a year later is not, and a
catalogue whose hidden datasets have no stated end date accumulates them
permanently.

`ice2:embargo` is stripped from the published catalogue. What is being withheld,
and until when, is nobody else's business.

## Paths are immutable

**A file at a published path never changes.** If a dataset's content changes,
the new bytes go to a new path.

The reason is the checksum. A consumer's cache holds a file it verified against
the manifest, and it re-verifies cheaply on every fetch. If the bytes behind a
path could change, one of two things happens: either the consumer keeps its old
copy forever and silently diverges from everyone who fetched later, or the
checksum stops matching and a job that worked yesterday fails today with no
change on the consumer's side. Neither is acceptable, and the second is worse
because it looks like a bug in the tool.

The rule is enforced where it can be: `ice2-data catalog upload` passes
`rclone --immutable`, which fails loudly on an attempted overwrite.

Publishing a revision at a new path also has a practical payoff — the unchanged
files keep their paths, so an update re-downloads only what actually changed
rather than forcing a full re-fetch.

## Deleting is not how a dataset changes

The corollary. Deleting published bytes is for making something **stop
existing** — cleaning up test data, or genuinely withdrawing a dataset — not for
correcting one.

And when it is genuinely a withdrawal, the order matters and is the opposite of
publishing: **unpublish the catalogue entry first, then delete the bytes**. The
other way round leaves a public catalogue pointing at a path that 404s, and
anyone resolving it mid-way gets a broken reference instead of a clean "not
published". See [Withdraw a dataset](../how-to/withdraw-a-dataset.md).

## What this does not cover

The licence of `ice2-data` (MIT) is not the licence of the data it fetches.
Each dataset carries its own terms, and a dataset being reachable through this
tooling is not a statement that you may use it for what you have in mind. See
[Legal Notice](../legal-notice.md).
