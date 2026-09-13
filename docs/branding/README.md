# ETHOS software logo family

This is a shared design proposal for the ETHOS packages. Every logo places a
square package symbol on the left and its name in Weissenhof Grotesk Bold on the
right. The standalone symbol is also its favicon. The initial eight designs
cover the five public frameworks listed on the institute's model-services page,
plus GeoKit, TSAM and ETHOS.Data, the new name for ice2-data.

## Shared rules

| Element | Rule |
|---|---|
| Naming | `ETHOS.` prefix for every package; preserve the package's established capitalisation |
| Typeface | Original Weissenhof Grotesk Bold OTF; exported lettering is outlined |
| Light wordmark | Jülich-Blau 1, `#023d6b` |
| Dark wordmark | White, `#ffffff` |
| Symbol | Dark-blue geometry on Jülich-Blau 2, `#adbde3` |
| Drawing area | 96 × 96 units, with 8 units of outer space on every side |
| Gap | 32 units between the symbol's right edge and the wordmark origin |
| Letter size | 70 units; constant across the family, with natural letter proportions |
| Wordmark baseline | 80 units from the top of the 112-unit canvas |
| Export width | Follows the actual name width; long names are never squeezed |
| Primary version | Symbol and name; purpose descriptions are ordinary page text |

Each package has a different silhouette. This keeps the favicons distinguishable
without assigning arbitrary colours to packages. The shared font, two blues,
proportions and square background make them recognisable as a family. The TSAM
symbol retains the idea of vertical time slices while using the common palette.
The symbol and its background remain identical in the light and dark versions.

The primary blues and typeface come from the local **FZJ Corporate Design Manual,
February 2025, v1.5**, pages 15 and 19. The resulting package marks are a design
proposal. Institutional attribution continues to use the existing FZJ/Jülich
Systems Analysis artwork and footer; the new symbols identify software packages.

## Package symbols

| Wordmark | Symbol | Meaning |
|---|---|---|
| ETHOS.Data | Indexed records | Shared catalogue and data cache |
| ETHOS.FINE | Connected components and a hub | Integrated energy-system optimisation |
| ETHOS.GLAES | Land cells and a check | Land availability and eligibility |
| ETHOS.RESKit | Wind turbine | Renewable energy generation |
| ETHOS.HiSim | House and energy flow | House infrastructure simulation |
| ETHOS.PeNALPS | Places and a transition | Petri-net-based industrial load modelling |
| ETHOS.GeoKit | Spatial layers | Shared geographic extent for raster and vector data |
| ETHOS.TSAM | Progressively wider time slices | Time series aggregation |

These eight form the first package set, not an exhaustive inventory of every
research model in the ETHOS suite. Additional packages use the same layout by
adding a record in `packages.json` and a drawing in `icons.tex`. Review the symbol
alongside the existing family at both full size and 16 pixels.

## Assets

All exports are in `docs/assets/branding/`.

| Pattern | Use |
|---|---|
| `ethos-<package>-logo-light.svg` | Full logo on white or pale backgrounds |
| `ethos-<package>-logo-dark.svg` | Full logo on dark backgrounds |
| `ethos-<package>-icon.svg` | Standalone symbol, site header or SVG favicon |
| `ethos-<package>-favicon-16.png` | Raster favicon at 16 pixels |
| `ethos-<package>-favicon-32.png` | Raster favicon at 32 pixels |
| `ethos-<package>-favicon-48.png` | Raster favicon at 48 pixels |
| `ethos-data-logo-preview.svg` / `.png` | ETHOS.Data on both backgrounds |
| `ethos-family-light-preview.svg` / `.png` | All wordmarks at a common scale |
| `ethos-family-dark-preview.svg` / `.png` | The same family on a dark background |
| `ethos-family-favicons-preview.svg` / `.png` | Each symbol at 16, 32, 48 and 64 pixels |

Use the icon where a complete name would become too small. Keep its padding and
preserve the logo's aspect ratio. In a family comparison, use equal icon heights
rather than forcing different-length wordmarks to the same total width.

ETHOS.Data's documentation uses the new assets. The other package exports are
prepared here for review and later adoption in their respective repositories.
The distribution name and Python imports (`ethos_data`) and the CLI (`ethos-data`)
use the new name as well.

## Regenerate

Initialize conda using the script for your installation. On this cluster:

```bash
source /fast/home/j-belina/miniforge3/etc/profile.d/conda.sh
conda activate reskit_env_data_09_2026
python docs/branding/render.py --all --preview
```

The default renders ETHOS.Data only. `--all` renders every package in
`packages.json`; `--preview` also creates PNG favicons and review sheets.

`logo.tex` controls the shared typography, colours and spacing. `icons.tex`
contains the package symbols. The renderer uses Tectonic and Poppler
(`pdftocairo` and `pdffonts`); PNG exports additionally use `rsvg-convert` from
librsvg. It verifies the PDF wordmarks use Weissenhof Grotesk Bold before
converting them to vector paths.

The default font directory is
`docs/font/weissenhof-grotesk/weissenhof-grotesk/OTF`. Use `--font-dir PATH` for
another local installation. The Regular, Bold, Italic and BoldItalic OTF files
must be present. No system-font installation is required, and missing files
produce an error rather than a substitute typeface.

The fonts and local reference PDFs stay in the ignored `docs/font/` directory,
which is also excluded from the MkDocs site. Published SVGs contain paths, not
font files, and viewing or building the documentation needs no font licence
files or installed font. Ordinary docs builds do not invoke Tectonic.

## References

- [ETHOS Model Suite at ICE-2](https://www.fz-juelich.de/en/ice/ice-2/expertise/model-services): initial list of FINE, GLAES, RESKit, HiSim and PeNALPS.
- [ETHOS.GeoKit](https://github.com/FZJ-IEK3-VSA/geokit): geospatial toolkit and suite affiliation.
- [ETHOS.TSAM](https://github.com/FZJ-IEK3-VSA/tsam): time series aggregation and suite affiliation.
- [Original TSAM logo reference](https://tsam.readthedocs.io/en/latest/assets/tsam-logo-light.svg): initial visual reference for the symbol-plus-wordmark arrangement.
- Local design reference: `docs/font/CD-Manual_2025-02_v1.5_de.pdf`, pages 15 and 19.
