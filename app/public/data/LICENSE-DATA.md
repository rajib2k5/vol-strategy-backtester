# Licence of the data in this folder

The full list of data sources, their terms and what is committed is in [`DATA.md`](../../../DATA.md) at the root of the repository. This page is the notice that sits next to the data.

## `data_quality.json`: partly DoltHub-derived, CC BY-SA 4.0

Attribution: contains information derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Changes: we aggregated it into counts, shares and quantiles and compared it with another vendor's chains. No quote row is reproduced.

These fields are DoltHub-derived, and are shared under CC BY-SA 4.0:

- `flags_by_year`: the rows where `source` is `dolthub` (their `rows`, `counts` and `shares`);
- `sources`: the `dolthub` row;
- `calendar`: the rows where `source` is `dolthub`;
- `gate.thresholds`: the rows where `source` is `dolthub` (the `worst` values);
- `cross_vendor`: all of it, because it compares DoltHub with OptionsDX (`distributions`, `within_thresholds`, `by_year`).

The OptionsDX-derived numbers in the file (the rows where `source` is `optionsdx`, and the OptionsDX side of `cross_vendor`) are aggregate counts, shares and quantile summaries only: our own measurements, with no OptionsDX quote, price or chain row.

The rest of the file (the flag names and descriptions, the labels, the gate limits and the envelope) is our own text and is MIT.

## The other files here

- `illustrative_surface.json`: a made-up SSVI surface, not market data. MIT, like the rest of the repository.
- `manifest.json`: lists the datasets above. MIT.

The rest of the repository is MIT, see [`LICENSE`](../../../LICENSE).
