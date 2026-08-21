// Minimal error classes imported by the generated adapters.
export class ArgumentError extends Error {
  constructor(message) { super(message); this.name = 'ArgumentError'; }
}
export class CommandExecutionError extends Error {
  constructor(message, detail) {
    super(detail ? `${message} (${detail})` : message);
    this.name = 'CommandExecutionError';
  }
}
export class EmptyResultError extends Error {
  constructor(message) { super(message); this.name = 'EmptyResultError'; }
}
