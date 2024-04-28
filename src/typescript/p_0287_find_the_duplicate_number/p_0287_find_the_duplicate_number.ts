/* time: O(n), space: O(1) */
export function findDuplicate(nums: number[]): number {
    let [slow, fast, slowFromStart] = [0, 0, 0];

    do {
        slow = nums[slow];
        fast = nums[fast];
        fast = nums[fast];
    } while (slow !== fast); // found the meeting point

    do {
        slow = nums[slow];
        slowFromStart = nums[slowFromStart];
    } while (slow !== slowFromStart);

    return slow;
}
