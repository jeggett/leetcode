/* time O(n), space O(1) */
export function firstMissingPositive(nums: number[]): number {
  // we consider nums from 1 to maxPossibleMissing
  const maxPossibleMissing = nums.length + 1;
  for (const [i, num] of nums.entries()) {
    if (num <= 0) {
      // replace the zeroes, and negative with maxPossibleMissing, so we can invert their sign
      // so their indices will denote numbers present in the nums array
      nums[i] = maxPossibleMissing;
    }
  }

  for (const num of nums) {
    // to prevent access by negative index
    const absNum = Math.abs(num);
    // we check that nums[num - 1] > 0 so if we meet a duplicate we don't invert the sign twice
    if (absNum < maxPossibleMissing && nums[absNum - 1] > 0) {
      //mark as visited
      nums[absNum - 1] = -nums[absNum - 1];
    }
  }

  for (const [i, num] of nums.entries()) {
    if (num > 0) {
      return i + 1;
    }
  }
  return maxPossibleMissing;
}
