type ToBeOrNotToBe = {
    toBe: (val: unknown) => boolean;
    notToBe: (val: unknown) => boolean;
};

// time: O(1), space: O(1)
export function expect(val: unknown): ToBeOrNotToBe {
    return {
        toBe: (valToCompare: unknown) => {
            if (val === valToCompare) {
                return true;
            }
            throw new Error("Not Equal");
        },
        notToBe: (valToCompare: unknown) => {
            if (val !== valToCompare) {
                return true;
            }
            throw new Error("Equal");
        },
    };
}
