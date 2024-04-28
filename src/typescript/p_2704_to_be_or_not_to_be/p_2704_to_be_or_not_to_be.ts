type ToBeOrNotToBe = {
    toBe: (val: unknown) => boolean | undefined;
    notToBe: (val: unknown) => boolean | undefined;
};

export function expectFunc(val: unknown): ToBeOrNotToBe {
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
