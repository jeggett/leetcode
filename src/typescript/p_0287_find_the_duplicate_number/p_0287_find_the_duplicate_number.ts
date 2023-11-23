/* time: O(n), space: O(1) */
export function findDuplicate(nums: number[]): number {
  let i = 0;
  while (i < nums.length) {
    const j = nums[i] - 1;
    // if true, then element is not on the correct place
    if (i !== j) {
      if (nums[i] === nums[j]) {
        return nums[i];
      }
      [nums[i], nums[j]] = [nums[j], nums[i]];
    } else {
      i++;
    }
  }

  return 0;
}
