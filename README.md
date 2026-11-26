# PrivyMed

**Detecting and redacting personal information in clinical-style text — a reproducible comparison of rules, Microsoft Presidio, a fine-tuned transformer, a local LLM, and a hybrid system.**

> ⚠️ **Research and educational prototype.** All data is synthetic. PrivyMed is not a certified clinical privacy product, makes no HIPAA/GDPR compliance claims, and automatic detection can miss sensitive information.

## Status

Milestone 1 (foundation) in progress. No models trained and no results measured yet — see [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md).

## Entity schema

| Type | Covers |
|---|---|
| PATIENT | Patient and family-member names |
| STAFF | Doctor, nurse and other staff names |
| DATE | Dates, including dates of birth |
| PHONE | Phone numbers |
| EMAIL | Email addresses |
| CNIC | Pakistani national identity numbers |
| ID | MRNs, patient IDs, record identifiers |
| ADDRESS | Street addresses and locations |
| HOSPITAL | Hospitals, clinics, labs |

## Quick start (development)

```powershell
uv sync                 # create .venv and install dependencies
uv run pytest           # run tests
uv run ruff check .     # lint
uv run mypy             # type-check
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Experiments log](docs/EXPERIMENTS.md)
- [Project status](docs/PROJECT_STATUS.md)
- [Changelog](CHANGELOG.md)

## License

MIT — see [LICENSE](LICENSE).
