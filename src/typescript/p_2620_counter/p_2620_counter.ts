export function createCounter(n: number): () => number {
  let value = n;
  return () => value++;
}
