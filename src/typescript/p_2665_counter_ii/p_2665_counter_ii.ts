type ReturnObj = {
    increment: () => number;
    decrement: () => number;
    reset: () => number;
};

/* time O(1), space O(1) */
export function createCounter(init: number): ReturnObj {
    let num = init;
    return {
        increment: () => ++num,
        decrement: () => --num,
        reset: () => (num = init),
    };
}
