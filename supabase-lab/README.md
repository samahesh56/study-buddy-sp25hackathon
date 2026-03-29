# Supabase Lab

Temporary sandbox for inspecting Supabase data before wiring it into the app.

This directory is intentionally isolated from the live frontend and backend code.
It is meant for:

- testing Supabase connectivity
- pulling sample rows from the browser and camera tables
- seeing which columns are actually populated
- saving inspection reports locally under `output/`

## Setup

1. Copy `.env.example` to `.env.local`
2. Fill in the Supabase URL, key, and table names
3. Run the scripts from this directory

## Commands

```bash
npm run test:connection
npm run inspect
```

`test:connection` verifies that the configured tables are reachable.

`inspect` pulls sample rows, counts records, computes basic field coverage, and writes a JSON report into `output/`.

## Notes

- This uses the Supabase REST API directly. No app integration happens here.
- Keep real credentials only in `supabase-lab/.env.local`.
- The directory is disposable and can be deleted once integration is finalized.
