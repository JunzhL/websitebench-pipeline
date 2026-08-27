// Minimal local stand-in for @jackwener/opencli/registry.
//
// `cli(definition)` records the adapter's command definition so the local
// harness can dispatch it; `Strategy` mirrors the constant the generated
// adapters reference. No behavior beyond registration.

export const Strategy = Object.freeze({ LOCAL: 'LOCAL', BROWSER: 'BROWSER' });

globalThis.__wbLocalCliDefinitions = globalThis.__wbLocalCliDefinitions || [];

export function cli(definition) {
  globalThis.__wbLocalCliDefinitions.push(definition);
  return definition;
}
