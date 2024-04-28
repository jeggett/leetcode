/* Time O(N), space O(1) */
export function moveZeroes(nums: number[]): void {
    let slow = 0;
    for (let fast = 0; fast < nums.length; fast++) {
        if (nums[fast] !== 0) {
            nums[slow] = nums[fast];
            slow += 1;
        }
    }

    for (let i = slow; i < nums.length; i++) {
        nums[i] = 0;
    }
}
