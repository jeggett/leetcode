export function createHelloWorld() {
  return function (...args: unknown[]): string {
    return "Hello World";
  };
}
