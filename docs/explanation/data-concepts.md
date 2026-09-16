# Data concepts

Start here to understand how a package such as ETHOS.RESKit finds its inputs and
why local access behaves differently across machines. These explanations keep
their own task-oriented names alongside the formal [Architecture](architecture/index.md)
guide.

| Page | Questions it answers |
|---|---|
| [Catalogues and storage](catalogues-and-storage.md) | How do the public/internal catalogues, collections, caches, and dCache fit together` |
| [Test data and reproducibility](test-data.md) | Which fixtures belong in Git` When should tests download` How do revisions and local edits differ` |
| [Why one catalogue](deduplication.md) | Why does a package declare collections` How do several packages reuse the same files` |
| [Caches, classes and roots](caches-and-access.md) | Where do files come from` When are they read in place or downloaded` |
| [The catalogue format](catalogue-format.md) | What is an index, descriptor, or shard` Why is inventory loading lazy` |
| [Licensing and immutability](licensing.md) | Why are access and visibility separate` Why must published paths retain their meaning` |

For the path from a request to usable files, see [Runtime View](architecture/runtime.md).
For the distinction between metadata hosting, dCache, and local test copies, see
[Deployment View](architecture/deployment.md).
