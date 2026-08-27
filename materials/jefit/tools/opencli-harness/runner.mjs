// Local execution harness for the GENERATED wb-jefit OpenCLI adapters.
//
// The real OpenCLI CLI is not installed in this environment and installing
// adapters into ~/.opencli is out of bounds for this run. This harness
// executes the committed, generator-produced adapters
// (harbor/sites/jefit/interactions/adapters/*.js) verbatim over plain HTTP:
// it implements only the surrounding surface the replay runner shells out to
// (`<binary> <site> <command> --flag value ... -f json`, `--version`,
// `doctor`) plus module-resolution for the tiny @jackwener/opencli imports
// (shim/). Observation rows come from the real adapter code, never from this
// harness.
//
// Advisory only, like every replay artifact.

import { registerHooks } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHIM = {
  '@jackwener/opencli/registry': pathToFileURL(
    path.join(HERE, 'shim', 'registry.mjs'),
  ).href,
  '@jackwener/opencli/errors': pathToFileURL(
    path.join(HERE, 'shim', 'errors.mjs'),
  ).href,
};
const ADAPTERS = path.resolve(
  HERE,
  '..',
  '..',
  '..',
  '..',
  'harbor',
  'sites',
  'jefit',
  'interactions',
  'adapters',
);

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (SHIM[specifier]) {
      return { url: SHIM[specifier], shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});

function fail(message, code = 1) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

function parseFlags(rest, defs) {
  const args = {};
  for (const def of defs) args[def.name] = def.default;
  let format = 'json';
  for (let index = 0; index < rest.length; index += 1) {
    const token = rest[index];
    if (token === '-f' || token === '--format') {
      format = rest[index + 1];
      index += 1;
      continue;
    }
    if (!token.startsWith('--')) fail(`unexpected argument: ${token}`, 2);
    const name = token.slice(2);
    const def = defs.find((entry) => entry.name === name);
    if (!def) fail(`unknown flag --${name}`, 2);
    const raw = rest[index + 1];
    index += 1;
    args[name] = def.type === 'int' ? Number.parseInt(raw, 10) : raw;
  }
  return { args, format };
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv[0] === '--version') {
    // Deliberately NOT an OpenCLI version string: this is the local harness.
    process.stdout.write('wb-local-adapter-harness 0.1.0\n');
    return;
  }
  if (argv[0] === 'doctor') {
    // No browser bridge exists here; report the degraded state honestly.
    process.stdout.write(
      'wb-local-adapter-harness: OpenCLI is not installed\n' +
        'extension: not connected\n[fail] connectivity\n',
    );
    process.exit(1);
  }
  const [site, command, ...rest] = argv;
  if (site !== 'wb-jefit') fail(`unknown site ${site}`, 2);
  if (!['state', 'click', 'submit'].includes(command)) {
    fail(`unknown command ${command}`, 2);
  }
  await import(pathToFileURL(path.join(ADAPTERS, `${command}.js`)).href);
  const definition = (globalThis.__wbLocalCliDefinitions || []).find(
    (entry) => entry.name === command && entry.site === site,
  );
  if (!definition) fail(`adapter did not register ${site} ${command}`, 2);
  const { args, format } = parseFlags(rest, definition.args);
  try {
    const rows = await definition.func(args);
    if (format === 'json') {
      process.stdout.write(`${JSON.stringify(rows)}\n`);
    } else {
      for (const row of rows) process.stdout.write(`${JSON.stringify(row)}\n`);
    }
  } catch (error) {
    fail(`${error.name || 'Error'}: ${error.message}`, 1);
  }
}

await main();
