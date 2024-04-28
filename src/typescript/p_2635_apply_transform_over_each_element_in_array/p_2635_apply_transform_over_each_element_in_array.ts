/* time O(n), space O(1) */
export function map(arr: number[], fn: (n: number, i: number) => number): number[] {
    const result: number[] = [];
    for (let index = 0; index < arr.length; index++) {
        result.push(fn(arr[index], index));
    }

    return result;
}
