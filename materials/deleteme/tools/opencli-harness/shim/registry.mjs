// Minimal stand-in for @jackwener/opencli/registry used only by the local
// adapter harness. It records generated command definitions for dispatch.
export const Strategy = Object.freeze({ LOCAL: 'LOCAL', BROWSER: 'BROWSER' });
globalThis.__wbLocalCliDefinitions = globalThis.__wbLocalCliDefinitions || [];
export function cli(definition) {
  globalThis.__wbLocalCliDefinitions.push(definition);
  return definition;
}
