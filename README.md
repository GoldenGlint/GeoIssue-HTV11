# CivicLens

Toronto civic-image collection for Hack the Valley. The current implementation collects, screens and groups photos, then describes candidate outdoor infrastructure issues with Gemini. Precise location verification and the product application remain separate work.

Start with the [collection package guide](scraping/README.md) for setup, commands, editable searches, and adding a source. The shared image format and processing live in [scraping/media.py](scraping/media.py).

| Area | Start here |
| --- | --- |
| Working collectors and review tools | [scraping/README.md](scraping/README.md) |
| Current collection status, freshness policy, and model handoff | [Collection workflow](scraping/docs/COLLECTION.md) |
| Automatic Gemini screening (Toronto / issue / locatability) | [Screening](scraping/docs/SCREENING.md) |
| Image-source experiment and expansion decisions | [Targeted discovery](scraping/docs/TARGETED-DISCOVERY.md) |
| Next social/photo sources and pilot gates | [Source expansion plan](scraping/docs/SOURCE-EXPANSION-PLAN.md) |
| Overall ingestion proposal | [Social-image ingestion plan](social-image-ingestion-plan.md) |
| Original project proposal | [Initial plan](initial-unfinalized-plans.md) |
| Challenge brief | [School of Cities](2026.10%20Hack%20The%20Valley%20School%20of%20Cities.md) |
| Civic-data references | [Toronto datasheet](2026.10%20Hack%20The%20Valley%20Datasheet.md) |

Saved images, local credentials, and session files stay in ignored local storage. Research summaries in `scraping/research/results/` contain sanitized evidence rather than raw account data.
