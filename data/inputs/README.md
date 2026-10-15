# Optional normalized teammate inputs

Supply `gpa.json`, `professors.json`, and `verified-links.json` here when real outputs are ready. Until then the integration manifest explicitly says `pending`. These files are normalized public data inputs, not raw downloads or secrets.

See [team handoffs](../../docs/team-handoffs.md), [the contract](../../docs/data-contract.md), and clearly labeled synthetic examples under `data/examples/integration/`. The GPA and matching owners generate these files without editing the collector. Production rejects fixture-labeled inputs. Raw downloads belong in ignored `data/raw/` or `data/downloads/`.
