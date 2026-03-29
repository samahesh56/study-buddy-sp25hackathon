import { loadLabEnv } from "./_env.mjs";
import { fetchTableCount, fetchTableRows } from "./_supabase.mjs";

async function main() {
  const config = loadLabEnv();
  const targets = [
    {
      label: "camera",
      table: config.cameraTable,
      orderColumn: config.cameraOrderColumn,
    },
    {
      label: "browser",
      table: config.browserTable,
      orderColumn: config.browserOrderColumn,
    },
  ];

  for (const target of targets) {
    const count = await fetchTableCount(config, target.table);
    const rows = await fetchTableRows(config, target.table, {
      limit: 1,
      orderColumn: target.orderColumn,
    });

    console.log(
      JSON.stringify(
        {
          status: "ok",
          target: target.label,
          table: target.table,
          count,
          sample_keys: rows[0] ? Object.keys(rows[0]) : [],
        },
        null,
        2
      )
    );
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
