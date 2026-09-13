# EDGAR Long-Form M&A Locator Addendum

## Gap closed
Helix could extract 10-K-style acquisition language when relevant text was supplied manually, but it could not discover/fetch the 10-K or locate M&A evidence across a long filing.

## Architecture
SEC submissions -> 10-K/10-K-A primary document -> HTML normalization -> document-wide M&A locator -> candidate regions -> existing production extractor -> REVIEW/MEDIUM candidate -> existing trust gate.

The locator is intentionally broader than the extractor. It may surface irrelevant text; it may not assert graph truth.

## 10-Q reuse
The locator is filing-type agnostic. 10-Q should be added by extending the configured long-form filing types, not by creating a duplicate locator.

## Files
- `code/parsers/edgar_longform_locator.py`
- `code/providers/edgar_resolver.py`
- `tests/test_edgar_longform_locator.py`
- `docs/DECISIONS_EDGAR_LONGFORM_LOCATOR.md`

## Still open
- historical SEC submissions files
- exhibits
- general divestiture extraction
- Disney vote fusion
- HelixFact identifier enrichment
