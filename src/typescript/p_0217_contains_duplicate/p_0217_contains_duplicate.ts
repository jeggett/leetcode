/* time O(n), space O(n) */
export function containsDuplicate(nums: number[]): boolean {
    const numSeenMap: Map<number, void> = new Map<number, void>();
    for (const num of nums) {
        if (numSeenMap.has(num)) {
            return true;
        } else {
            numSeenMap.set(num);
        }
    }
    return false;
}
