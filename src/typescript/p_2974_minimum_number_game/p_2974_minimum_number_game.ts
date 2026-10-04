/* time: O(n log n), space: O(n) for sorting */
export function numberGame(nums: number[]): number[] {
    nums.sort((left, right) => left - right);
    for (let index = 0; index < nums.length; index += 2) {
        [nums[index], nums[index + 1]] = [nums[index + 1], nums[index]];
    }
    return nums;
}
