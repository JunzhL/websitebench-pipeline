// Minimal local stand-ins for @jackwener/opencli/errors.
//
// The OpenCLI npm package is not installed in this environment; this shim
// provides only the error classes the GENERATED adapters import, so the real
// adapter code (harbor/sites/ipvanish/interactions/adapters/*.js) can execute
// against the local clone. Nothing here alters adapter behavior.

export class ArgumentError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ArgumentError';
  }
}

export class CommandExecutionError extends Error {
  constructor(message, detail) {
    super(detail ? `${message} (${detail})` : message);
    this.name = 'CommandExecutionError';
  }
}

export class EmptyResultError extends Error {
  constructor(message) {
    super(message);
    this.name = 'EmptyResultError';
  }
}
