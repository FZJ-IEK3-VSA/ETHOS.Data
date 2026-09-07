# Tutorials

Learning-oriented lessons. Each is a guided walk you can follow start to
finish. If you want to *understand by doing*, start here; if you already know
what you need and want a recipe, go to the [how-to guides](../how-to/index.md).

## Start here

**[Your first fetch](first-fetch.md)** — install the package, point it at a
catalogue, find out what is on offer, and download a collection. Then do the
same thing from Python, and watch the second fetch transfer nothing. Assumes
nothing but a terminal.

## Going deeper

The two tutorials below are the two things people actually do with `ice2-data`
after they have fetched something. They are independent; read whichever
describes you.

**[Use it from your own package](use-from-a-library.md)** — you maintain a
Python package that needs input data. Declare which slices of the catalogue it
needs, wrap `ice2_data` in a thin module so the rest of your code never touches
it, and pin a catalogue version so a released version of your package always
resolves to the same bytes. RESKit is the worked example.

**[Add a dataset to the catalogue](add-a-dataset.md)** — you have data that
other people's tools should be able to ask for. Describe it, build its
manifest, upload the bytes, and publish the entry — the full maintainer round
trip on one small dataset.

---

Once these make sense, the [how-to guides](../how-to/index.md) are the
task-oriented recipes, and [Explanation](../explanation/index.md) covers why
the cache is shaped the way it is — which is worth reading before you change
anything about it.
