type Fn = (n: number, i: number) => unknown;

// time O(n), space O(1)
export function filter(arr: number[], fn: Fn): number[] {
    let indexForAssigned: number = 0;
    arr.forEach((num, index) => {
        if (fn(num, index)) {
            arr[indexForAssigned] = num;
            indexForAssigned += 1;
        }
    });
    // drop the tail of the array
    arr.splice(indexForAssigned, arr.length - indexForAssigned);
    return arr;
}
