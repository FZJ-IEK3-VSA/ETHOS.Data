# Explanation

Why `ice2-data` is shaped the way it is. These pages are about design
decisions and their consequences, not about getting a task done — for that, see
the [how-to guides](../how-to/index.md).

| Page | Answers |
|---|---|
| [Why one catalogue](deduplication.md) | Why does a tool declare *slices* rather than files? What actually makes the deduplication work, and what would break it? |
| [Caches, classes and roots](caches-and-access.md) | Why three cache roots and not one, or one per dataset? How does a dataset end up read in place rather than downloaded? |
| [The catalogue format](catalogue-format.md) | Why Frictionless Data Packages? Why is loading lazy, and what is sharding for? |
| [Licensing and immutability](licensing.md) | Why does an absent licence produce a warning rather than a default? Why can a published path never be reused? |

---

The shortest version of all four:

**Deduplication is achieved by agreement, not by synchronisation.** Every tool
derives the same cache path from the same catalogue entry, so the second tool to
ask for a file finds it already there. Nothing coordinates, because nothing
needs to.

**Configuration is two settings, not a table.** Which root a dataset comes from
follows from its access class; whether it is read in place follows from whether
its cache entry is a symbolic link. Both facts are already available without
anybody writing them down.

**Metadata is cheap and inventories are lazy.** The index answers sizes, file
counts, access classes and licence status without loading a single dataset
descriptor, which is what keeps `list` instant on a catalogue holding 170,000-file
datasets.

**Ambiguity fails loudly.** An unresolved licence warns on every download. A
dataset that cannot be reached stops the command and says what to configure. A
`.one("suffix")` that matches two files raises. The alternative in each case is
a wrong answer that nobody notices until it is in a result.
